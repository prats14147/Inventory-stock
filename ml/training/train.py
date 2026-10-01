"""
ml/training/train.py

Trains the demand forecasting model:
  1. Chronological train/val/test split (oldest -> newest, never random).
  2. Baseline: 7-day moving average (already computed in features.csv).
  3. XGBoost regressor using native categorical feature support.
  4. Metrics: MAE, RMSE, sMAPE for both baseline and XGBoost on the same
     test set, so the comparison is apples-to-apples.
  5. Saves model + feature list + categorical categories + metadata to
     ml/artifacts/.

The existing `Demand Forecast` / `demand_forecast_reference` column is
NEVER included as a feature (see docs/limitations.md and spec section 7/22).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent.parent.parent
FEATURES_PATH = ROOT / "data" / "processed" / "features.csv"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("train")

CATEGORICAL_FEATURES = ["product_id", "store_id", "category", "region", "weather_condition", "seasonality"]
NUMERIC_FEATURES = [
    "year", "month", "day", "day_of_week", "week_of_year", "weekend",
    "lag_1", "lag_7", "lag_14",
    "rolling_mean_7", "rolling_mean_14", "rolling_std_7", "rolling_std_14",
    "price", "discount", "promotion", "competitor_pricing", "inventory_level",
]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET = "units_sold"
BASELINE_COLUMN = "baseline_7day_ma"

# Columns that must NEVER be used as model features (leakage risk).
FORBIDDEN_COLUMNS = {"Demand Forecast", "demand_forecast_reference", "Units Ordered", "possible_stock_constrained"}


def chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """70/15/15 split by date -- same global cutoff dates applied to every
    (product, store) group, so no group's test rows can influence another
    group's training via a shared cutoff that varies by group."""
    unique_dates = np.sort(df["date"].unique())
    n = len(unique_dates)
    train_cutoff = unique_dates[int(n * 0.70)]
    val_cutoff = unique_dates[int(n * 0.85)]

    train = df[df["date"] < train_cutoff]
    val = df[(df["date"] >= train_cutoff) & (df["date"] < val_cutoff)]
    test = df[df["date"] >= val_cutoff]

    log.info(
        "Chronological split -- train: %s to %s (%d rows), val: %s to %s (%d rows), test: %s to %s (%d rows)",
        train["date"].min(), train["date"].max(), len(train),
        val["date"].min(), val["date"].max(), len(val),
        test["date"].min(), test["date"].max(), len(test),
    )
    return train, val, test


def prepare_categoricals(df: pd.DataFrame, categories: dict[str, list] | None = None) -> tuple[pd.DataFrame, dict[str, list]]:
    """Cast categorical columns to pandas 'category' dtype for XGBoost's
    native categorical support. If `categories` is given (from training),
    reuse the same category sets so val/test/inference encode consistently."""
    df = df.copy()
    out_categories: dict[str, list] = {}
    for col in CATEGORICAL_FEATURES:
        if categories is not None:
            df[col] = pd.Categorical(df[col], categories=categories[col])
        else:
            df[col] = df[col].astype("category")
        out_categories[col] = list(df[col].cat.categories)
    return df, out_categories


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))

    # sMAPE: guard against 0/0 by only counting rows where |true|+|pred| > 0
    denom = np.abs(y_true) + np.abs(y_pred)
    mask = denom > 0
    smape = float(np.mean(2 * np.abs(y_pred[mask] - y_true[mask]) / denom[mask]) * 100) if mask.any() else 0.0

    return {"mae": float(mae), "rmse": rmse, "smape": smape}


