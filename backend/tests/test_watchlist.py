"""
backend/tests/test_watchlist.py

Tests for the Tier C watchlist (pinned products) and the daily alert digest.

Runs against the real Postgres database like the other API tests. Watchlist
rows are removed afterwards; digest rows are inserted with a timestamp far in
the past so they can never collide with alerts the simulator creates live.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import StockoutAlert, WatchlistItem

client = TestClient(app)

# A day far enough in the past that no live alert can land there.
DIGEST_DAY = "2020-03-17"
_DIGEST_NOON = datetime(2020, 3, 17, 12, 0, 0)


@pytest.fixture
def clean_watchlist():
    """Empty the watchlist before and after the test."""
    session = SessionLocal()
    session.query(WatchlistItem).delete()
    session.commit()
    session.close()
    yield
    session = SessionLocal()
    session.query(WatchlistItem).delete()
    session.commit()
    session.close()


@pytest.fixture
def digest_alerts():
    """Four alerts on DIGEST_DAY, then removed."""
    session = SessionLocal()
    for i, (product_id, severity, acknowledged) in enumerate(
        [
            ("P0001", "CRITICAL", False),
            ("P0001", "WARNING", True),
            ("P0002", "CRITICAL", False),
            ("P0003", "WARNING", False),
        ]
    ):
        session.add(
            StockoutAlert(
                created_at=_DIGEST_NOON + timedelta(minutes=i),
                product_id=product_id,
                severity=severity,
                kind="STOCKOUT_RISK",
                message=f"test alert {i} for {product_id}",
                current_inventory=10.0,
                live_units_sold=5.0,
                projected_inventory=5.0,
                forecast_lead_time_demand=40.0,
                required_inventory=50.0,
                lead_time_days=7,
                acknowledged=acknowledged,
                acknowledged_at=_DIGEST_NOON if acknowledged else None,
                trigger="test",
            )
        )
    session.commit()
    yield
    session.query(StockoutAlert).filter(StockoutAlert.trigger == "test").delete(
        synchronize_session=False
    )
    session.commit()
    session.close()


def _some_product_id() -> str:
    res = client.get("/api/products")
    assert res.status_code == 200
    product_ids = res.json()["product_ids"]
    assert product_ids, "dataset should have products"
    return product_ids[0]


# --- Watchlist ---------------------------------------------------------------


def test_watchlist_starts_empty(clean_watchlist):
    res = client.get("/api/watchlist")
    assert res.status_code == 200
    assert res.json() == {"entries": [], "count": 0}


def test_pin_then_unpin_roundtrip(clean_watchlist):
    product_id = _some_product_id()

    res = client.post(f"/api/watchlist/{product_id}", json={"note": "holiday promo"})
    assert res.status_code == 201
    body = res.json()
    assert body["product_id"] == product_id
    assert body["note"] == "holiday promo"
    # Live figures are computed on read, not stored on the pin.
    assert body["current_inventory"] is not None
    assert body["risk"] in {"LOW", "MEDIUM", "HIGH"}

    ids = client.get("/api/watchlist/ids")
    assert ids.status_code == 200
    assert product_id in ids.json()["product_ids"]

    assert client.get("/api/watchlist").json()["count"] == 1

    unpin = client.delete(f"/api/watchlist/{product_id}")
    assert unpin.status_code == 200
    assert client.get("/api/watchlist").json()["count"] == 0


def test_pinning_twice_is_idempotent(clean_watchlist):
    product_id = _some_product_id()
    first = client.post(f"/api/watchlist/{product_id}", json={"note": "first"})
    second = client.post(f"/api/watchlist/{product_id}", json={"note": "second"})
    assert first.status_code == 201
    assert second.status_code == 201
    # The original pin and its note survive a second pin.
    assert second.json()["pinned_at"] == first.json()["pinned_at"]
    assert second.json()["note"] == "first"
    assert client.get("/api/watchlist").json()["count"] == 1


def test_pin_unknown_product_is_404(clean_watchlist):
    res = client.post("/api/watchlist/NOT-A-PRODUCT", json={})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_unpin_unknown_is_404(clean_watchlist):
    assert client.delete("/api/watchlist/NOT-A-PRODUCT").status_code == 404


def test_note_can_be_edited_and_cleared(clean_watchlist):
    product_id = _some_product_id()
    client.post(f"/api/watchlist/{product_id}", json={})

    updated = client.patch(f"/api/watchlist/{product_id}", json={"note": "supplier delayed"})
    assert updated.status_code == 200
    assert updated.json()["note"] == "supplier delayed"

    cleared = client.patch(f"/api/watchlist/{product_id}", json={"note": None})
    assert cleared.status_code == 200
    assert cleared.json()["note"] is None


def test_note_on_unpinned_product_is_404(clean_watchlist):
    res = client.patch(f"/api/watchlist/{_some_product_id()}", json={"note": "nope"})
    assert res.status_code == 404


def test_watchlist_ids_route_is_not_shadowed(clean_watchlist):
    """`/ids` is a static path that sits next to `/{product_id}`."""
    res = client.get("/api/watchlist/ids")
    assert res.status_code == 200
    assert res.json() == {"count": 0, "product_ids": []}



# --- Alert digest ------------------------------------------------------------


def test_digest_counts_and_rollup(digest_alerts):
    res = client.get(f"/api/live/digest?date={DIGEST_DAY}")
    assert res.status_code == 200
    body = res.json()

    assert body["date"] == DIGEST_DAY
    assert body["total_alerts"] == 4
    assert body["critical_alerts"] == 2
    assert body["warning_alerts"] == 2
    assert body["open_alerts"] == 3
    assert body["acknowledged_alerts"] == 1
    assert body["products_affected"] == 3

    by_id = {p["product_id"]: p for p in body["products"]}
    assert set(by_id) == {"P0001", "P0002", "P0003"}

    # One row per product, counting its alerts and its still-open ones.
    assert by_id["P0001"]["alert_count"] == 2
    assert by_id["P0001"]["open_count"] == 1
    # Worst severity wins for a product that fired both.
    assert by_id["P0001"]["worst_severity"] == "CRITICAL"
    assert by_id["P0003"]["open_count"] == 1
    assert by_id["P0003"]["worst_severity"] == "WARNING"


def test_digest_sorts_critical_first(digest_alerts):
    body = client.get(f"/api/live/digest?date={DIGEST_DAY}").json()
    severities = [p["worst_severity"] for p in body["products"]]
    # No WARNING row may appear before a CRITICAL one.
    assert severities == sorted(severities, key=lambda s: s != "CRITICAL")


def test_digest_for_quiet_day_is_empty():
    res = client.get("/api/live/digest?date=2019-01-01")
    assert res.status_code == 200
    body = res.json()
    assert body["total_alerts"] == 0
    assert body["products"] == []


def test_digest_rejects_bad_date():
    assert client.get("/api/live/digest?date=not-a-date").status_code == 400


def test_digest_defaults_to_today():
    res = client.get("/api/live/digest")
    assert res.status_code == 200
    # YYYY-MM-DD and a real date -- it must not echo the query param.
    assert len(res.json()["date"]) == 10

