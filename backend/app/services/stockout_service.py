"""
backend/app/services/stockout_service.py

Deterministic stockout-risk engine using a shared inventory-risk policy.
"""

from __future__ import annotations

import threading
import time

from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories import product_repository
from app.services import forecast_service, inventory_service
from app.services.settings_service import (
    effective_lead_time_days,
    effective_safety_stock_factor,
)
from app.schemas.stockout import RiskLevel, StockoutRiskResponse
from app.services.errors import NotFoundError
from app.services.inventory_risk_policy import (
    calculate_safety_stock,
    classify_risk_by_inventory,
)


# Result cache
# Cache keys include lead time and safety factor so changes to settings
# cannot accidentally reuse a result calculated with old settings.

_cache: dict[
    tuple[str, int, str | None, float],
    tuple[float, StockoutRiskResponse],
] = {}

_cache_lock = threading.Lock()


def clear_risk_cache() -> None:
    """Remove every cached stockout-risk result."""
    with _cache_lock:
        _cache.clear()


def _cache_get(
    key: tuple[str, int, str | None, float],
) -> StockoutRiskResponse | None:
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


def _cache_put(
    key: tuple[str, int, str | None, float],
    value: StockoutRiskResponse,
) -> None:
    if get_settings().risk_cache_ttl_seconds <= 0:
        return

    with _cache_lock:
        _cache[key] = (time.monotonic(), value)


def was_cached(
    product_id: str,
    lead_time_days: int | None = None,
    store_id: str | None = None,
    db: Session | None = None,
) -> bool:
    """Return whether an unexpired result is already cached."""
    effective = effective_lead_time_days(db, lead_time_days)
    safety_factor = effective_safety_stock_factor(db)

    key = (product_id, effective, store_id, safety_factor)

    return _cache_get(key) is not None


def calculate_stockout_risk(
    db: Session,
    product_id: str,
    lead_time_days: int | None = None,
    store_id: str | None = None,
) -> StockoutRiskResponse:
    """Calculate stockout risk for a product."""
    effective_lead_time = effective_lead_time_days(
        db, lead_time_days
    )
    safety_factor = effective_safety_stock_factor(db)

    key = (
        product_id,
        effective_lead_time,
        store_id,
        safety_factor,
    )

    cached = _cache_get(key)

    if cached is not None:
        return cached

    result = _compute_stockout_risk(
        db,
        product_id,
        effective_lead_time,
        store_id,
        safety_factor,
    )

    _cache_put(key, result)

    return result


def list_stockout_risks(
    db: Session,
    lead_time_days: int | None = None,
    store_id: str | None = None,
    category: str | None = None,
    product_id: str | None = None,
) -> list[StockoutRiskResponse]:
    """Return stockout-risk results for matching products."""
    if (
        product_id
        and not product_repository.product_exists(db, product_id)
    ):
        raise NotFoundError(
            f"Product '{product_id}' was not found "
            "in the current inventory data."
        )

    listing = inventory_service.get_current_inventory_listing(
        db,
        category=category,
    )

    pairs = sorted(
        {
            (row.product_id, row.store_id)
            for row in listing.items
        }
    )

    if product_id:
        pairs = [
            (pid, sid)
            for pid, sid in pairs
            if pid == product_id
        ]

    if store_id:
        pairs = [
            (pid, sid)
            for pid, sid in pairs
            if sid == store_id
        ]

    results: list[StockoutRiskResponse] = []

    for current_product_id, current_store_id in pairs:
        try:
            results.append(
                calculate_stockout_risk(
                    db,
                    current_product_id,
                    lead_time_days=lead_time_days,
                    store_id=current_store_id,
                )
            )
        except NotFoundError:
            # Do not fabricate a forecast-based risk result when
            # usable demand history is unavailable.
            continue

    risk_order = {
        RiskLevel.HIGH: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.LOW: 2,
    }

    results.sort(
        key=lambda item: (
            risk_order[item.risk],
            (
                item.estimated_days_of_stock
                if item.estimated_days_of_stock is not None
                else float("inf")
            ),
            item.product_id,
            item.store_id or "",
        )
    )

    return results