def main() -> None:
    assert not FORBIDDEN_COLUMNS.intersection(FEATURE_COLUMNS), "Leakage-risk column found in feature list!"

    log.info("Loading feature dataset from %s", FEATURES_PATH)
    df = pd.read_csv(FEATURES_PATH, parse_dates=["date"])

    train, val, test = chronological_split(df)

    # Rows with all-NaN lag/rolling features (the first ~14 days of each
    # group) can't be used for training -- drop them from train, but keep
    # val/test rows even if some lag features are NaN (XGBoost handles
    # missing values natively via sparsity-aware splits).
    train = train.dropna(subset=["lag_1"])

    X_train, cat_categories = prepare_categoricals(train[FEATURE_COLUMNS])
    y_train = train[TARGET].to_numpy()

    X_val, _ = prepare_categoricals(val[FEATURE_COLUMNS], categories=cat_categories)
    y_val = val[TARGET].to_numpy()

    X_test, _ = prepare_categoricals(test[FEATURE_COLUMNS], categories=cat_categories)
    y_test = test[TARGET].to_numpy()

    log.info("Training XGBoost on %d rows, %d features (%d categorical)...", len(X_train), len(FEATURE_COLUMNS), len(CATEGORICAL_FEATURES))

    model = XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        enable_categorical=True,
        tree_method="hist",
        early_stopping_rounds=30,
        eval_metric="mae",
        random_state=42,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    log.info("Best iteration: %d", model.best_iteration)

    # --- Evaluate XGBoost on the held-out test set ---
    y_pred_xgb = model.predict(X_test)
    y_pred_xgb = np.clip(y_pred_xgb, 0, None)  # sales can't be negative
    xgb_metrics = compute_metrics(y_test, y_pred_xgb)

    # --- Evaluate the 7-day moving-average baseline on the SAME test rows ---
    baseline_pred = test[BASELINE_COLUMN].to_numpy()
    # Baseline can be NaN for the very first rows of a group; fill with the
    # overall training mean as a last resort so both models are scored on
    # the exact same rows.
    baseline_pred = np.where(np.isnan(baseline_pred), y_train.mean(), baseline_pred)
    baseline_metrics = compute_metrics(y_test, baseline_pred)

    log.info("Baseline (7-day MA) -- MAE: %.3f, RMSE: %.3f, sMAPE: %.2f%%", baseline_metrics["mae"], baseline_metrics["rmse"], baseline_metrics["smape"])
    log.info("XGBoost           -- MAE: %.3f, RMSE: %.3f, sMAPE: %.2f%%", xgb_metrics["mae"], xgb_metrics["rmse"], xgb_metrics["smape"])

    improvement_mae = 100 * (baseline_metrics["mae"] - xgb_metrics["mae"]) / baseline_metrics["mae"]
    log.info("XGBoost improvement over baseline (MAE): %.2f%%", improvement_mae)

    # --- Feature importance (for transparency / documentation) ---
    importances = dict(zip(FEATURE_COLUMNS, model.feature_importances_.tolist()))
    importances = dict(sorted(importances.items(), key=lambda kv: kv[1], reverse=True))

    # --- Save artifacts ---
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, ARTIFACTS_DIR / "xgboost_model.joblib")

    metadata = {
        "trained_at": datetime.utcnow().isoformat(),
        "feature_columns": FEATURE_COLUMNS,
        "categorical_features": CATEGORICAL_FEATURES,
        "categorical_categories": {k: [str(v) for v in vals] for k, vals in cat_categories.items()},
        "target": TARGET,
        "train_rows": len(X_train),
        "val_rows": len(X_val),
        "test_rows": len(X_test),
        "split_dates": {
            "train_end": str(train["date"].max().date()),
            "val_start": str(val["date"].min().date()),
            "val_end": str(val["date"].max().date()),
            "test_start": str(test["date"].min().date()),
            "test_end": str(test["date"].max().date()),
        },
        "metrics": {
            "baseline_7day_ma": baseline_metrics,
            "xgboost": xgb_metrics,
            "xgboost_improvement_over_baseline_mae_pct": improvement_mae,
        },
        "feature_importance": importances,
        "model_params": model.get_params(),
        "best_iteration": int(model.best_iteration),
    }
    # get_params() includes non-JSON-serializable values sometimes; sanitize
    metadata["model_params"] = {k: (v if isinstance(v, (int, float, str, bool)) or v is None else str(v)) for k, v in metadata["model_params"].items()}

    with open(ARTIFACTS_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    log.info("Saved model and metadata to %s", ARTIFACTS_DIR)


if __name__ == "__main__":
    main()
