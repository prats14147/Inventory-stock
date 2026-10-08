"""backend/app/routers/reorder.py"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import product_repository
from app.schemas.reorder import ReorderResponse
from app.services import reorder_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/api/reorder", tags=["reorder"])


@router.get("", response_model=list[ReorderResponse])
def list_reorder(
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    only_needed: bool = Query(False, description="If true, only return products with a nonzero reorder quantity"),
    store_id: str | None = Query(None, description="Store scope, e.g. S001..S005"),
    search: str | None = Query(None, description="Filter by product id, name, or SKU"),
    category: str | None = Query(None, description="Filter by product category"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
    db: Session = Depends(get_db),
):
    results = []
    for pid in product_repository.list_product_ids(db):
        try:
            results.append(reorder_service.calculate_reorder(db, pid, lead_time_days=lead_time_days, store_id=store_id))
        except NotFoundError:
            # A reorder quantity needs a forecast; skip products without
            # enough sales history until they have usable history.
            continue
    if only_needed:
        results = [r for r in results if r.recommended_reorder_quantity > 0]
    if category:
        results = [r for r in results if r.category.lower() == category.lower()]
    if search:
        q = search.lower()
        results = [r for r in results if q in r.product_id.lower() or q in r.name.lower() or q in r.sku.lower()]
    return results[offset : offset + limit]


@router.get("/{product_id}", response_model=ReorderResponse)
def get_reorder(
    product_id: str,
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    store_id: str | None = Query(None, description="Store scope, e.g. S001..S005"),
    db: Session = Depends(get_db),
):
    return reorder_service.calculate_reorder(db, product_id, lead_time_days=lead_time_days, store_id=store_id)
