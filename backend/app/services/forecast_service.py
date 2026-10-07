"""
backend/app/services/forecast_service.py

Loads the saved XGBoost models ONCE (module-level cache) and never
retrains on request, per spec section 24. Forecasts are computed at the
PRODUCT level (summed across all 5 stores), matching how the master
spec's own chatbot examples talk about demand ("P0001's forecast demand")
-- see docs/limitations.md for the full reasoning.
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
    Forecasts total demand (units) for `product_id`, summed across all
    stores, `horizon` days beyond the latest date in the data.

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

    return {
        "product_id": product_id,
        "requested_horizon_days": horizon,
        "model_horizon_days": actual_horizon,
        "target_date": target_date.date(),
        "forecast_total_units": float(preds.sum()),
        "per_store": per_store,
        "model_test_mae": metadata["xgboost_metrics"]["mae"],
    }


def forecast_daily_rate_and_history_std(db: Session, product_id: str, lead_time_days: int) -> dict:
    """
    Used by the stockout-risk/reorder engine (Phase 6): returns the
    forecast total demand over the next `lead_time_days` (approximated as
    forecast_daily_rate * lead_time_days -- see docs/limitations.md,
    "Lead-time demand approximation"), plus the historical daily-demand
    standard deviation (summed across stores) used for safety stock.
    """
    nearest_horizon = _nearest_available_horizon(lead_time_days)
    forecast = forecast_product_demand(db, product_id, horizon=nearest_horizon)
    # forecast_total_units is the sum of the per-store prediction for the
    # single target date T+h, so it is already a daily product-wide quantity.
    # Dividing by the model horizon would mix daily units with period units
    # and materially understate lead-time demand.
    forecast_daily_rate = forecast["forecast_total_units"]
    forecast_lead_time_demand = forecast_daily_rate * lead_time_days

    history = get_full_history_dataframe_cached(db)
    product_history = history[history["Product ID"] == product_id]
    daily_totals = product_history.groupby("Date")["Units Sold"].sum()
    demand_std = float(daily_totals.std())

    return {
        "product_id": product_id,
        "lead_time_days": lead_time_days,
        "forecast_model_horizon_used": nearest_horizon,
        "forecast_daily_rate": forecast_daily_rate,
        "forecast_lead_time_demand": forecast_lead_time_demand,
        "historical_daily_demand_std": demand_std,
    }
