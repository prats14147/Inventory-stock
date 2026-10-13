"""
backend/app/services/forecast_service.py

Loads the saved XGBoost models ONCE (module-level cache) and never
retrains on request, per spec section 24. Forecasts are predicted per store
for one future target date. Product-level results sum those store-specific
point predictions. See docs/limitations.md for the full reasoning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.repositories import product_repository, sales_repository
from app.repositories.sales_repository import get_full_history_dataframe_cached
from app.services.errors import NotFoundError

ROOT = Path(__file__).resolve().parents[3]
ML_FEATURES_DIR = ROOT / "ml" / "features"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"

if str(ML_FEATURES_DIR) not in sys.path:
    sys.path.insert(0, str(ML_FEATURES_DIR))

from build_features import FEATURE_COLUMNS, build_live_feature_row  # noqa: E402

AVAILABLE_HORIZONS = (7, 14)

_model_cache: dict[int, object] = {}
_metadata_cache: dict[int, dict] = {}


def _nearest_available_horizon(requested: int) -> int:
    return min(AVAILABLE_HORIZONS, key=lambda h: abs(h - requested))


def _load_model(horizon: int):
    """Loads and caches the model for `horizon`. Loaded once per process, not per request."""
    actual_horizon = _nearest_available_horizon(horizon)
    if actual_horizon not in _model_cache:
        model_path = ARTIFACTS_DIR / f"forecast_model_h{actual_horizon}.joblib"
        metadata_path = ARTIFACTS_DIR / f"forecast_metadata_h{actual_horizon}.json"
        if not model_path.exists():
            raise FileNotFoundError(
                f"No trained model found at {model_path}. Run ml/training/train_forecast.py first."
            )
        _model_cache[actual_horizon] = joblib.load(model_path)
        _metadata_cache[actual_horizon] = json.loads(metadata_path.read_text())
    return _model_cache[actual_horizon], _metadata_cache[actual_horizon], actual_horizon


def forecast_product_demand(db: Session, product_id: str, horizon: int = 14) -> dict:
    """
    Predicts sales for one future target date (`origin + horizon`), for each
    store, then sums those point predictions across stores. This is NOT a
    cumulative forecast for every day in the horizon.

    If `horizon` isn't exactly 7 or 14, the nearest trained model is used
    and this is reported in the response (never silently substituted).
    """
    if not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")

    model, metadata, actual_horizon = _load_model(horizon)

    history = get_full_history_dataframe_cached(db)
    product_history = history[history["Product ID"] == product_id]

    live_rows = build_live_feature_row(product_history, horizon=actual_horizon)
    if live_rows.empty:
        raise NotFoundError(f"Not enough sales history for product '{product_id}' to forecast.")

    preds = model.predict(live_rows[FEATURE_COLUMNS])
    preds = np.clip(preds, a_min=0, a_max=None)

    per_store = [
        {"store_id": row["Store ID"], "forecast_units": float(pred)}
        for row, pred in zip(live_rows.to_dict("records"), preds)
    ]
    target_date = live_rows["target_date"].iloc[0]

    predicted_units_on_target_date = float(preds.sum())
    xgb_mae = float(metadata["xgboost_metrics"]["mae"])
    baseline_mae = float(metadata.get("baseline_metrics", {}).get("mae", 0.0))
    baseline_improvement_pct = (
        (baseline_mae - xgb_mae) / baseline_mae * 100.0 if baseline_mae > 0 else 0.0
    )

    return {
        "product_id": product_id,
        "requested_horizon_days": horizon,
        "model_horizon_days": actual_horizon,
        "target_date": target_date.date(),
        # Explicit name distinguishes a point prediction from a multi-day sum.
        "predicted_units_on_target_date": predicted_units_on_target_date,
        "forecast_total_units": predicted_units_on_target_date,  # legacy API field
        "prediction_semantics": "single-day point prediction on target_date; not cumulative across the horizon",
        "per_store": per_store,
        "model_test_mae": xgb_mae,
        "baseline_mae": baseline_mae,
        "baseline_improvement_pct": baseline_improvement_pct,
    }


def forecast_daily_rate_and_history_std(
    db: Session,
    product_id: str,
    lead_time_days: int,
    store_id: str | None = None,
) -> dict:
    """
    Used by the stockout-risk/reorder engine (Phase 6): returns the
    a single-day point prediction at the model target date, plus the
    historical daily-demand standard deviation. The lead-time total is an
    explicit constant-rate approximation: point prediction * lead_time_days.
    When `store_id` is provided, both values are calculated for that store.
    """
    nearest_horizon = _nearest_available_horizon(lead_time_days)
    forecast = forecast_product_demand(db, product_id, horizon=nearest_horizon)
    # The prediction is sales on one target date, so it is a daily demand
    # proxy. It is not a cumulative total for the 7/14-day horizon.
    if store_id:
        store_prediction = next(
            (row["forecast_units"] for row in forecast["per_store"] if row["store_id"] == store_id),
            None,
        )
        if store_prediction is None:
            raise NotFoundError(
                f"Not enough sales history to forecast product '{product_id}' at store '{store_id}'."
            )
        forecast_daily_rate = float(store_prediction)
    else:
        forecast_daily_rate = forecast.get(
            "predicted_units_on_target_date", forecast["forecast_total_units"]
        )
    forecast_lead_time_demand = forecast_daily_rate * lead_time_days

    history = get_full_history_dataframe_cached(db)
    product_history = history[history["Product ID"] == product_id]
    if store_id:
        product_history = product_history[product_history["Store ID"] == store_id]
    daily_totals = product_history.groupby("Date")["Units Sold"].sum()
    demand_std = float(daily_totals.std())

    return {
        "product_id": product_id,
        "lead_time_days": lead_time_days,
        "forecast_model_horizon_used": nearest_horizon,
        "forecast_daily_rate": forecast_daily_rate,
        "target_date_prediction_units": forecast_daily_rate,
        "store_id": store_id,
        "forecast_lead_time_demand": forecast_lead_time_demand,
        "historical_daily_demand_std": demand_std,
    }
