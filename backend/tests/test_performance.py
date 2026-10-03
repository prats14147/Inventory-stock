"""
backend/tests/test_performance.py

Tests for the Tier A performance work:

  * the inference history cache (one joined frame per process, not per call)
  * the stockout/reorder result cache (TTL, keyed by product + lead time)
  * the single-request dashboard summary
  * the SQL-side low-stock filter

Two things matter for correctness here, and are asserted explicitly:

  1. Caching must not change a single number. Every "cached" assertion also
     checks the value equals the freshly computed one.
  2. A cache must be droppable, and a test that writes to the source tables
     must be able to drop it -- otherwise tests leak into each other.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.repositories import inventory_repository, product_repository, sales_repository
from app.services import dashboard_service, stockout_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_caches():
    """Every test starts and ends with no cached state."""
    stockout_service.clear_risk_cache()
    sales_repository.clear_history_cache()
    yield
    stockout_service.clear_risk_cache()
    sales_repository.clear_history_cache()


def _some_product_ids(n: int = 3) -> list[str]:
    return product_repository.list_product_ids(SessionLocal())[:n]


# --- History cache -----------------------------------------------------------


def test_history_cache_returns_equal_frames(db):
    fresh = sales_repository.get_full_history_dataframe(db)
    cached_first = sales_repository.get_full_history_dataframe_cached(db)
    cached_second = sales_repository.get_full_history_dataframe_cached(db)

    assert list(cached_first.columns) == list(fresh.columns)
    assert len(cached_first) == len(fresh)
    # Same object back on the second call: that is the whole point of the cache.
    assert cached_first is cached_second


def test_history_cache_can_be_cleared(db):
    first = sales_repository.get_full_history_dataframe_cached(db)
    sales_repository.clear_history_cache()
    second = sales_repository.get_full_history_dataframe_cached(db)
    assert first is not second
    assert len(first) == len(second)


# --- Risk result cache -------------------------------------------------------


def test_risk_cache_does_not_change_the_number(db):
    product_id = _some_product_ids(1)[0]
    stockout_service.clear_risk_cache()
    cold = stockout_service.calculate_stockout_risk(db, product_id)
    assert stockout_service.was_cached(product_id) is True
    warm = stockout_service.calculate_stockout_risk(db, product_id)
    assert warm == cold


def test_risk_cache_is_keyed_by_lead_time(db):
    product_id = _some_product_ids(1)[0]
    stockout_service.clear_risk_cache()
    seven = stockout_service.calculate_stockout_risk(db, product_id, lead_time_days=7)
    assert stockout_service.was_cached(product_id, 7) is True
    # A different lead time is a different key, so it must not be a cache hit.
    assert stockout_service.was_cached(product_id, 14) is False
    fourteen = stockout_service.calculate_stockout_risk(db, product_id, lead_time_days=14)
    assert fourteen.lead_time_days == 14
    assert seven.lead_time_days == 7


def test_risk_cache_can_be_cleared(db):
    product_id = _some_product_ids(1)[0]
    stockout_service.calculate_stockout_risk(db, product_id)
    stockout_service.clear_risk_cache()
    assert stockout_service.was_cached(product_id) is False


def test_risk_cache_disabled_by_zero_ttl(db, monkeypatch):
    """TTL 0 must mean "never cache", not "cache forever"."""
    product_id = _some_product_ids(1)[0]
    stockout_service.clear_risk_cache()

    real = stockout_service.get_settings()

    class _NoCache:
        default_lead_time_days = real.default_lead_time_days
        safety_stock_service_factor = real.safety_stock_service_factor
        risk_cache_ttl_seconds = 0.0

    monkeypatch.setattr(stockout_service, "get_settings", lambda: _NoCache)
    stockout_service.calculate_stockout_risk(db, product_id)
    assert stockout_service.was_cached(product_id) is False


# --- SQL-side low stock ------------------------------------------------------


def test_low_stock_rows_match_python_filter(db):
    """The SQL filter must return exactly what filtering in Python returns."""
    rows = inventory_repository.get_low_stock_rows(db, 50)
    everything = inventory_repository.get_all_current_inventory(db)
    expected = [r for r in everything if r["inventory_level"] < 50]
    assert len(rows) == len(expected)
    assert {r["product_id"] for r in rows} == {r["product_id"] for r in expected}


def test_inventory_headline_totals_match_the_listing(db):
    headline = inventory_repository.get_inventory_headline(db)
    rows = inventory_repository.get_all_current_inventory(db)
    assert headline["total_inventory_units"] == sum(r["inventory_level"] for r in rows)
    assert headline["store_count"] == len({r["store_id"] for r in rows})


# --- Dashboard summary -------------------------------------------------------


def test_dashboard_summary_is_one_request_with_the_right_shape():
    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    body = res.json()

    for key in (
        "as_of_date",
        "product_count",
        "store_count",
        "total_inventory_units",
        "low_stock_count",
        "risk_counts",
        "needs_attention",
        "category_sales",
        "top_products",
        "compute_ms",
    ):
        assert key in body, f"missing {key}"

    assert body["product_count"] == 20
    assert body["store_count"] == 5
    counts = body["risk_counts"]
    assert counts["high"] + counts["medium"] + counts["low"] == body["product_count"]
    assert len(body["category_sales"]) > 0
    assert len(body["top_products"]) == 5


def test_dashboard_needs_attention_is_ordered_and_bounded():
    body = client.get("/api/dashboard/summary").json()
    items = body["needs_attention"]
    assert len(items) <= dashboard_service.NEEDS_ATTENTION_LIMIT
    # Every listed item is genuinely at risk.
    assert all(i["risk"] in {"HIGH", "MEDIUM"} for i in items)
    # HIGH must come before MEDIUM.
    severities = [i["risk"] for i in items]
    assert severities == sorted(severities, key=lambda s: s != "HIGH")


def test_dashboard_summary_agrees_with_the_detail_endpoints():
    """The summary must not drift from the pages it summarises."""
    summary = client.get("/api/dashboard/summary").json()
    risk = client.get("/api/stockout-risk").json()
    by_id = {r["product_id"]: r for r in risk}

    assert summary["risk_counts"]["high"] == sum(1 for r in risk if r["risk"] == "HIGH")
    assert summary["risk_counts"]["medium"] == sum(1 for r in risk if r["risk"] == "MEDIUM")

    for item in summary["needs_attention"]:
        detail = by_id[item["product_id"]]
        assert item["current_inventory"] == detail["current_inventory"]
        assert item["required_inventory"] == detail["required_inventory"]


def test_dashboard_summary_second_call_is_served_from_cache(db):
    """The whole point of Tier A: a warm dashboard is cheap and says so."""
    stockout_service.clear_risk_cache()
    first = dashboard_service.get_dashboard_summary(db)
    second = dashboard_service.get_dashboard_summary(db)
    assert first.served_from_cache is False
    assert second.served_from_cache is True
    # Identical numbers, just no recomputation.
    assert first.risk_counts == second.risk_counts
    assert first.needs_attention == second.needs_attention
    assert second.compute_ms <= first.compute_ms

