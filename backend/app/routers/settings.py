"""backend/app/routers/settings.py

Admin operations knobs, DB-backed with env-var defaults.

Editable keys:
  default_lead_time_days        int   (supplier lead time assumption)
  safety_stock_service_factor   float (safety-stock z-score/service factor)
  low_stock_threshold           int   (low-stock listing threshold)

GET  /api/settings              -- current effective values + source of each
PUT  /api/settings              -- upsert one or more keys (validated)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import engine, get_db
from app.models import Base, SystemSetting
from app.services.errors import InvalidRequestError

router = APIRouter(prefix="/api/settings", tags=["settings"])

# key -> (type, min, max, description)
EDITABLE = {
    "default_lead_time_days": (int, 1, 90, "Supplier lead time assumption in days (no real lead time in dataset)"),
    "safety_stock_service_factor": (float, 0.0, 5.0, "Safety-stock service factor / z-score multiplier on demand std"),
    "low_stock_threshold": (int, 1, 10000, "Inventory level below which a store-product row counts as low stock"),
}

# Ensure the table exists even on databases created before this router landed
# (Alembic migration covers fresh deploys; this covers existing ones).
Base.metadata.create_all(bind=engine, tables=[SystemSetting.__table__])


class SettingsUpdateRequest(BaseModel):
    default_lead_time_days: int | None = None
    safety_stock_service_factor: float | None = None
    low_stock_threshold: int | None = None


def _parse(key: str, raw: str):
    typ, _, _, _ = EDITABLE[key]
    try:
        return typ(raw)
    except (ValueError, TypeError):
        raise InvalidRequestError(f"Stored setting '{key}' has an invalid value '{raw}'.")


def effective_settings(db: Session) -> dict:
    defaults = get_settings()
    rows = {row.key: row.value for row in db.query(SystemSetting).all()}
    result = {}
    for key, (typ, _min, _max, description) in EDITABLE.items():
        default_value = getattr(defaults, key)
        if key in rows:
            result[key] = {
                "value": _parse(key, rows[key]),
                "source": "database",
                "default": default_value,
                "description": description,
            }
        else:
            result[key] = {
                "value": default_value,
                "source": "environment",
                "default": default_value,
                "description": description,
            }
    return result


@router.get("")
def get_all_settings(db: Session = Depends(get_db)) -> dict:
    return {"settings": effective_settings(db)}


@router.put("")
def update_settings(payload: SettingsUpdateRequest, db: Session = Depends(get_db)) -> dict:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise InvalidRequestError("Provide at least one setting to update.")
    for key, value in updates.items():
        if key not in EDITABLE:
            raise InvalidRequestError(f"Unknown setting '{key}'. Editable: {sorted(EDITABLE)}.")
        _, _min, _max, _ = EDITABLE[key]
        if not (_min <= value <= _max):
            raise InvalidRequestError(f"'{key}' must be between {_min} and {_max}, got {value}.")
        row = db.get(SystemSetting, key)
        if row is None:
            db.add(SystemSetting(key=key, value=str(value)))
        else:
            row.value = str(value)
    db.commit()
    # Risk/reorder rows depend on these knobs -- drop the cache so the next
    # read recomputes with the new values.
    from app.services.stockout_service import clear_risk_cache
    clear_risk_cache()
    return {"settings": effective_settings(db)}
