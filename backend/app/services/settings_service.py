"""backend/app/services/settings_service.py

Effective operations knobs: env-var default overridden by a DB row.

The /settings page writes rows to `system_settings`; the stockout, reorder,
and inventory services read through these helpers so an admin edit takes
effect without a redeploy. If the table is missing (older database) or a
value is unreadable, the env-var default applies -- never a crash.
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings


def _db_override(db: Session | None, key: str):
    if db is None:
        return None
    try:
        from app.models.system_setting import SystemSetting
        row = db.get(SystemSetting, key)
        if row is None:
            return None
        return row.value
    except SQLAlchemyError:
        return None


def effective_lead_time_days(db: Session | None = None, override: int | None = None) -> int:
    if override is not None:
        return override
    raw = _db_override(db, "default_lead_time_days")
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return get_settings().default_lead_time_days


def effective_safety_stock_factor(db: Session | None = None) -> float:
    raw = _db_override(db, "safety_stock_service_factor")
    if raw is not None:
        try:
            return float(raw)
        except (ValueError, TypeError):
            pass
    return get_settings().safety_stock_service_factor


def effective_low_stock_threshold(db: Session | None = None, override: int | None = None) -> int:
    if override is not None:
        return override
    raw = _db_override(db, "low_stock_threshold")
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return get_settings().low_stock_threshold
