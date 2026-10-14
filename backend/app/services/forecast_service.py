
"""
backend/app/services/forecast_service.py

Loads saved XGBoost models once per process and does not retrain on requests.

The model predicts sales for one future target date per store. Product-level
forecasts sum the available store predictions.

IMPORTANT:
- A target-date prediction is not a cumulative forecast over the horizon.
- Lead-time demand below is a constant-rate approximation.
- Products/stores with insufficient history are reported as unavailable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from numbers import Integral
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.repositories import product_repository
from app.repositories.sales_repository import get_full_history_dataframe_cached
from app.services.errors import NotFoundError


ROOT = Path(__file__).resolve().parents[3]
ML_FEATURES_DIR = ROOT / "ml" / "features"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"

if str(ML_FEATURES_DIR) not in sys.path:
    sys.path.insert(0, str(ML_FEATURES_DIR))

from build_features import FEATURE_COLUMNS, build_live_feature_row  # noqa: E402


AVAILABLE_HORIZONS = (7, 14)

_model_cache: dict[int, Any] = {}
_metadata_cache: dict[int, dict] = {}


def _validate_positive_days(value: int, name: str) -> int:
    """Validate a positive integer day count."""
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return int(value)


def _nearest_available_horizon(requested: int) -> int:
    """Return the closest horizon for which a model is available."""
    requested = _validate_positive_days(requested, "horizon")
    return min(AVAILABLE_HORIZONS, key=lambda h: abs(h - requested))


def _load_model(horizon: int):
    """Load and cache a trained model and its metadata."""
    actual_horizon = _nearest_available_horizon(horizon)

    if actual_horizon not in _model_cache:
        model_path = ARTIFACTS_DIR / f"forecast_model_h{actual_horizon}.joblib"
        metadata_path = ARTIFACTS_DIR / f"forecast_metadata_h{actual_horizon}.json"

        if not model_path.is_file():
            raise FileNotFoundError(
                f"Trained model not found: {model_path}. "
                "Run ml/training/train_forecast.py first."
            )

        if not metadata_path.is_file():
            raise FileNotFoundError(
                f"Forecast metadata not found: {metadata_path}."
            )

        model = joblib.load(model_path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        if not isinstance(metadata, dict):
            raise ValueError(
                f"Invalid forecast metadata format: {metadata_path}"
            )

        _model_cache[actual_horizon] = model
        _metadata_cache[actual_horizon] = metadata

    return (
        _model_cache[actual_horizon],
        _metadata_cache[actual_horizon],
        actual_horizon,
    )


def _optional_metric(value: Any) -> float | None:
    """Return a finite metric, or None when it is missing or invalid."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(result):
        return None

    return result


def _get_model_metrics(metadata: dict) -> tuple[float | None, float | None, float | None]:
    """Read saved evaluation metrics without inventing missing values."""
    xgb_metrics = metadata.get("xgboost_metrics") or {}
    baseline_metrics = metadata.get("baseline_metrics") or {}

    xgb_mae = _optional_metric(xgb_metrics.get("mae"))
    baseline_mae = _optional_metric(baseline_metrics.get("mae"))

    improvement = None
    if xgb_mae is not None and baseline_mae is not None and baseline_mae > 0:
        improvement = (baseline_mae - xgb_mae) / baseline_mae * 100.0

    return xgb_mae, baseline_mae, improvement


