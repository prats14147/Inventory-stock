"""Compare forecast candidates on a time-ordered validation window.

The final test window is only evaluated for the candidate selected by
validation MAE. This avoids selecting a model directly on the test results.
The script does not replace the production model artifacts.

Run from the repository root:
    python ml/training/compare_forecast_models.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "features"))

from build_features import FEATURE_COLUMNS, build_supervised_frame  # noqa: E402

PROCESSED_PATH = ROOT / "data" / "processed" / "cleaned_inventory.csv"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
TRAIN_END = pd.Timestamp("2023-07-01")
VAL_END = pd.Timestamp("2023-10-01")
HORIZONS = (7, 14)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("compare_forecast_models")


def metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    y = actual.to_numpy(dtype=float)
    p = np.clip(np.asarray(predicted, dtype=float), 0, None)
    denom = np.abs(y) + np.abs(p)
    valid = denom > 1e-9
    smape = float(np.mean(2 * np.abs(p[valid] - y[valid]) / denom[valid]) * 100) if valid.any() else 0.0
    return {
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "smape": smape,
    }


def time_split(frame: pd.DataFrame):
    train = frame[frame["target_date"] < TRAIN_END]
    val = frame[(frame["target_date"] >= TRAIN_END) & (frame["target_date"] < VAL_END)]
    test = frame[frame["target_date"] >= VAL_END]
    return train, val, test


def xgb_model(*, regularized: bool, n_estimators: int = 400):
    params = {
        "n_estimators": n_estimators,
        "max_depth": 3 if regularized else 6,
        "learning_rate": 0.05 if not regularized else 0.03,
        "subsample": 0.9 if regularized else 0.8,
        "colsample_bytree": 0.9 if regularized else 0.8,
        "min_child_weight": 20 if regularized else 1,
        "reg_lambda": 10 if regularized else 1,
        "objective": "reg:squarederror",
        "enable_categorical": True,
        "random_state": 42,
        "early_stopping_rounds": 40,
        "eval_metric": "mae",
        "n_jobs": 4,
    }
    return xgb.XGBRegressor(**params)


def sklearn_models(categorical: list[str]):
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    preprocess = ColumnTransformer(
        [("categorical", encoder, categorical)], remainder="passthrough", verbose_feature_names_out=False
    )
    return {
        "Extra Trees": make_pipeline(
            preprocess,
            ExtraTreesRegressor(
                n_estimators=160, min_samples_leaf=10, max_features=0.8,
                n_jobs=4, random_state=42,
            ),
        ),
        "Random Forest": make_pipeline(
            preprocess,
            RandomForestRegressor(
                n_estimators=140, min_samples_leaf=12, max_features=0.8,
                n_jobs=4, random_state=42,
            ),
        ),
        # Gradient boosting benchmark using numeric/history/calendar signals.
        "Histogram Gradient Boosting": HistGradientBoostingRegressor(
            max_iter=160, max_leaf_nodes=15, learning_rate=0.06,
            l2_regularization=5.0, min_samples_leaf=30, random_state=42,
        ),
    }


def main() -> None:
    df = pd.read_csv(PROCESSED_PATH, parse_dates=["Date"])
    results: dict[str, dict] = {}

    for horizon in HORIZONS:
        log.info("Building supervised rows for %s-day horizon", horizon)
        supervised = build_supervised_frame(df, horizon)
        train, val, test = time_split(supervised)
        x_train, y_train = train[FEATURE_COLUMNS], train["y"]
        x_val, y_val = val[FEATURE_COLUMNS], val["y"]
        categorical = [col for col in FEATURE_COLUMNS if str(x_train[col].dtype) == "category"]
        candidates: list[dict] = []

        # Score today's deployed weights with the inputs available in real
        # inference (latest-known prices/promotions), not future actuals.
        production = joblib.load(ARTIFACTS_DIR / f"forecast_model_h{horizon}.joblib")
        candidates.append({
            "name": "Saved production XGBoost (live-like inputs)",
            "validation": metrics(y_val, production.predict(x_val)),
            "model": production,
        })

        baseline_columns = {
            "7-day rolling average": "rolling_mean_7",
            "14-day rolling average": "rolling_mean_14",
            "same-weekday seasonal naive": f"lag_{horizon}",
        }
        for name, column in baseline_columns.items():
            pred = val[column].to_numpy()
            candidates.append({"name": name, "validation": metrics(y_val, pred), "model": None})

        for name, model in [
            ("XGBoost current settings", xgb_model(regularized=False)),
            ("XGBoost regularized", xgb_model(regularized=True)),
        ]:
            log.info("Fitting %s for %s-day horizon", name, horizon)
            model.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)
            candidates.append({"name": name, "validation": metrics(y_val, model.predict(x_val)), "model": model})

        models = sklearn_models(categorical)
        numeric_columns = [col for col in FEATURE_COLUMNS if col not in categorical]
        for name, model in models.items():
            log.info("Fitting %s for %s-day horizon", name, horizon)
            if name == "Histogram Gradient Boosting":
                model.fit(x_train[numeric_columns], y_train)
                pred = model.predict(x_val[numeric_columns])
            else:
                model.fit(x_train, y_train)
                pred = model.predict(x_val)
            candidates.append({"name": name, "validation": metrics(y_val, pred), "model": model})

        candidates.sort(key=lambda item: item["validation"]["mae"])
        champion = candidates[0]
        log.info("Validation winner for %s-day horizon: %s", horizon, champion["name"])

        # Evaluate the selected candidate once on the untouched final window.
        if champion["model"] is None:
            column = baseline_columns[champion["name"]]
            test_pred = test[column].to_numpy()
        elif champion["name"] == "Histogram Gradient Boosting":
            test_pred = champion["model"].predict(test[numeric_columns])
        else:
            test_pred = champion["model"].predict(test[FEATURE_COLUMNS])

        final_metrics = metrics(test["y"], test_pred)
        production_test_metrics = metrics(test["y"], production.predict(test[FEATURE_COLUMNS]))
        results[str(horizon)] = {
            "rows": {"train": len(train), "validation": len(val), "test": len(test)},
            "validation_candidates": [
                {"model": item["name"], **item["validation"]}
                for item in candidates
            ],
            "selected_by_validation": champion["name"],
            "selected_test_metrics": final_metrics,
            "saved_production_test_metrics_with_live_like_inputs": production_test_metrics,
            "test_mae_change_vs_saved_production": final_metrics["mae"] - production_test_metrics["mae"],
        }
        log.info(
            "%s-day selected test metrics: %s; saved production with live-like inputs: %s",
            horizon, final_metrics, production_test_metrics,
        )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
