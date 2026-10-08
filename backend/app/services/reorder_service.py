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

from app.repositories import product_repository
from app.services import forecast_service, inventory_service
from app.services.settings_service import effective_lead_time_days, effective_safety_stock_factor
from app.schemas.reorder import ReorderResponse


def calculate_reorder(
    db: Session,
    product_id: str,
    lead_time_days: int | None = None,
    store_id: str | None = None,
) -> ReorderResponse:
    effective_lead_time = effective_lead_time_days(db, lead_time_days)
    safety_factor = effective_safety_stock_factor(db)

    current = inventory_service.get_product_inventory(db, product_id)  # raises NotFoundError if unknown
    if store_id:
        store_rows = [s for s in current.stores if s.store_id == store_id]
        if not store_rows:
            from app.services.errors import NotFoundError as _NotFound
            raise _NotFound(f"No inventory record for product '{product_id}' at store '{store_id}'.")
        current_inventory = float(sum(s.inventory_level for s in store_rows))
        as_of_date = current.as_of_date
        store_count = max(1, len(current.stores))
    else:
        current_inventory = current.total_inventory
        as_of_date = current.as_of_date
        store_count = None

    product = product_repository.get_product(db, product_id)
    name = product.name if product else product_id
    sku = product.sku if product else product_id
    category = product.category if product else "Unknown"

    demand_info = forecast_service.forecast_daily_rate_and_history_std(db, product_id, effective_lead_time)
    if store_id and store_count:
        forecast_lead_time_demand = demand_info["forecast_lead_time_demand"] / store_count
        demand_std = demand_info["historical_daily_demand_std"] / store_count
    else:
        forecast_lead_time_demand = demand_info["forecast_lead_time_demand"]
        demand_std = demand_info["historical_daily_demand_std"]

    safety_stock = demand_std * safety_factor
    recommended_quantity = max(0.0, forecast_lead_time_demand + safety_stock - current_inventory)

    assumptions = {
        "lead_time_days": effective_lead_time,
        "lead_time_source": "configurable default (DEFAULT_LEAD_TIME_DAYS) -- "
        "no real supplier lead time exists in this dataset, see docs/limitations.md",
            "safety_stock_service_factor": safety_factor,
        "forecast_model_horizon_used": demand_info["forecast_model_horizon_used"],
        "lead_time_demand_approximation": "forecast_daily_rate * lead_time_days "
        "(near-constant demand rate over the window assumption, see docs/limitations.md)",
    }
    if store_id:
        assumptions["store_scope"] = store_id
        assumptions["store_demand_apportionment"] = (
            f"product demand apportioned evenly across {store_count} stores"
        )

    return ReorderResponse(
        product_id=product_id,
        name=name,
        sku=sku,
        category=category,
        store_id=store_id,
        as_of_date=as_of_date,
        current_inventory=current_inventory,
        forecast_lead_time_demand=forecast_lead_time_demand,
        safety_stock=safety_stock,
        recommended_reorder_quantity=recommended_quantity,
        assumptions=assumptions,
    )
