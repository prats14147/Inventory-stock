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

import threading
import time

from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories import product_repository
from app.services import forecast_service, inventory_service
from app.services.settings_service import effective_lead_time_days, effective_safety_stock_factor
from app.schemas.stockout import RiskLevel, StockoutRiskResponse

# --- Result cache (Tier A) ----------------------------------------------------
#
# A stockout/reorder list forecasts every product, and each forecast is an ML
# predict plus feature engineering. The inputs are historical and immutable
# (see sales_repository.get_full_history_dataframe_cached), so a computed row
# cannot go stale -- but recomputing it on every page view is still the single
# biggest source of dashboard latency.
#
# Keyed by (product_id, effective lead time) because those two fully determine
# the result. Guarded by a lock so concurrent requests can't double-compute.

_cache: dict[tuple[str, int, str | None], tuple[float, StockoutRiskResponse]] = {}
_cache_lock = threading.Lock()


def clear_risk_cache() -> None:
    """Drops every cached risk row. Call after any change to the source data."""
    with _cache_lock:
        _cache.clear()


def _cache_get(key: tuple[str, int, str | None]) -> StockoutRiskResponse | None:
    ttl = get_settings().risk_cache_ttl_seconds
    if ttl <= 0:
        return None
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        stored_at, value = hit
        if time.monotonic() - stored_at > ttl:
            del _cache[key]
            return None
        return value


def _cache_put(key: tuple[str, int, str | None], value: StockoutRiskResponse) -> None:
    if get_settings().risk_cache_ttl_seconds <= 0:
        return
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)


def was_cached(product_id: str, lead_time_days: int | None = None, store_id: str | None = None) -> bool:
    """True when a risk row for this product is already cached (and unexpired).

    Only used to report `served_from_cache` on the dashboard summary, so the UI
    can be honest about a number it did not recompute.
    """
    effective = effective_lead_time_days(None, lead_time_days)
    return _cache_get((product_id, effective, store_id)) is not None


def calculate_stockout_risk(
    db: Session,
    product_id: str,
    lead_time_days: int | None = None,
    store_id: str | None = None,
) -> StockoutRiskResponse:
    effective_lead_time = effective_lead_time_days(db, lead_time_days)

    key = (product_id, effective_lead_time, store_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    result = _compute_stockout_risk(db, product_id, effective_lead_time, store_id)
    _cache_put(key, result)
    return result


def _compute_stockout_risk(
    db: Session, product_id: str, effective_lead_time: int, store_id: str | None = None
) -> StockoutRiskResponse:
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
        # Product forecast is summed across stores; apportion evenly for a
        # store-specific evaluation and say so in the reason/assumptions.
        forecast_lead_time_demand = demand_info["forecast_lead_time_demand"] / store_count
        demand_std = demand_info["historical_daily_demand_std"] / store_count
    else:
        forecast_lead_time_demand = demand_info["forecast_lead_time_demand"]
        demand_std = demand_info["historical_daily_demand_std"]

    safety_stock = demand_std * safety_factor
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

    scope_note = f" Store scope: {store_id} (product demand apportioned evenly across {store_count} stores)." if store_id else ""
    reason = reason + scope_note
    return StockoutRiskResponse(
        product_id=product_id,
        name=name,
        sku=sku,
        category=category,
        store_id=store_id,
        as_of_date=as_of_date,
        current_inventory=current_inventory,
        lead_time_days=effective_lead_time,
        forecast_model_horizon_used=demand_info["forecast_model_horizon_used"],
        forecast_lead_time_demand=forecast_lead_time_demand,
        safety_stock=safety_stock,
        required_inventory=required_inventory,
        risk=risk,
        reason=reason,
    )