def _compute_stockout_risk(
    db: Session,
    product_id: str,
    effective_lead_time: int,
    store_id: str | None = None,
    safety_factor: float | None = None,
) -> StockoutRiskResponse:
    """Calculate demand coverage, safety stock and risk classification."""
    if safety_factor is None:
        safety_factor = effective_safety_stock_factor(db)

    current = inventory_service.get_product_inventory(
        db,
        product_id,
    )

    if store_id:
        store_rows = [
            store
            for store in current.stores
            if store.store_id == store_id
        ]

        if not store_rows:
            raise NotFoundError(
                f"No inventory record for product '{product_id}' "
                f"at store '{store_id}'."
            )

        current_inventory = float(
            sum(store.inventory_level for store in store_rows)
        )
        as_of_date = current.as_of_date
    else:
        current_inventory = current.total_inventory
        as_of_date = current.as_of_date

    product = product_repository.get_product(db, product_id)

    name = product.name if product else product_id
    sku = product.sku if product else product_id
    category = product.category if product else "Unknown"

    if store_id:
        demand_info = (
            forecast_service.forecast_daily_rate_and_history_std(
                db,
                product_id,
                effective_lead_time,
                store_id=store_id,
            )
        )
    else:
        demand_info = (
            forecast_service.forecast_daily_rate_and_history_std(
                db,
                product_id,
                effective_lead_time,
            )
        )

    forecast_daily_demand = demand_info["forecast_daily_rate"]
    forecast_lead_time_demand = demand_info[
        "forecast_lead_time_demand"
    ]
    demand_std = demand_info["historical_daily_demand_std"]

    estimated_days_of_stock = (
        current_inventory / forecast_daily_demand
        if forecast_daily_demand > 0
        else None
    )

    coverage_description = (
        f"{estimated_days_of_stock:.1f} days"
        if estimated_days_of_stock is not None
        else "undefined because predicted daily demand is zero"
    )

    # Calculate safety stock using the shared policy.
    # Daily demand variability is scaled by the square root
    # of the supplier lead time.
    safety_stock = calculate_safety_stock(
        demand_std,
        safety_factor,
        effective_lead_time,
    )

    # Target inventory covers expected lead-time demand plus
    # the safety-stock buffer.
    required_inventory = (
        forecast_lead_time_demand + safety_stock
    )

    # IMPORTANT:
    # Use the same lead-time demand value for both the target
    # inventory and risk classification.
    risk = RiskLevel(
        classify_risk_by_inventory(
            current_inventory=current_inventory,
            forecast_lead_time_demand=forecast_lead_time_demand,
            safety_stock=safety_stock,
        )
    )

    if risk == RiskLevel.HIGH:
        reason = (
            f"HIGH risk: on-hand stock is estimated to cover "
            f"{coverage_description}, shorter than the "
            f"{effective_lead_time}-day supplier lead time. "
            f"Forecast daily demand is "
            f"{forecast_daily_demand:.1f} units/day, estimated "
            f"lead-time demand is "
            f"{forecast_lead_time_demand:.1f} units, and safety "
            f"stock is {safety_stock:.1f} units."
        )

    elif risk == RiskLevel.MEDIUM:
        reason = (
            f"MEDIUM risk: on-hand stock covers estimated "
            f"lead-time demand "
            f"({forecast_lead_time_demand:.1f} units) but not "
            f"the safety-stock buffer ({safety_stock:.1f} units; "
            f"{required_inventory:.1f} units required). "
            f"Estimated coverage is {coverage_description}."
        )

    else:
        reason = (
            f"LOW risk: on-hand stock covers estimated "
            f"lead-time demand "
            f"({forecast_lead_time_demand:.1f} units) plus "
            f"safety stock ({safety_stock:.1f} units; "
            f"{required_inventory:.1f} units required). "
            f"Estimated coverage is {coverage_description}."
        )

    if store_id:
        scope_note = (
            f" Store scope: {store_id}; demand comes from "
            "that store's own forecast and history."
        )
    else:
        scope_note = (
            " Product scope: inventory and demand are "
            "summed across stores."
        )

    reason += scope_note

    return StockoutRiskResponse(
        product_id=product_id,
        name=name,
        sku=sku,
        category=category,
        store_id=store_id,
        as_of_date=as_of_date,
        current_inventory=current_inventory,
        lead_time_days=effective_lead_time,
        forecast_model_horizon_used=(
            demand_info["forecast_model_horizon_used"]
        ),
        forecast_daily_demand=forecast_daily_demand,
        estimated_days_of_stock=estimated_days_of_stock,
        forecast_lead_time_demand=forecast_lead_time_demand,
        safety_stock=safety_stock,
        required_inventory=required_inventory,
        risk=risk,
        reason=reason,
    )
