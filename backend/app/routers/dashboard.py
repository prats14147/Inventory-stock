"""
backend/app/routers/dashboard.py

  * GET /api/dashboard/summary -- one request for the whole dashboard

The dashboard previously issued five requests on mount and blocked on the
slowest, which meant a blank loading screen for as long as the stockout engine
took. This returns the same figures in one response (see
app/services/dashboard_service.py).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.dashboard import DashboardSummaryResponse
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummaryResponse:
    return dashboard_service.get_dashboard_summary(db)