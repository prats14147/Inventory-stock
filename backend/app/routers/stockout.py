"""backend/app/routers/stockout.py"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import product_repository
from app.schemas.stockout import StockoutRiskResponse
from app.services import stockout_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/api/stockout-risk", tags=["stockout"])


@router.get("", response_model=list[StockoutRiskResponse])
def list_stockout_risk(
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    only_at_risk: bool = Query(False, description="If true, only return MEDIUM/HIGH risk products"),
    store_id: str | None = Query(None, description="Store scope, e.g. S001..S005. Without it, inventory/demand are product-level totals across stores."),
    search: str | None = Query(None, description="Filter by product id, name, or SKU"),
    category: str | None = Query(None, description="Filter by product category"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
    db: Session = Depends(get_db),
):
    results = []
    for pid in product_repository.list_product_ids(db):
        try:
            results.append(stockout_service.calculate_stockout_risk(db, pid, lead_time_days=lead_time_days, store_id=store_id))
        except NotFoundError:
            # Products without enough sales history cannot receive an honest
            # forecast-based risk score yet. Keep them visible in inventory.
            continue
    if only_at_risk:
        results = [r for r in results if r.risk.value != "LOW"]
    if category:
        results = [r for r in results if r.category.lower() == category.lower()]
    if search:
        q = search.lower()
        results = [r for r in results if q in r.product_id.lower() or q in r.name.lower() or q in r.sku.lower()]
    return results[offset : offset + limit]


@router.get("/{product_id}", response_model=StockoutRiskResponse)
def get_stockout_risk(
    product_id: str,
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    store_id: str | None = Query(None, description="Store scope, e.g. S001..S005"),
    db: Session = Depends(get_db),
):
    return stockout_service.calculate_stockout_risk(db, product_id, lead_time_days=lead_time_days, store_id=store_id)
