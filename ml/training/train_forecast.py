"""
ml/training/train_forecast.py

Trains and evaluates demand-forecasting models for both required horizons
(7 and 14 days ahead). For each horizon:
  1. Build the supervised frame (ml/features/build_features.py).
  2. Chronological split by target_date (train / val / test).
  3. Baseline: 7-day moving average (already available as rolling_mean_7).
  4. XGBoost regressor (categorical features handled natively).
  5. Evaluate both on the held-out test set: MAE, RMSE, sMAPE.
  6. Save the model, encoders (none needed -- native categorical), feature
     list, metadata, and metrics to ml/artifacts/.

Usage:
    python ml/training/train_forecast.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "ml" / "features"))

from build_features import FEATURE_COLUMNS, build_supervised_frame  # noqa: E402

PROCESSED_PATH = ROOT / "data" / "processed" / "cleaned_inventory.csv"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"

HORIZONS = (7, 14)

# Chronological split cutoffs on target_date (data spans 2022-01-01 to
# 2024-01-01). ~75% train / ~12.5% val / ~12.5% test.
TRAIN_END = pd.Timestamp("2023-07-01")   # exclusive
VAL_END = pd.Timestamp("2023-10-01")     # exclusive

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("train_forecast")


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Symmetric MAPE, careful with zero actual+predicted (spec section 23)."""
    denom = np.abs(y_true) + np.abs(y_pred)
    mask = denom > 1e-9
    if not mask.any():
        return 0.0
    return float(np.mean(2.0 * np.abs(y_pred[mask] - y_true[mask]) / denom[mask]) * 100)


def chronological_split(sup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = sup[sup["target_date"] < TRAIN_END]
    val = sup[(sup["target_date"] >= TRAIN_END) & (sup["target_date"] < VAL_END)]
    test = sup[sup["target_date"] >= VAL_END]
    return train, val, test


def evaluate(y_true: pd.Series, y_pred: np.ndarray) -> dict:
    y_true_arr = y_true.to_numpy()
    return {
        "mae": float(mean_absolute_error(y_true_arr, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true_arr, y_pred))),
        "smape": smape(y_true_arr, y_pred),
        "n": int(len(y_true_arr)),
    }


def train_and_evaluate_horizon(df: pd.DataFrame, horizon: int) -> dict:
    log.info("=== Horizon: %d days ===", horizon)
    sup = build_supervised_frame(df, horizon)
    train, val, test = chronological_split(sup)
    log.info("Rows -- train: %d, val: %d, test: %d", len(train), len(val), len(test))

    X_train, y_train = train[FEATURE_COLUMNS], train["y"]
    X_val, y_val = val[FEATURE_COLUMNS], val["y"]
    X_test, y_test = test[FEATURE_COLUMNS], test["y"]

    # --- Baseline: 7-day moving average of the origin-side history ---
    baseline_pred_test = test["rolling_mean_7"].to_numpy()
    baseline_metrics = evaluate(y_test, baseline_pred_test)
    log.info("Baseline (7-day MA) test metrics: %s", baseline_metrics)

    # --- XGBoost ---
    model = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        enable_categorical=True,
        random_state=42,
        early_stopping_rounds=30,
        eval_metric="mae",
    )
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    xgb_pred_test = model.predict(X_test)
    xgb_pred_test = np.clip(xgb_pred_test, a_min=0, a_max=None)  # sales can't be negative
    xgb_metrics = evaluate(y_test, xgb_pred_test)
    log.info("XGBoost test metrics: %s", xgb_metrics)

    improved = xgb_metrics["mae"] < baseline_metrics["mae"]
    log.info("XGBoost improves on baseline (MAE)? %s", improved)

    # --- Save artifacts ---
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = ARTIFACTS_DIR / f"forecast_model_h{horizon}.joblib"
    joblib.dump(model, model_path)

    metadata = {
        "horizon": horizon,
        "feature_columns": FEATURE_COLUMNS,
        "categorical_columns": [
            c for c in FEATURE_COLUMNS if str(X_train[c].dtype) == "category"
        ],
        "train_rows": len(train),
        "val_rows": len(val),
        "test_rows": len(test),
        "train_date_cutoff": str(TRAIN_END.date()),
        "val_date_cutoff": str(VAL_END.date()),
        "baseline_metrics": baseline_metrics,
        "xgboost_metrics": xgb_metrics,
        "xgboost_improves_on_baseline_mae": improved,
        "best_iteration": int(model.best_iteration) if hasattr(model, "best_iteration") else None,
    }
    metadata_path = ARTIFACTS_DIR / f"forecast_metadata_h{horizon}.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))
    log.info("Saved model to %s and metadata to %s", model_path, metadata_path)

    return metadata


def main() -> None:
    df = pd.read_csv(PROCESSED_PATH, parse_dates=["Date"])
    log.info("Loaded %d rows", len(df))

    all_metadata = {}
    for horizon in HORIZONS:
        all_metadata[horizon] = train_and_evaluate_horizon(df, horizon)

    summary_path = ARTIFACTS_DIR / "forecast_summary.json"
    summary_path.write_text(json.dumps(all_metadata, indent=2))
    log.info("Wrote combined summary to %s", summary_path)


if __name__ == "__main__":
    main()
