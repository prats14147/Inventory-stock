# """backend/app/routers/stockout.py"""

# from fastapi import APIRouter, Depends, Query
# from sqlalchemy.orm import Session

# from app.database import get_db
# from app.services import inventory_service
# from app.schemas.stockout import StockoutRiskResponse
# from app.services import stockout_service
# from app.services.errors import NotFoundError

# router = APIRouter(prefix="/api/stockout-risk", tags=["stockout"])


# @router.get("", response_model=list[StockoutRiskResponse])
# def list_stockout_risk(
#     lead_time_days: int | None = Query(None, description="Override the default lead time"),
#     only_at_risk: bool = Query(False, description="If true, only return MEDIUM/HIGH risk product/store rows"),
#     store_id: str | None = Query(None, description="Optional store filter. Results are scored per product/store inventory row."),
#     search: str | None = Query(None, description="Filter by product id, name, or SKU"),
#     category: str | None = Query(None, description="Filter by product category"),
#     limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
#     offset: int = Query(0, ge=0, description="Rows to skip"),
#     db: Session = Depends(get_db),
# ):
#     listing = inventory_service.get_current_inventory_listing(db, category=category)
#     pairs = sorted({(row.product_id, row.store_id) for row in listing.items})
#     if store_id:
#         pairs = [(pid, sid) for pid, sid in pairs if sid == store_id]

#     results = []
#     for pid, sid in pairs:
#         try:
#             results.append(
#                 stockout_service.calculate_stockout_risk(
#                     db, pid, lead_time_days=lead_time_days, store_id=sid
#                 )
#             )
#         except NotFoundError:
#             # Products without enough sales history cannot receive an honest
#             # forecast-based risk score yet. Keep them visible in inventory.
#             continue
#     if only_at_risk:
#         results = [r for r in results if r.risk.value != "LOW"]
#     if search:
#         q = search.lower()
#         results = [r for r in results if q in r.product_id.lower() or q in r.name.lower() or q in r.sku.lower()]
#     risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
#     results.sort(
#         key=lambda r: (
#             risk_order[r.risk.value],
#             r.estimated_days_of_stock if r.estimated_days_of_stock is not None else float("inf"),
#             r.product_id,
#             r.store_id or "",
#         )
#     )
#     return results[offset : offset + limit]


# @router.get("/{product_id}", response_model=StockoutRiskResponse)
# def get_stockout_risk(
#     product_id: str,
#     lead_time_days: int | None = Query(None, description="Override the default lead time"),
#     store_id: str | None = Query(None, description="Store scope, e.g. S001..S005"),
#     db: Session = Depends(get_db),
# ):
#     return stockout_service.calculate_stockout_risk(db, product_id, lead_time_days=lead_time_days, store_id=store_id)


"""backend/app/routers/stockout.py"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.stockout import StockoutRiskResponse
from app.services import stockout_service

router = APIRouter(prefix="/api/stockout-risk", tags=["stockout"])


@router.get("", response_model=list[StockoutRiskResponse])
def list_stockout_risk(
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    only_at_risk: bool = Query(False, description="If true, only return MEDIUM/HIGH risk product/store rows"),
    store_id: str | None = Query(None, description="Optional store filter. Results are scored per product/store inventory row."),
    search: str | None = Query(None, description="Filter by product id, name, or SKU"),
    category: str | None = Query(None, description="Filter by product category"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
    db: Session = Depends(get_db),
):
    results = stockout_service.list_stockout_risks(
        db, lead_time_days=lead_time_days, store_id=store_id, category=category
    )
    if only_at_risk:
        results = [r for r in results if r.risk.value != "LOW"]
    if search:
        q = search.lower()
        results = [r for r in results if q in r.product_id.lower() or q in r.name.lower() or q in r.sku.lower()]
    risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    results.sort(
        key=lambda r: (
            risk_order[r.risk.value],
            r.estimated_days_of_stock if r.estimated_days_of_stock is not None else float("inf"),
            r.product_id,
            r.store_id or "",
        )
    )
    return results[offset : offset + limit]


@router.get("/{product_id}", response_model=StockoutRiskResponse)
def get_stockout_risk(
    product_id: str,
    lead_time_days: int | None = Query(None, description="Override the default lead time"),
    store_id: str | None = Query(None, description="Store scope, e.g. S001..S005"),
    db: Session = Depends(get_db),
):
    return stockout_service.calculate_stockout_risk(db, product_id, lead_time_days=lead_time_days, store_id=store_id)