def _get_history(db: Session) -> pd.DataFrame:
    """Load historical sales and validate the columns required by forecasting."""
    history = get_full_history_dataframe_cached(db)

    required_columns = {
        "Product ID",
        "Store ID",
        "Date",
        "Units Sold",
    }
    missing_columns = required_columns.difference(history.columns)

    if missing_columns:
        raise ValueError(
            "Sales history is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    if history.empty:
        raise NotFoundError("No sales history is available for forecasting.")

    return history


def _calculate_daily_demand_std(
    product_history: pd.DataFrame,
    product_id: str,
    store_id: str | None = None,
) -> float:
    """
    Calculate sample standard deviation of observed daily sales.

    Missing dates are not automatically treated as zero-sales days because
    missing records and genuine zero demand cannot safely be distinguished here.
    """
    if store_id is not None:
        product_history = product_history[
            product_history["Store ID"].astype(str) == str(store_id)
        ]

    if product_history.empty:
        location = f" at store '{store_id}'" if store_id is not None else ""
        raise NotFoundError(
            f"No sales history found for product '{product_id}'{location}."
        )

    history = product_history[["Date", "Units Sold"]].copy()
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce")
    history["Units Sold"] = pd.to_numeric(
        history["Units Sold"], errors="coerce"
    )
    history = history.dropna(subset=["Date", "Units Sold"])

    if history.empty:
        raise NotFoundError(
            f"Valid daily sales history is unavailable for product '{product_id}'."
        )

    daily_totals = history.groupby("Date")["Units Sold"].sum()

    if len(daily_totals) < 2:
        raise NotFoundError(
            f"At least two observed sales dates are required to calculate "
            f"demand variability for product '{product_id}'."
        )

    demand_std = float(daily_totals.std(ddof=1))

    if not np.isfinite(demand_std):
        raise NotFoundError(
            f"Demand variability could not be calculated for product '{product_id}'."
        )

    return max(0.0, demand_std)


def forecast_product_demand(
    db: Session,
    product_id: str,
    horizon: int = 14,
) -> dict:
    """
    Predict sales for one future target date, separately for each eligible store.

    The product-level prediction sums the available store predictions. Stores
    without sufficient history may not appear in the forecast.
    """
    horizon = _validate_positive_days(horizon, "horizon")

    if not product_repository.product_exists(db, product_id):
        raise NotFoundError(
            f"Product '{product_id}' was not found in the current inventory data."
        )

    model, metadata, actual_horizon = _load_model(horizon)
    history = _get_history(db)

    product_history = history[
        history["Product ID"].astype(str) == str(product_id)
    ].copy()

    if product_history.empty:
        raise NotFoundError(
            f"No sales history found for product '{product_id}'."
        )

    live_rows = build_live_feature_row(
        product_history,
        horizon=actual_horizon,
    )

    if live_rows.empty:
        raise NotFoundError(
            f"Not enough sales history for product '{product_id}' to forecast."
        )

    missing_features = set(FEATURE_COLUMNS).difference(live_rows.columns)
    if missing_features:
        raise ValueError(
            "Forecast feature data is missing required columns: "
            + ", ".join(sorted(missing_features))
        )

    feature_data = live_rows[FEATURE_COLUMNS]

    if feature_data.isna().any().any():
        raise ValueError(
            f"Forecast features contain missing values for product '{product_id}'."
        )

    predictions = np.asarray(model.predict(feature_data), dtype=float).reshape(-1)

    if len(predictions) != len(live_rows):
        raise ValueError(
            "The forecasting model returned a different number of predictions "
            "than the number of store rows."
        )

    if not np.isfinite(predictions).all():
        raise ValueError(
            f"The forecasting model returned invalid predictions for '{product_id}'."
        )

    # Demand cannot be negative.
    predictions = np.clip(predictions, a_min=0.0, a_max=None)

    per_store = [
        {
            "store_id": row["Store ID"],
            "forecast_units": float(prediction),
        }
        for row, prediction in zip(
            live_rows.to_dict("records"),
            predictions,
        )
    ]

    target_dates = pd.to_datetime(live_rows["target_date"], errors="coerce")
    if target_dates.isna().any():
        raise ValueError("The forecast contains an invalid target date.")

    unique_target_dates = target_dates.dt.normalize().unique()
    if len(unique_target_dates) != 1:
        raise ValueError(
            "Store predictions do not share the same forecast target date."
        )

    target_date = pd.Timestamp(unique_target_dates[0]).date()
    predicted_units = float(predictions.sum())

    xgb_mae, baseline_mae, improvement_pct = _get_model_metrics(metadata)

    return {
        "product_id": product_id,
        "requested_horizon_days": horizon,
        "model_horizon_days": actual_horizon,
        "target_date": target_date,
        "predicted_units_on_target_date": predicted_units,
        # Retained for compatibility with existing API consumers.
        "forecast_total_units": predicted_units,
        "prediction_semantics": (
            "single-day point prediction on target_date; "
            "not cumulative across the horizon"
        ),
        "per_store": per_store,
        "model_test_mae": xgb_mae,
        "baseline_mae": baseline_mae,
        "baseline_improvement_pct": improvement_pct,
    }


def forecast_daily_rate_and_history_std(
    db: Session,
    product_id: str,
    lead_time_days: int,
    store_id: str | None = None,
) -> dict:
    """
    Return a forecast-based daily demand proxy and historical daily-demand std.

    The lead-time demand is approximated as:
        forecast_daily_rate * lead_time_days

    This is a constant-rate approximation, not a true multi-day model forecast.
    """
    lead_time_days = _validate_positive_days(
        lead_time_days,
        "lead_time_days",
    )

    nearest_horizon = _nearest_available_horizon(lead_time_days)

    forecast = forecast_product_demand(
        db,
        product_id,
        horizon=nearest_horizon,
    )

    if store_id is not None:
        store_prediction = next(
            (
                row["forecast_units"]
                for row in forecast["per_store"]
                if str(row["store_id"]) == str(store_id)
            ),
            None,
        )

        if store_prediction is None:
            raise NotFoundError(
                f"Not enough sales history to forecast product '{product_id}' "
                f"at store '{store_id}'."
            )

        forecast_daily_rate = float(store_prediction)
    else:
        forecast_daily_rate = float(
            forecast["predicted_units_on_target_date"]
        )

    if not np.isfinite(forecast_daily_rate) or forecast_daily_rate < 0:
        raise ValueError(
            f"Invalid daily demand prediction for product '{product_id}'."
        )

    forecast_lead_time_demand = forecast_daily_rate * lead_time_days

    history = _get_history(db)
    product_history = history[
        history["Product ID"].astype(str) == str(product_id)
    ].copy()

    demand_std = _calculate_daily_demand_std(
        product_history=product_history,
        product_id=product_id,
        store_id=store_id,
    )

    return {
        "product_id": product_id,
        "lead_time_days": lead_time_days,
        "forecast_model_horizon_used": nearest_horizon,
        "forecast_daily_rate": forecast_daily_rate,
        "target_date_prediction_units": forecast_daily_rate,
        "store_id": store_id,
        "forecast_lead_time_demand": forecast_lead_time_demand,
        "historical_daily_demand_std": demand_std,
        "lead_time_demand_method": "constant_daily_rate_approximation",
    }
