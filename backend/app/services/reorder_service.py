"""
backend/app/services/reorder_service.py

reorder_quantity = max(0, forecast_lead_time_demand + safety_stock - current_inventory)

No real supplier lead-time exists in this dataset (see docs/limitations.md),
so lead_time_days uses the configurable DEFAULT_LEAD_TIME_DAYS setting
unless explicitly overridden -- this assumption is always echoed back in
the response's `assumptions` field, never silently applied.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import forecast_service, inventory_service
from app.schemas.reorder import ReorderResponse


def calculate_reorder(db: Session, product_id: str, lead_time_days: int | None = None) -> ReorderResponse:
    settings = get_settings()
    effective_lead_time = lead_time_days if lead_time_days is not None else settings.default_lead_time_days

    current = inventory_service.get_product_inventory(db, product_id)  # raises NotFoundError if unknown
    current_inventory = current.total_inventory

    demand_info = forecast_service.forecast_daily_rate_and_history_std(db, product_id, effective_lead_time)
    forecast_lead_time_demand = demand_info["forecast_lead_time_demand"]
    demand_std = demand_info["historical_daily_demand_std"]

    safety_stock = demand_std * settings.safety_stock_service_factor
    recommended_quantity = max(0.0, forecast_lead_time_demand + safety_stock - current_inventory)

    return ReorderResponse(
        product_id=product_id,
        as_of_date=current.as_of_date,
        current_inventory=current_inventory,
        forecast_lead_time_demand=forecast_lead_time_demand,
        safety_stock=safety_stock,
        recommended_reorder_quantity=recommended_quantity,
        assumptions={
            "lead_time_days": effective_lead_time,
            "lead_time_source": "configurable default (DEFAULT_LEAD_TIME_DAYS) -- "
            "no real supplier lead time exists in this dataset, see docs/limitations.md",
            "safety_stock_service_factor": settings.safety_stock_service_factor,
            "forecast_model_horizon_used": demand_info["forecast_model_horizon_used"],
            "lead_time_demand_approximation": "forecast_daily_rate * lead_time_days "
            "(near-constant demand rate over the window assumption, see docs/limitations.md)",
        },
    )
