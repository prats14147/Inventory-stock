"""
backend/app/services/simulator_service.py

Demo data simulator + proactive stockout alerting (Tier 1).

WHAT IT DOES
  tick():
    1. Generates a few synthetic point-of-sale events, sampled from the real
       (store, product) demand profile in Postgres -- so the live numbers
       move the way this dataset actually moves instead of looking random.
    2. Writes them to `live_sales_events` and publishes them on the live hub.
    3. Re-evaluates stockout risk for the products that just sold, using the
       SAME documentation-backed formula as the REST endpoint
       (app/services/stockout_service.py), adjusted for live drawdown --
       and raises a proactive alert when risk crosses a threshold.

WHY IT CANNOT CORRUPT THE ANALYTICS
  It never writes to `daily_sales` or `daily_inventory`. Historical analytics,
  ML features, and forecasting keep reading the untouched source of truth
  (spec section 14); live events live beside it, in their own table.

NO-HALLUCINATION NOTE
  Every number in an alert message (and in its stored fields) comes straight
  from a query or the documented risk formula. The LLM is never involved in
  deciding that an alert exists or what it says.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Optional

import anyio
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import DailySales, LiveSalesEvent, StockoutAlert
from app.services import stockout_service
from app.services.live_hub import LiveEventHub, get_live_hub

log = logging.getLogger("simulator")

CRITICAL = "CRITICAL"
WARNING = "WARNING"
# How many recent historical rows define a (store, product)'s demand profile.
PROFILE_WINDOW_DAYS = 21


def _utcnow() -> datetime:
    """Naive UTC, matching the DateTime columns (no deprecation warning)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class SimulationTick:
    """Everything one tick produced, in a JSON-ready shape."""

    tick_at: datetime
    events: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    suppressed_alerts: int = 0

    def as_dict(self) -> dict:
        return {
            "tick_at": self.tick_at.isoformat(),
            "events": self.events,
            "alerts": self.alerts,
            "suppressed_alerts": self.suppressed_alerts,
        }


# --- Event generation -------------------------------------------------------

def _demand_profile(db: Session, store_id: str, product_id: str) -> tuple[float, float, float]:
    """(mean units/day, std-dev, latest price) from real historical rows."""
    stmt = (
        select(DailySales.units_sold, DailySales.price)
        .where(DailySales.store_id == store_id, DailySales.product_id == product_id)
        .order_by(DailySales.date.desc())
        .limit(PROFILE_WINDOW_DAYS)
    )
    rows = db.execute(stmt).all()
    if not rows:
        return 0.0, 0.0, 0.0
    units = [float(row[0]) for row in rows]
    mean = sum(units) / len(units)
    variance = sum((u - mean) ** 2 for u in units) / len(units) if len(units) > 1 else 0.0
    return mean, variance ** 0.5, float(rows[0][1])


