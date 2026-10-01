"""backend/app/routers/forecast.py"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.services import forecast_service

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


@router.get("/{product_id}", response_model=ForecastResponse)
def get_forecast(
    product_id: str,
    horizon: int | None = Query(None, description="Days ahead to forecast (defaults to DEFAULT_FORECAST_HORIZON)"),
    db: Session = Depends(get_db),
):
    effective_horizon = horizon or get_settings().default_forecast_horizon
    return forecast_service.forecast_product_demand(db, product_id, horizon=effective_horizon)


@router.post("", response_model=ForecastResponse)
def post_forecast(body: ForecastRequest, db: Session = Depends(get_db)):
    effective_horizon = body.horizon or get_settings().default_forecast_horizon
    return forecast_service.forecast_product_demand(db, body.product_id, horizon=effective_horizon)
