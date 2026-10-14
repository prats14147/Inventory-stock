"""Unit tests for the shared inventory risk policy (no database required)."""
import math

import pytest

from app.services.inventory_risk_policy import calculate_safety_stock, classify_risk_by_coverage


def test_safety_stock_increases_with_lead_time_sqrt_rule():
    daily_std = 10.0
    factor = 1.65
    seven_day = calculate_safety_stock(daily_std, factor, 7)
    fourteen_day = calculate_safety_stock(daily_std, factor, 14)

    assert seven_day == pytest.approx(factor * daily_std * math.sqrt(7))
    assert fourteen_day == pytest.approx(factor * daily_std * math.sqrt(14))
    assert fourteen_day > seven_day
    assert fourteen_day / seven_day == pytest.approx(math.sqrt(2))


def test_risk_categories_follow_days_of_coverage():
    # Daily demand=10; lead time=7 days; safety buffer=20 units (2 days).
    assert classify_risk_by_coverage(60, 10, 7, 20) == "HIGH"  # 6 days cover
    assert classify_risk_by_coverage(75, 10, 7, 20) == "MEDIUM"  # 7.5 days cover
    assert classify_risk_by_coverage(90, 10, 7, 20) == "LOW"  # 9 days cover


def test_zero_forecast_demand_does_not_divide_by_zero():
    assert classify_risk_by_coverage(10, 0, 7, 20) == "MEDIUM"
    assert classify_risk_by_coverage(25, 0, 7, 20) == "LOW"


def test_policy_rejects_invalid_lead_time():
    with pytest.raises(ValueError, match="at least 1"):
        calculate_safety_stock(10, 1.65, 0)

# 

def test_risk_and_reorder_share_the_same_thresholds():
    from app.services.inventory_risk_policy import (
        calculate_reorder_quantity,
        classify_risk_by_inventory,
    )

    demand = 70.0
    buffer = 20.0

    assert classify_risk_by_inventory(69, demand, buffer) == "HIGH"
    assert classify_risk_by_inventory(70, demand, buffer) == "MEDIUM"
    assert classify_risk_by_inventory(89.99, demand, buffer) == "MEDIUM"
    assert classify_risk_by_inventory(90, demand, buffer) == "LOW"

    assert calculate_reorder_quantity(69, demand, buffer) == pytest.approx(21.0)
    assert calculate_reorder_quantity(70, demand, buffer) == pytest.approx(20.0)
    assert calculate_reorder_quantity(90, demand, buffer) == pytest.approx(0.0)


def test_invalid_non_finite_values_are_rejected():
    with pytest.raises(ValueError, match="finite number"):
        calculate_safety_stock(float("nan"), 1.65, 7)

    with pytest.raises(ValueError, match="finite number"):
        calculate_safety_stock(10, float("inf"), 7)


def test_negative_std_or_service_factor_is_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_safety_stock(-1, 1.65, 7)

    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_safety_stock(10, -1, 7)


def test_lead_time_must_be_positive_integer():
    with pytest.raises(ValueError, match="positive integer"):
        calculate_safety_stock(10, 1.65, 1.5)

    with pytest.raises(ValueError, match="positive integer"):
        calculate_safety_stock(10, 1.65, True)