def _sellable_pairs(db: Session) -> list[tuple[str, str]]:
    stmt = select(DailySales.store_id, DailySales.product_id).group_by(
        DailySales.store_id, DailySales.product_id
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def generate_events(
    db: Session,
    *,
    count: int,
    rng: random.Random,
    now: datetime,
    source: str = "simulator",
) -> list[LiveSalesEvent]:
    """Insert `count` synthetic POS events drawn from the real demand profile."""
    pairs = _sellable_pairs(db)
    if not pairs:
        return []

    created: list[LiveSalesEvent] = []
    for _ in range(count):
        store_id, product_id = rng.choice(pairs)
        mean, std, price = _demand_profile(db, store_id, product_id)
        # A live event is one store's day of demand for that product: sample
        # around the historical mean, and never below zero.
        units = max(0, int(round(rng.gauss(mean, max(std, 1.0)))))
        created.append(
            LiveSalesEvent(
                event_time=now,
                store_id=store_id,
                product_id=product_id,
                units_sold=units,
                unit_price=price,
                source=source,
            )
        )
    db.add_all(created)
    db.commit()
    for event in created:
        db.refresh(event)
    return created


# --- Proactive alerting -----------------------------------------------------

def live_units_sold(db: Session, product_id: str, since: datetime | None = None) -> float:
    """Total simulated units sold for a product (optionally from `since`)."""
    stmt = select(func.coalesce(func.sum(LiveSalesEvent.units_sold), 0)).where(
        LiveSalesEvent.product_id == product_id
    )
    if since is not None:
        stmt = stmt.where(LiveSalesEvent.event_time >= since)
    return float(db.execute(stmt).scalar_one())


def evaluate_product_alert(
    db: Session,
    product_id: str,
    *,
    now: datetime,
    cooldown_seconds: int,
    trigger: str = "simulator",
    lead_time_days: int | None = None,
) -> tuple[StockoutAlert | None, str | None]:
    """Raise an alert if the live drawdown pushes this product into risk.

    Returns (alert, None) when one was written, or (None, reason) where
    reason is "healthy" or "suppressed" (still inside the cooldown window at
    the same severity -- the open alert is already on the dashboard).

    The risk formula is the documented one from stockout_service; the only
    change is that inventory is projected forward with real live sales
    instead of being read at the end of the historical dataset.
    """
    risk = stockout_service.calculate_stockout_risk(db, product_id, lead_time_days)
    as_of = datetime.combine(risk.as_of_date, time.min)
    sold = live_units_sold(db, product_id, since=as_of)
    projected = risk.current_inventory - sold

    if projected < risk.forecast_lead_time_demand:
        severity = CRITICAL
    elif projected < risk.required_inventory:
        severity = WARNING
    else:
        return None, "healthy"

    latest = db.execute(
        select(StockoutAlert)
        .where(StockoutAlert.product_id == product_id)
        .order_by(StockoutAlert.created_at.desc())
        .limit(1)
    ).scalars().first()
    if (
        latest is not None
        and latest.severity == severity
        and (now - latest.created_at) < timedelta(seconds=cooldown_seconds)
    ):
        return None, "suppressed"

    message = (
        f"{product_id}: projected on-hand stock is {projected:.0f} units "
        f"({risk.current_inventory:.0f} recorded on {risk.as_of_date} minus {sold:.0f} units of live sales), "
        f"against {risk.forecast_lead_time_demand:.0f} units forecast for the {risk.lead_time_days}-day lead time "
        f"and a {risk.safety_stock:.0f}-unit safety buffer "
        f"(required: {risk.required_inventory:.0f})."
    )

    alert = StockoutAlert(
        created_at=now,
        product_id=product_id,
        severity=severity,
        kind="STOCKOUT_RISK",
        message=message,
        current_inventory=risk.current_inventory,
        live_units_sold=sold,
        projected_inventory=projected,
        forecast_lead_time_demand=risk.forecast_lead_time_demand,
        required_inventory=risk.required_inventory,
        lead_time_days=risk.lead_time_days,
        acknowledged=False,
        trigger=trigger,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert, None


# --- Service + background runner --------------------------------------------

class SimulatorService:
    """Generates live traffic on demand, on a timer, or from the API."""

    def __init__(
        self,
        hub: LiveEventHub | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
        settings: Settings | None = None,
        rng: random.Random | None = None,
    ):
        self.hub = hub if hub is not None else get_live_hub()
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.rng = rng or random.Random()
        self._task: Optional[asyncio.Task] = None
        self._ticks = 0
        self._last_tick: Optional[SimulationTick] = None
        self.last_tick_seconds: Optional[float] = None

    # --- one tick -----------------------------------------------------------

    def tick(
        self,
        *,
        events_per_tick: int | None = None,
        trigger: str = "simulator",
        now: datetime | None = None,
    ) -> SimulationTick:
        """Generate events, publish them, and re-check risk for what sold."""
        now = now or _utcnow()
        count = events_per_tick if events_per_tick is not None else self.settings.simulator_events_per_tick
        cooldown = self.settings.simulator_alert_cooldown_seconds

        with self.session_factory() as db:
            events = generate_events(db, count=count, rng=self.rng, now=now)
            tick = SimulationTick(tick_at=now, events=[event.to_dict() for event in events])

            for frame in tick.events:
                self.hub.publish({"type": "sales_event", **frame})

            for product_id in sorted({event["product_id"] for event in tick.events}):
                alert, reason = evaluate_product_alert(
                    db, product_id, now=now, cooldown_seconds=cooldown, trigger=trigger
                )
                if alert is None:
                    if reason == "suppressed":
                        tick.suppressed_alerts += 1
                    continue
                tick.alerts.append(alert.to_dict())
                self.hub.publish({"type": "alert", **alert.to_dict()})

        self._ticks += 1
        self._last_tick = tick
        return tick

    # --- background runner --------------------------------------------------

    async def run_forever(self, tick_seconds: float | None = None) -> None:
        interval = tick_seconds if tick_seconds is not None else self.settings.simulator_tick_seconds
        self.last_tick_seconds = interval
        log.info("Live simulator started (%.1fs interval)", interval)
        try:
            while True:
                try:
                    # DB + XGBoost work is blocking; keep the event loop free.
                    await anyio.to_thread.run_sync(self.tick)
                except Exception:  # noqa: BLE001 -- one bad tick must not kill the loop
                    log.exception("Simulator tick failed; continuing")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            log.info("Live simulator stopped")
            raise

    def start(self, loop: asyncio.AbstractEventLoop, tick_seconds: float | None = None) -> bool:
        """Start the background task. False if it was already running."""
        if self.running:
            return False
        self._task = loop.create_task(self.run_forever(tick_seconds))
        return True

    def stop(self) -> bool:
        """Cancel the background task. False if it wasn't running."""
        if not self.running:
            self._task = None
            return False
        self._task.cancel()
        self._task = None
        return True

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        return {
            "running": self.running,
            "ticks": self._ticks,
            "tick_seconds": self.last_tick_seconds or self.settings.simulator_tick_seconds,
            "events_per_tick": self.settings.simulator_events_per_tick,
            "alert_cooldown_seconds": self.settings.simulator_alert_cooldown_seconds,
            "last_tick": self._last_tick.as_dict() if self._last_tick else None,
            "hub": self.hub.stats(),
        }


_simulator: Optional[SimulatorService] = None


def get_simulator_service() -> SimulatorService:
    global _simulator
    if _simulator is None:
        _simulator = SimulatorService()
    return _simulator


def set_simulator_service(service: Optional[SimulatorService]) -> None:
    """Override the global service (used by tests)."""
    global _simulator
    _simulator = service

