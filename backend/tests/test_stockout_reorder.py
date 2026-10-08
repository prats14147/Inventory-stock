"""backend/tests/test_stockout_reorder.py"""

import pytest

from app.services import forecast_service, reorder_service, stockout_service
from app.services.errors import NotFoundError


def test_forecast_product_demand_shape(db):
    result = forecast_service.forecast_product_demand(db, "P0001", horizon=14)
    assert result["product_id"] == "P0001"
    assert result["model_horizon_days"] == 14
    assert len(result["per_store"]) == 5  # 5 stores in this dataset
    assert result["forecast_total_units"] >= 0
    assert abs(sum(s["forecast_units"] for s in result["per_store"]) - result["forecast_total_units"]) < 1e-3


def test_forecast_unknown_product_raises(db):
    with pytest.raises(NotFoundError):
        forecast_service.forecast_product_demand(db, "P9999")


def test_forecast_nearest_horizon_used_when_not_exactly_trained(db):
    # lead_time_days=10 is between the two trained horizons (7, 14) --
    # nearest should be picked and reported, not silently rounded.
    info = forecast_service.forecast_daily_rate_and_history_std(db, "P0001", lead_time_days=10)
    assert info["forecast_model_horizon_used"] in (7, 14)
    assert info["lead_time_days"] == 10


def test_lead_time_demand_uses_daily_forecast_units(monkeypatch):
    import pandas as pd

    forecast = {"forecast_total_units": 600.0}
    history = pd.DataFrame({
        "Product ID": ["P0001", "P0001"],
        "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "Units Sold": [100, 120],
    })
    monkeypatch.setattr(
        forecast_service,
        "forecast_product_demand",
        lambda _db, _product_id, horizon: {**forecast, "model_horizon_days": horizon},
    )
    monkeypatch.setattr(forecast_service, "get_full_history_dataframe_cached", lambda _db: history)
    info = forecast_service.forecast_daily_rate_and_history_std(None, "P0001", lead_time_days=7)

    # The model predicts one day's sales at T+7, summed across stores. It is
    # already a daily rate and must not be divided by the horizon again.
    assert info["forecast_daily_rate"] == pytest.approx(600.0)
    assert info["forecast_lead_time_demand"] == pytest.approx(4200.0)


def test_stockout_risk_formula_consistency(db):
    """required_inventory must always equal forecast_lead_time_demand + safety_stock."""
    result = stockout_service.calculate_stockout_risk(db, "P0001")
    assert result.required_inventory == pytest.approx(
        result.forecast_lead_time_demand + result.safety_stock, abs=1e-6
    )


def test_stockout_risk_tiers_are_consistent_with_thresholds(db):
    from app.repositories import product_repository

    for pid in product_repository.list_product_ids(db):
        result = stockout_service.calculate_stockout_risk(db, pid)
        if result.current_inventory < result.forecast_lead_time_demand:
            assert result.risk.value == "HIGH"
        elif result.current_inventory < result.required_inventory:
            assert result.risk.value == "MEDIUM"
        else:
            assert result.risk.value == "LOW"

    # At the default 7-day lead time every product is HIGH: on-hand cover is
    # ~2 days while lead-time demand spans 7 (the forecast is calibrated --
    # one-day product demand matches the observed daily average -- so this is
    # the honest answer, not a stuck formula). The engine must still
    # discriminate at shorter lead times, where cover exceeds demand for
    # most products.
    short_horizon_tiers = {
        stockout_service.calculate_stockout_risk(db, pid, lead_time_days=1).risk.value
        for pid in product_repository.list_product_ids(db)
    }
    assert len(short_horizon_tiers) > 1


def test_stockout_risk_unknown_product_raises(db):
    with pytest.raises(NotFoundError):
        stockout_service.calculate_stockout_risk(db, "P9999")


def test_reorder_formula_never_negative(db):
    from app.repositories import product_repository

    for pid in product_repository.list_product_ids(db):
        result = reorder_service.calculate_reorder(db, pid)
        assert result.recommended_reorder_quantity >= 0


def test_reorder_matches_manual_formula(db):
    result = reorder_service.calculate_reorder(db, "P0007")  # known HIGH-risk product
    expected = max(
        0.0,
        result.forecast_lead_time_demand + result.safety_stock - result.current_inventory,
    )
    assert result.recommended_reorder_quantity == pytest.approx(expected, abs=1e-6)
    assert result.recommended_reorder_quantity > 0  # P0007 is under-stocked


def test_reorder_unknown_product_raises(db):
    with pytest.raises(NotFoundError):
        reorder_service.calculate_reorder(db, "P9999")


def test_reorder_assumptions_are_disclosed(db):
    result = reorder_service.calculate_reorder(db, "P0001")
    assert "lead_time_days" in result.assumptions
    assert "safety_stock_service_factor" in result.assumptions
    assert "no real supplier lead time" in result.assumptions["lead_time_source"]
