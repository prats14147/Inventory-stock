"""Experimental cumulative-demand benchmark for InventoryAI's synthetic dataset.

This script DOES NOT change production model files. It compares forecasts of
TOTAL units expected over the next 7 or 14 days against simple historical
rate baselines. Results describe performance on this synthetic/demo dataset
only and must not be interpreted as real-business forecast accuracy.

Run from the repository root:
    python ml/training/compare_cumulative_forecasts.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[2]
FEATURES_DIR = ROOT / "ml" / "features"
DATA_PATH = ROOT / "data" / "processed" / "cleaned_inventory.csv"
TRAIN_END = pd.Timestamp("2023-07-01")
VAL_END = pd.Timestamp("2023-10-01")
HORIZONS = (7, 14)

if str(FEATURES_DIR) not in sys.path:
    sys.path.insert(0, str(FEATURES_DIR))
from build_features import FEATURE_COLUMNS, build_supervised_frame  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("compare_cumulative_forecasts")


def score(y_true: pd.Series | np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    actual = np.asarray(y_true, dtype=float)
    predicted = np.clip(np.asarray(y_pred, dtype=float), 0, None)
    denom = np.abs(actual) + np.abs(predicted)
    valid = denom > 1e-9
    smape = float(np.mean(2 * np.abs(predicted[valid] - actual[valid]) / denom[valid]) * 100) if valid.any() else 0.0
    actual_sum = float(np.sum(np.abs(actual)))
    return {
        "mae_units_over_period": float(mean_absolute_error(actual, predicted)),
        "rmse_units_over_period": float(np.sqrt(mean_squared_error(actual, predicted))),
        "wape_pct": float(np.sum(np.abs(actual - predicted)) / actual_sum * 100) if actual_sum else 0.0,
        "smape_pct": smape,
        "mean_actual_units_over_period": float(np.mean(actual)),
        "n": int(len(actual)),
    }


def attach_experimental_history_features(df: pd.DataFrame, sup: pd.DataFrame) -> pd.DataFrame:
    """Add longer rolling and expanding-mean features without changing production features."""
    key_cols = ["Store ID", "Product ID"]
    pieces = []
    ordered = df.sort_values(key_cols + ["Date"])
    for (store, product), group in ordered.groupby(key_cols, sort=False):
        g = group.sort_values("Date").reset_index(drop=True)
        part = pd.DataFrame({
            "Store ID": store,
            "Product ID": product,
            "origin_date": g["Date"],
            "rolling_mean_28_experimental": g["Units Sold"].rolling(28, min_periods=14).mean(),
            "rolling_mean_56_experimental": g["Units Sold"].rolling(56, min_periods=14).mean(),
            "expanding_mean_experimental": g["Units Sold"].expanding(min_periods=14).mean(),
        })
        pieces.append(part)
    extra = pd.concat(pieces, ignore_index=True)
    result = sup.merge(extra, on=["Store ID", "Product ID", "origin_date"], how="left", validate="one_to_one")
    for col in ["rolling_mean_28_experimental", "rolling_mean_56_experimental"]:
        result[col] = result[col].fillna(result["rolling_mean_14"])
    result["expanding_mean_experimental"] = result["expanding_mean_experimental"].fillna(result["rolling_mean_14"])
    # Pandas merge can coerce categorical identifiers back to object dtype.
    for col in ["Store ID", "Product ID", "origin_category", "origin_region", "origin_weather", "origin_seasonality"]:
        result[col] = result[col].astype("category")
    return result


def cumulative_target_frame(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Convert existing origin features into target = sales on days 1..horizon."""
    sup = build_supervised_frame(df, horizon)
    ordered = df.sort_values(["Store ID", "Product ID", "Date"]).copy()
    ordered["cumulative_y"] = ordered.groupby(["Store ID", "Product ID"], sort=False)["Units Sold"].transform(
        lambda series: series.rolling(horizon, min_periods=horizon).sum().shift(-horizon)
    )
    target_map = ordered[["Store ID", "Product ID", "Date", "cumulative_y"]].rename(columns={"Date": "origin_date"})
    sup = sup.drop(columns=["y"]).merge(
        target_map,
        on=["Store ID", "Product ID", "origin_date"],
        how="left",
        validate="one_to_one",
    ).rename(columns={"cumulative_y": "y"})
    sup = sup.dropna(subset=["y"]).copy()
    sup["y"] = sup["y"].astype(float)
    return attach_experimental_history_features(df, sup)


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Expected dataset at {DATA_PATH}; run this script from the project root."
        )

    log.info("Reading synthetic/demo dataset: %s", DATA_PATH)
    df = pd.read_csv(DATA_PATH, parse_dates=["Date"])
    results: dict[str, dict] = {}

    experimental_features = list(FEATURE_COLUMNS) + [
        "rolling_mean_28_experimental",
        "rolling_mean_56_experimental",
        "expanding_mean_experimental",
    ]

    for horizon in HORIZONS:
        log.info(
            "Preparing %s-day cumulative target (sum of future days 1..%s)",
            horizon,
            horizon,
        )
        frame = cumulative_target_frame(df, horizon)

        train = frame[frame["target_date"] < TRAIN_END]
        val = frame[
            (frame["target_date"] >= TRAIN_END)
            & (frame["target_date"] < VAL_END)
        ]
        test = frame[frame["target_date"] >= VAL_END]

        if train.empty or val.empty or test.empty:
            raise RuntimeError(
                f"A chronological split is empty for horizon={horizon}."
            )

        base_cols = list(FEATURE_COLUMNS)
        x_train = train[experimental_features]
        x_val = val[experimental_features]
        x_test = test[experimental_features]
        y_train, y_val, y_test = train["y"], val["y"], test["y"]

        baseline_columns = {
            "7-day mean demand rate x horizon": "rolling_mean_7",
            "14-day mean demand rate x horizon": "rolling_mean_14",
            "28-day mean demand rate x horizon": "rolling_mean_28_experimental",
            "56-day mean demand rate x horizon": "rolling_mean_56_experimental",
            "expanding mean demand rate x horizon": "expanding_mean_experimental",
        }

        candidates: list[dict] = []

        for name, column in baseline_columns.items():
            candidates.append({
                "model": name,
                "validation": score(y_val, val[column].to_numpy() * horizon),
                "kind": "baseline",
            })

        categorical = [
            col for col in base_cols
            if str(x_train[col].dtype) == "category"
        ]

        xgb_model = xgb.XGBRegressor(
            n_estimators=500,
            max_depth=3,
            learning_rate=0.03,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_weight=20,
            reg_lambda=10,
            objective="reg:squarederror",
            enable_categorical=True,
            random_state=42,
            n_jobs=4,
            early_stopping_rounds=40,
            eval_metric="mae",
        )

        log.info(
            "Training regularized XGBoost for %s-day cumulative target",
            horizon,
        )
        xgb_model.fit(
            x_train,
            y_train,
            eval_set=[(x_val, y_val)],
            verbose=False,
        )

        candidates.append({
            "model": "XGBoost regularized + 28/56-day features",
            "validation": score(y_val, xgb_model.predict(x_val)),
            "kind": "xgb",
            "estimator": xgb_model,
        })

        numeric_cols = [
            col for col in experimental_features
            if col not in categorical
            and str(x_train[col].dtype) != "category"
        ]

        hgb = HistGradientBoostingRegressor(
            max_iter=160,
            max_leaf_nodes=15,
            learning_rate=0.06,
            l2_regularization=5.0,
            min_samples_leaf=30,
            random_state=42,
        )

        log.info(
            "Training Histogram Gradient Boosting for %s-day cumulative target",
            horizon,
        )
        hgb.fit(x_train[numeric_cols], y_train)

        candidates.append({
            "model": "Histogram Gradient Boosting + 28/56-day features",
            "validation": score(y_val, hgb.predict(x_val[numeric_cols])),
            "kind": "hgb",
            "estimator": hgb,
        })

        candidates.sort(
            key=lambda item: item["validation"]["mae_units_over_period"]
        )
        winner = candidates[0]

        if winner["kind"] == "baseline":
            winner_test_prediction = (
                test[baseline_columns[winner["model"]]].to_numpy() * horizon
            )
        elif winner["kind"] == "xgb":
            winner_test_prediction = winner["estimator"].predict(x_test)
        else:
            winner_test_prediction = winner["estimator"].predict(
                x_test[numeric_cols]
            )

        test_baselines = {
            name: score(y_test, test[column].to_numpy() * horizon)
            for name, column in baseline_columns.items()
        }

        winner_test_metrics = score(y_test, winner_test_prediction)

        results[str(horizon)] = {
            "target": (
                f"sum of Units Sold on days 1 through {horizon} "
                "after origin_date"
            ),
            "synthetic_demo_data_only": True,
            "rows": {
                "train": len(train),
                "validation": len(val),
                "test": len(test),
            },
            "selected_by_validation_mae": winner["model"],
            "validation_candidates": [
                {"model": item["model"], **item["validation"]}
                for item in candidates
            ],
            "selected_test_metrics": winner_test_metrics,
            "test_baselines": test_baselines,
            "warning": (
                "Results use synthetic/demo data only and do not establish "
                "real-world forecasting accuracy."
            ),
        }

        log.info(
            "%s-day winner: %s; held-out test: %s",
            horizon,
            winner["model"],
            winner_test_metrics,
        )

    print(json.dumps(results, indent=2))
    print(
        "\nEXPERIMENT ONLY: no production model artifacts "
        "were written or replaced."
    )


if __name__ == "__main__":
    main()
