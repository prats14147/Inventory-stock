"""
backend/tests/test_realtime.py

Tests for the Tier 1 real-time layer: the demo data simulator, the proactive
stockout alert engine, the live hub, and the live REST/WebSocket endpoints.

Everything runs against the real Postgres database (like the other API tests)
and cleans up the rows it creates, so the suite can be run repeatedly without
the live tables drifting.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import LiveSalesEvent, StockoutAlert
from app.services import simulator_service
from app.services.live_hub import LiveEventHub, set_live_hub
from app.services.simulator_service import (
    CRITICAL,
    SimulatorService,
    evaluate_product_alert,
    live_units_sold,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RecordingHub(LiveEventHub):
    """Hub that keeps every published frame for assertions."""

    def __init__(self):
        super().__init__()
        self.frames: list[dict] = []

    def publish(self, frame: dict) -> None:
        self.frames.append(frame)
        super().publish(frame)


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def realtime_db(db):
    """Rollback-scoped session plus max-id cleanup for the simulator's own writes.

    The `db` fixture (conftest) rolls back everything written through the
    test session. But SimulatorService.ticks write through their own
    SessionLocal session on a separate connection, so those commits are NOT
    covered by the rollback -- the max-id DELETE below removes exactly the
    rows a test's ticks created, restoring the live tables for the next test.
    """
    event_max = db.execute(select(func.coalesce(func.max(LiveSalesEvent.id), 0))).scalar_one()
    alert_max = db.execute(select(func.coalesce(func.max(StockoutAlert.id), 0))).scalar_one()
    yield db
    db.rollback()  # release any uncommitted state before the cleanup DELETEs
    db.execute(LiveSalesEvent.__table__.delete().where(LiveSalesEvent.id > event_max))
    db.execute(StockoutAlert.__table__.delete().where(StockoutAlert.id > alert_max))
    db.commit()


@pytest.fixture
def service(realtime_db):
    """Simulator service with a seeded RNG (deterministic event sampling).

    The recording hub is also installed as the process-global hub, so the
    simulator, the REST endpoints (`/api/live/summary`) and the WebSocket
    subscribers all talk to the same object -- exactly as in production.
    """
    recorder = RecordingHub()
    set_live_hub(recorder)
    svc = SimulatorService(hub=recorder, rng=random.Random(1234))
    simulator_service.set_simulator_service(svc)
    yield svc
    svc.stop()
    simulator_service.set_simulator_service(None)
    set_live_hub(None)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# --- Simulator + alert engine ----------------------------------------------

def test_tick_persists_events_and_publishes_frames(service, realtime_db):
    tick = service.tick(events_per_tick=3)

    assert len(tick.events) == 3
    stored = realtime_db.execute(
        select(func.count()).select_from(LiveSalesEvent)
    ).scalar_one()
    assert stored >= 3

    sales_frames = [f for f in service.hub.frames if f["type"] == "sales_event"]
    assert len(sales_frames) == 3
    assert {f["product_id"] for f in sales_frames}  # real products, from the DB
    assert all(f["units_sold"] >= 0 for f in sales_frames)


def test_tick_never_touches_the_analytical_tables(service, realtime_db):
    """The whole point of the separate table: history stays reproducible."""
    from app.models import DailySales

    before = realtime_db.execute(select(func.count()).select_from(DailySales)).scalar_one()
    service.tick(events_per_tick=4)
    after = realtime_db.execute(select(func.count()).select_from(DailySales)).scalar_one()
    assert after == before


def test_live_units_sold_sums_only_that_product(service, realtime_db):
    # The simulator commits through its own session outside the db-fixture
    # rollback, so earlier tests may have left rows behind. Snapshot the
    # per-product totals BEFORE the tick; the tick's contribution is the delta.
    realtime_db.expire_all()
    all_pids = [f"P{i:04d}" for i in range(1, 21)]
    baseline = {pid: live_units_sold(realtime_db, pid) for pid in all_pids}
    tick = service.tick(events_per_tick=5)
    realtime_db.expire_all()
    for product_id in {e["product_id"] for e in tick.events}:
        expected = sum(e["units_sold"] for e in tick.events if e["product_id"] == product_id)
        assert live_units_sold(realtime_db, product_id) - baseline[product_id] == expected


def test_alert_escalates_to_critical_and_is_verified(realtime_db):
    """A drain far larger than the recorded stock must raise CRITICAL, with
    every number in the message traceable to a query or the risk formula."""
    # Unique product: the simulator commits through its own session outside the
    # db-fixture rollback, so earlier tests may have left CRITICAL alerts for
    # P0001 behind -- and the cooldown would suppress this one as a duplicate.
    product_id = "P0003"
    realtime_db.add(
        LiveSalesEvent(
            event_time=_utcnow(),
            store_id="S001",
            product_id=product_id,
            units_sold=999_999,
            unit_price=10.0,
            source="test",
        )
    )
    realtime_db.commit()

    alert, reason = evaluate_product_alert(
        realtime_db, product_id, now=_utcnow(), cooldown_seconds=120, trigger="test"
    )

    assert reason is None
    assert alert is not None
    assert alert.severity == CRITICAL
    assert alert.projected_inventory == pytest.approx(
        alert.current_inventory - alert.live_units_sold
    )
    assert alert.projected_inventory < alert.forecast_lead_time_demand
    assert product_id in alert.message
    assert f"{alert.projected_inventory:.0f}" in alert.message
    assert alert.acknowledged is False


def test_repeat_alert_within_cooldown_is_suppressed(realtime_db):
    product_id = "P0002"
    realtime_db.add(
        LiveSalesEvent(
            event_time=_utcnow(),
            store_id="S001",
            product_id=product_id,
            units_sold=999_999,
            unit_price=10.0,
            source="test",
        )
    )
    realtime_db.commit()

    now = _utcnow()
    first, _ = evaluate_product_alert(realtime_db, product_id, now=now, cooldown_seconds=120, trigger="test")
    second, reason = evaluate_product_alert(realtime_db, product_id, now=now, cooldown_seconds=120, trigger="test")

    assert first is not None
    assert second is None
    assert reason == "suppressed"

    # Past the cooldown the alert is allowed through again (it is still open
    # and still worsening -- a dashboard should be re-notified).
    third, reason3 = evaluate_product_alert(
        realtime_db, product_id, now=now + timedelta(seconds=121), cooldown_seconds=120, trigger="test"
    )
    assert third is not None
    assert reason3 is None


# --- Live hub fan-out -------------------------------------------------------

def test_hub_fans_out_to_every_subscriber():
    async def scenario():
        hub = LiveEventHub()
        async with hub.subscribe() as first, hub.subscribe() as second:
            frame = {"type": "sales_event", "product_id": "P0001"}
            hub.publish(frame)
            assert await first.get() == frame
            assert await second.get() == frame
        assert hub.subscriber_count == 0

    anyio.run(scenario)


def test_hub_drops_oldest_frame_for_slow_subscriber():
    """A slow consumer must never stall the producer or grow memory."""

    async def scenario():
        hub = LiveEventHub(max_buffer=1)
        async with hub.subscribe() as queue:
            hub.publish({"type": "sales_event", "id": 1})
            hub.publish({"type": "sales_event", "id": 2})
            assert queue.qsize() == 1
            assert (await queue.get())["id"] == 2  # newest wins

    anyio.run(scenario)


def test_hub_delivers_frames_published_from_a_worker_thread():
    """The simulator ticks in a worker thread and the REST endpoints run in a
    threadpool -- those frames must still reach a waiting subscriber (this is
    the bug that would leave the live dashboard frozen)."""

    async def scenario():
        hub = LiveEventHub()
        async with hub.subscribe() as queue:
            await anyio.to_thread.run_sync(hub.publish, {"type": "sales_event", "id": 7})
            frame = await queue.get()
            assert frame["id"] == 7

    anyio.run(scenario)


# --- REST endpoints ---------------------------------------------------------

def test_simulator_tick_endpoint_creates_events(client, service):
    r = client.post("/api/simulator/tick?events=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body["events"]) == 2
    assert "tick_at" in body

    listed = client.get("/api/live/events?limit=5").json()
    assert listed["count"] >= 2


def test_live_summary_endpoint(client, service):
    client.post("/api/simulator/tick?events=3")
    body = client.get("/api/live/summary").json()

    assert body["live_events"] >= 3
    assert body["live_units_sold"] >= 0
    assert body["open_alerts"] >= body["critical_alerts"]
    assert body["hub"]["frames_published"] >= 3


def test_simulator_status_and_start_stop(client, service):
    assert client.get("/api/simulator/status").json()["running"] is False

    started = client.post("/api/simulator/start?tick_seconds=3600").json()
    assert started["started"] is True
    assert started["running"] is True

    # Idempotent: a second start reports that it was already running.
    assert client.post("/api/simulator/start").json()["started"] is False

    stopped = client.post("/api/simulator/stop").json()
    assert stopped["stopped"] is True
    assert stopped["running"] is False


def test_alerts_endpoint_and_acknowledgement(client, service, realtime_db):
    realtime_db.add(
        LiveSalesEvent(
            event_time=_utcnow(),
            store_id="S001",
            product_id="P0003",
            units_sold=999_999,
            unit_price=10.0,
            source="test",
        )
    )
    realtime_db.commit()
    client.post("/api/simulator/tick?events=1")

    alerts = client.get("/api/live/alerts?acknowledged=false").json()["alerts"]
    assert alerts, "expected the drained product to have raised an alert"
    alert_id = alerts[0]["id"]

    acked = client.post(f"/api/live/alerts/{alert_id}/acknowledge")
    assert acked.status_code == 200
    assert acked.json()["acknowledged"] is True
    assert acked.json()["acknowledged_at"] is not None

    # Acknowledging is idempotent, and an unknown id is a clean 404.
    assert client.post(f"/api/live/alerts/{alert_id}/acknowledge").status_code == 200
    assert client.post("/api/live/alerts/99999999/acknowledge").status_code == 404

    open_alerts = client.get("/api/live/alerts?acknowledged=false").json()["alerts"]
    assert all(a["id"] != alert_id for a in open_alerts)


def test_live_ws_replays_backlog_then_signals_ready(client, service):
    client.post("/api/simulator/tick?events=3")

    with client.websocket_connect("/api/live/ws?backlog=5") as ws:
        first = ws.receive_json()
        assert first["type"] == "connected"
        assert first["subscribers"] >= 1

        frames = []
        while True:
            frame = ws.receive_json()
            if frame["type"] == "ready":
                break
            frames.append(frame)

    assert any(f["type"] == "sales_event" for f in frames)
    assert all(f["product_id"] for f in frames if f["type"] == "sales_event")


def test_live_ws_without_backlog_goes_straight_to_ready(client, service):
    with client.websocket_connect("/api/live/ws?backlog=0") as ws:
        assert ws.receive_json()["type"] == "connected"
        assert ws.receive_json()["type"] == "ready"


