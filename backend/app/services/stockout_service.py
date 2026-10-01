"""
backend/app/services/stockout_service.py

Deterministic stockout-risk engine (spec section 25). NOT an ML model --
a transparent, documented formula:

    required_inventory = forecast_demand_during_lead_time + safety_stock

Risk tiers (documented, and configurable via the same settings that drive
the formula -- LEAD_TIME_DAYS, SAFETY_STOCK_SERVICE_FACTOR):
    HIGH   -- current_inventory < forecast_lead_time_demand
              (can't even cover expected demand before the next delivery)
    MEDIUM -- forecast_lead_time_demand <= current_inventory < required_inventory
              (covers expected demand, but not the safety buffer)
    LOW    -- current_inventory >= required_inventory

This is an analytical recommendation, not a claim of optimal inventory
policy -- see docs/limitations.md.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import forecast_service, inventory_service
from app.schemas.stockout import RiskLevel, StockoutRiskResponse


def calculate_stockout_risk(db: Session, product_id: str, lead_time_days: int | None = None) -> StockoutRiskResponse:
    settings = get_settings()
    effective_lead_time = lead_time_days if lead_time_days is not None else settings.default_lead_time_days

    current = inventory_service.get_product_inventory(db, product_id)  # raises NotFoundError if unknown
    current_inventory = current.total_inventory

    demand_info = forecast_service.forecast_daily_rate_and_history_std(db, product_id, effective_lead_time)
    forecast_lead_time_demand = demand_info["forecast_lead_time_demand"]
    demand_std = demand_info["historical_daily_demand_std"]

    safety_stock = demand_std * settings.safety_stock_service_factor
    required_inventory = forecast_lead_time_demand + safety_stock

    if current_inventory < forecast_lead_time_demand:
        risk = RiskLevel.HIGH
        reason = (
            f"Current inventory ({current_inventory:.0f}) is below the forecast demand for the "
            f"{effective_lead_time}-day lead time alone ({forecast_lead_time_demand:.1f}), before even "
            f"accounting for safety stock."
        )
    elif current_inventory < required_inventory:
        risk = RiskLevel.MEDIUM
        reason = (
            f"Current inventory ({current_inventory:.0f}) covers the forecast lead-time demand "
            f"({forecast_lead_time_demand:.1f}) but not the recommended safety-stock buffer of "
            f"{safety_stock:.1f} (required: {required_inventory:.1f})."
        )
    else:
        risk = RiskLevel.LOW
        reason = (
            f"Current inventory ({current_inventory:.0f}) covers both the forecast lead-time demand "
            f"({forecast_lead_time_demand:.1f}) and the safety-stock buffer ({safety_stock:.1f})."
        )

    return StockoutRiskResponse(
        product_id=product_id,
        as_of_date=current.as_of_date,
        current_inventory=current_inventory,
        lead_time_days=effective_lead_time,
        forecast_model_horizon_used=demand_info["forecast_model_horizon_used"],
        forecast_lead_time_demand=forecast_lead_time_demand,
        safety_stock=safety_stock,
        required_inventory=required_inventory,
        risk=risk,
        reason=reason,
    )
