"""
backend/app/routers/live.py

Real-time API surface (Tier 1):

  * GET  /api/live/ws                       -- WebSocket stream (events + alerts)
  * GET  /api/live/events                   -- recent live sales events
  * GET  /api/live/alerts                   -- proactive alerts (open/acknowledged)
  * POST /api/live/alerts/{id}/acknowledge  -- mark an alert handled
  * GET  /api/live/summary                  -- one-shot numbers for the dashboard
  * GET  /api/simulator/status              -- is the demo simulator running?
  * POST /api/simulator/start|stop|tick     -- control it

The WebSocket sends a short backlog on connect (so a dashboard opened mid-demo
is not blank), then forwards everything the hub publishes. REST remains the
fallback transport: the frontend polls /api/live/summary if the socket drops.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.repositories import realtime_repository
from app.services import simulator_service
from app.services.live_hub import get_live_hub
from app.security import require_websocket_identity

router = APIRouter(tags=["live"])
log = logging.getLogger("live")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- REST: live data --------------------------------------------------------

@router.get("/api/live/events")
def list_live_events(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    events = realtime_repository.get_recent_events(db, limit)
    return {"count": len(events), "events": [event.to_dict() for event in events]}


@router.get("/api/live/alerts")
def list_alerts(
    acknowledged: Optional[bool] = Query(None, description="Filter by handled state"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    alerts = realtime_repository.get_alerts(db, acknowledged, limit)
    return {"count": len(alerts), "alerts": [alert.to_dict() for alert in alerts]}


@router.post("/api/live/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)) -> dict:
    alert = realtime_repository.acknowledge_alert(db, alert_id, _utcnow())
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    payload = alert.to_dict()
    # Let every open dashboard drop it from the list immediately.
    get_live_hub().publish({"type": "alert_acknowledged", "id": alert.id, "product_id": alert.product_id})
    return payload


@router.get("/api/live/summary")
def live_summary(db: Session = Depends(get_db)) -> dict:
    """Numbers for the live dashboard header (also the polling fallback)."""
    settings = get_settings()
    return {
        "simulator": simulator_service.get_simulator_service().status(),
        "live_events": realtime_repository.count_events(db),
        "live_units_sold": realtime_repository.total_live_units(db),
        "open_alerts": realtime_repository.count_open_alerts(db),
        "critical_alerts": realtime_repository.count_open_alerts(db, simulator_service.CRITICAL),
        "hub": get_live_hub().stats(),
        "alert_cooldown_seconds": settings.simulator_alert_cooldown_seconds,
    }

@router.get("/api/live/digest")
def alert_digest(
    date: Optional[str] = Query(None, description="UTC day to summarise, as YYYY-MM-DD. Defaults to today."),
    db: Session = Depends(get_db),
) -> dict:
    """Everything that fired on one UTC day, rolled up for a morning read.

    A digest, not a new alert store: it is a pure read over `stockout_alerts`
    bucketed by day, so it cannot drift from the alerts themselves.
    """
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date() if date else _utcnow().date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    alerts = realtime_repository.get_alerts_between(db, start, end)

    critical = [a for a in alerts if a.severity == "CRITICAL"]
    open_alerts = [a for a in alerts if not a.acknowledged]

    # One row per product: how often it fired, and whether it is still open.
    by_product: dict[str, dict] = {}
    for alert in alerts:
        created = alert.created_at.isoformat()
        row = by_product.setdefault(
            alert.product_id,
            {
                "product_id": alert.product_id,
                "alert_count": 0,
                "open_count": 0,
                "worst_severity": "WARNING",
                "first_alert_at": created,
                "last_alert_at": created,
                "projected_inventory": alert.projected_inventory,
                "required_inventory": alert.required_inventory,
                "message": alert.message,
            },
        )
        row["alert_count"] += 1
        if not alert.acknowledged:
            row["open_count"] += 1
        if alert.severity == "CRITICAL":
            row["worst_severity"] = "CRITICAL"
            row["message"] = alert.message
        if created < row["first_alert_at"]:
            row["first_alert_at"] = created

    products = sorted(
        by_product.values(),
        key=lambda r: (r["worst_severity"] != "CRITICAL", -r["open_count"], -r["alert_count"]),
    )

    return {
        "date": day.isoformat(),
        "total_alerts": len(alerts),
        "critical_alerts": len(critical),
        "warning_alerts": len(alerts) - len(critical),
        "open_alerts": len(open_alerts),
        "acknowledged_alerts": len(alerts) - len(open_alerts),
        "products_affected": len(products),
        "products": products,
    }




# --- REST: simulator control ------------------------------------------------

@router.get("/api/simulator/status")
def simulator_status() -> dict:
    return simulator_service.get_simulator_service().status()


@router.post("/api/simulator/start")
async def simulator_start(
    tick_seconds: Optional[float] = Query(None, gt=0.1, le=3600),
    events_per_tick: Optional[int] = Query(None, ge=1, le=50),
) -> dict:
    service = simulator_service.get_simulator_service()
    if events_per_tick is not None:
        service.settings.simulator_events_per_tick = events_per_tick
    # async endpoint: the background task must be created on the serving loop.
    started = service.start(asyncio.get_running_loop(), tick_seconds)
    return {"started": started, **service.status()}


@router.post("/api/simulator/stop")
async def simulator_stop() -> dict:
    service = simulator_service.get_simulator_service()
    stopped = service.stop()
    return {"stopped": stopped, **service.status()}


@router.post("/api/simulator/tick")
def simulator_tick(
    events: Optional[int] = Query(None, ge=1, le=50, description="Events for this single tick"),
) -> dict:
    """Run exactly one tick -- deterministic and instant, so demos and tests
    never have to wait on a timer."""
    service = simulator_service.get_simulator_service()
    tick = service.tick(events_per_tick=events, trigger="manual")
    return tick.as_dict()


# --- WebSocket: live stream -------------------------------------------------

@router.websocket("/api/live/ws")
async def live_ws(
    websocket: WebSocket,
    backlog: int = Query(10, ge=0, le=100),
) -> None:
    """Stream live sales events and alerts as they happen."""
    if require_websocket_identity(websocket) is None:
        await websocket.close(code=1008, reason="Sign-in required")
        return
    await websocket.accept(subprotocol="inventoryai")
    hub = get_live_hub()

    async with hub.subscribe() as queue:
        await websocket.send_json(
            {"type": "connected", "subscribers": hub.subscriber_count, "backlog_size": backlog}
        )

        if backlog:
            # A dashboard opened mid-demo should show recent context instead
            # of an empty panel until the next tick.
            await _send_backlog(websocket, backlog)

        await websocket.send_json({"type": "ready"})

        ping_task = asyncio.create_task(_keepalive(websocket))
        try:
            while True:
                frame = await queue.get()
                await websocket.send_json(frame)
        except WebSocketDisconnect:
            log.info("Live dashboard disconnected")
        except Exception:  # noqa: BLE001
            log.exception("Live stream failed")
        finally:
            ping_task.cancel()


async def _send_backlog(websocket: WebSocket, backlog: int) -> None:
    """Best-effort replay of recent events/alerts on connect."""
    db: Session = SessionLocal()
    try:
        for event in realtime_repository.get_recent_events(db, backlog):
            await websocket.send_json({"type": "sales_event", **event.to_dict()})
        for alert in realtime_repository.get_alerts(db, acknowledged=False, limit=backlog):
            await websocket.send_json({"type": "alert", **alert.to_dict()})
    except Exception:  # noqa: BLE001
        log.exception("Failed to send live backlog")
    finally:
        db.close()


async def _keepalive(websocket: WebSocket, interval: float = 25.0) -> None:
    """Idle sockets through proxies/load balancers that time out quiet ones."""
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json({"type": "ping"})
    except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
        pass

