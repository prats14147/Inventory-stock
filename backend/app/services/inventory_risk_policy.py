
"""Shared, deterministic inventory-risk and reorder policy helpers.

These helpers are not an ML classifier. Forecast quality still depends on
the forecast model and the assumption used to estimate lead-time demand.
"""

from __future__ import annotations

from math import isfinite, sqrt


def _finite_number(value: float, name: str) -> float:
    """Convert a numeric input and reject NaN/inf."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc

    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number")

    return number


def _validate_lead_time(lead_time_days: int) -> int:
    """Require lead time to be a positive whole number of days."""
    if isinstance(lead_time_days, bool):
        raise ValueError(
            "lead_time_days must be at least 1 and a positive integer"
        )

    try:
        lead_time = int(lead_time_days)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "lead_time_days must be at least 1 and a positive integer"
        ) from exc

    if lead_time != lead_time_days or lead_time < 1:
        raise ValueError(
            "lead_time_days must be at least 1 and a positive integer"
        )

    return lead_time


def calculate_safety_stock(
    historical_daily_demand_std: float,
    service_factor: float,
    lead_time_days: int,
) -> float:
    """Calculate safety stock from demand variability and lead time.

    Formula:
        safety_stock = service_factor * daily_std * sqrt(lead_time_days)

    This assumes daily demand errors are approximately independent.
    The service factor should be calibrated against real forecast errors.
    """
    lead_time = _validate_lead_time(lead_time_days)

    daily_std = _finite_number(
        historical_daily_demand_std,
        "historical_daily_demand_std",
    )
    factor = _finite_number(service_factor, "service_factor")

    if daily_std < 0:
        raise ValueError(
            "historical_daily_demand_std cannot be negative"
        )

    if factor < 0:
        raise ValueError("service_factor cannot be negative")

    return daily_std * factor * sqrt(lead_time)


def calculate_required_inventory(
    forecast_lead_time_demand: float,
    safety_stock: float,
) -> float:
    """Calculate expected lead-time demand plus safety stock."""
    demand = _finite_number(
        forecast_lead_time_demand,
        "forecast_lead_time_demand",
    )
    buffer = _finite_number(safety_stock, "safety_stock")

    if demand < 0:
        raise ValueError(
            "forecast_lead_time_demand cannot be negative"
        )

    if buffer < 0:
        raise ValueError("safety_stock cannot be negative")

    return demand + buffer


def calculate_reorder_quantity(
    current_inventory: float,
    forecast_lead_time_demand: float,
    safety_stock: float,
) -> float:
    """Calculate how many units are needed to reach the stock target."""
    on_hand = _finite_number(current_inventory, "current_inventory")

    if on_hand < 0:
        raise ValueError("current_inventory cannot be negative")

    required = calculate_required_inventory(
        forecast_lead_time_demand,
        safety_stock,
    )

    return max(0.0, required - on_hand)


def classify_risk_by_inventory(
    current_inventory: float,
    forecast_lead_time_demand: float,
    safety_stock: float,
) -> str:
    """Classify inventory using the same threshold as reorder calculations.

    HIGH: stock is below expected lead-time demand.
    MEDIUM: demand is covered, but the safety-stock buffer is not.
    LOW: demand and safety stock are both covered.
    """
    on_hand = _finite_number(current_inventory, "current_inventory")
    demand = _finite_number(
        forecast_lead_time_demand,
        "forecast_lead_time_demand",
    )
    buffer = _finite_number(safety_stock, "safety_stock")

    if on_hand < 0 or demand < 0 or buffer < 0:
        raise ValueError(
            "inventory, lead-time demand, and safety stock "
            "cannot be negative"
        )

    if on_hand < demand:
        return "HIGH"

    if on_hand < demand + buffer:
        return "MEDIUM"

    return "LOW"


def classify_risk_by_coverage(
    current_inventory: float,
    forecast_daily_demand: float,
    lead_time_days: int,
    safety_stock: float,
) -> str:
    """Backward-compatible wrapper accepting daily demand."""
    lead_time = _validate_lead_time(lead_time_days)
    daily_demand = _finite_number(
        forecast_daily_demand,
        "forecast_daily_demand",
    )

    if daily_demand < 0:
        raise ValueError(
            "forecast_daily_demand cannot be negative"
        )

    return classify_risk_by_inventory(
        current_inventory=current_inventory,
        forecast_lead_time_demand=daily_demand * lead_time,
        safety_stock=safety_stock,
    )
