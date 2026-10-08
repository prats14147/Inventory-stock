"""backend/app/routers/briefing.py

Proactive briefing endpoint (Upgrade #4).

GET /api/briefing -- headline, open/critical alert counts, top risks, and
suggested draft orders. Deterministic read over existing services; safe to
call on every dashboard load.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import briefing_service

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


@router.get("")
def morning_briefing(db: Session = Depends(get_db)) -> dict:
    return briefing_service.build_morning_briefing(db)
