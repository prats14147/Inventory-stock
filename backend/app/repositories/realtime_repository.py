"""backend/app/repositories/realtime_repository.py

Read/write queries for the real-time layer (live sales events, stockout
alerts), kept out of the routers the same way the Phase 4-6 queries are.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LiveSalesEvent, StockoutAlert


def get_recent_events(db: Session, limit: int = 50) -> list[LiveSalesEvent]:
    stmt = select(LiveSalesEvent).order_by(LiveSalesEvent.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def count_events(db: Session) -> int:
    return int(db.execute(select(func.count()).select_from(LiveSalesEvent)).scalar_one())


def get_alerts(db: Session, acknowledged: bool | None = None, limit: int = 50) -> list[StockoutAlert]:
    stmt = select(StockoutAlert)
    if acknowledged is not None:
        stmt = stmt.where(StockoutAlert.acknowledged.is_(acknowledged))
    stmt = stmt.order_by(StockoutAlert.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_alerts_between(db: Session, start: datetime, end: datetime) -> list[StockoutAlert]:
    """Alerts raised in the half-open window [start, end), newest first.

    Used by the daily digest. An index on (product_id, created_at) exists but
    this filters on created_at alone, so the ordering below is the sort; for
    the demo's alert volume that is cheaper than adding a second index.
    """
    stmt = (
        select(StockoutAlert)
        .where(StockoutAlert.created_at >= start, StockoutAlert.created_at < end)
        .order_by(StockoutAlert.created_at.desc(), StockoutAlert.id.desc())
    )
    return list(db.execute(stmt).scalars().all())


def count_open_alerts(db: Session, severity: str | None = None) -> int:
    stmt = select(func.count()).select_from(StockoutAlert).where(StockoutAlert.acknowledged.is_(False))
    if severity:
        stmt = stmt.where(StockoutAlert.severity == severity)
    return int(db.execute(stmt).scalar_one())


def get_alert(db: Session, alert_id: int) -> StockoutAlert | None:
    return db.get(StockoutAlert, alert_id)


def acknowledge_alert(db: Session, alert_id: int, now: datetime) -> StockoutAlert | None:
    """Mark one alert as handled. Returns None when the id doesn't exist."""
    alert = db.get(StockoutAlert, alert_id)
    if alert is None:
        return None
    if not alert.acknowledged:
        alert.acknowledged = True
        alert.acknowledged_at = now
        db.commit()
        db.refresh(alert)
    return alert


def total_live_units(db: Session) -> int:
    stmt = select(func.coalesce(func.sum(LiveSalesEvent.units_sold), 0))
    return int(db.execute(stmt).scalar_one())
