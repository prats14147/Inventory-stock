"""backend/app/routers/reorder.py"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import product_repository
from app.schemas.reorder import ReorderResponse
from app.services import reorder_service

router = APIRouter(prefix="/api/reorder", tags=["reorder"])


@router.get("", response_model=list[ReorderResponse])
def list_reorder(
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    only_needed: bool = Query(False, description="If true, only return products with a nonzero reorder quantity"),
    db: Session = Depends(get_db),
):
    results = [
        reorder_service.calculate_reorder(db, pid, lead_time_days=lead_time_days)
        for pid in product_repository.list_product_ids(db)
    ]
    if only_needed:
        results = [r for r in results if r.recommended_reorder_quantity > 0]
    return results


@router.get("/{product_id}", response_model=ReorderResponse)
def get_reorder(
    product_id: str,
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    db: Session = Depends(get_db),
):
    return reorder_service.calculate_reorder(db, product_id, lead_time_days=lead_time_days)
