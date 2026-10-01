"""backend/app/routers/stockout.py"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import product_repository
from app.schemas.stockout import StockoutRiskResponse
from app.services import stockout_service

router = APIRouter(prefix="/api/stockout-risk", tags=["stockout"])


@router.get("", response_model=list[StockoutRiskResponse])
def list_stockout_risk(
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    only_at_risk: bool = Query(False, description="If true, only return MEDIUM/HIGH risk products"),
    db: Session = Depends(get_db),
):
    results = [
        stockout_service.calculate_stockout_risk(db, pid, lead_time_days=lead_time_days)
        for pid in product_repository.list_product_ids(db)
    ]
    if only_at_risk:
        results = [r for r in results if r.risk.value != "LOW"]
    return results


@router.get("/{product_id}", response_model=StockoutRiskResponse)
def get_stockout_risk(
    product_id: str,
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    db: Session = Depends(get_db),
):
    return stockout_service.calculate_stockout_risk(db, product_id, lead_time_days=lead_time_days)
