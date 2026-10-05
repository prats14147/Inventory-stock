"""backend/app/routers/sales.py"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.stock_movement import StockMovementResponse
from app.repositories import inventory_repository, sales_repository
from app.schemas.sales import (
    CategorySalesSummary,
    DailySaleRow,
    RecordSaleRequest,
    RecordSaleResponse,
    SalesTrendResponse,
    StoreSalesSummary,
    TopProductsResponse,
)
from app.services import sales_service
from app.services.errors import InvalidRequestError, NotFoundError


router = APIRouter(prefix="/api/sales", tags=["sales"])


@router.post("/record", response_model=RecordSaleResponse)
def record_sale(
    payload: RecordSaleRequest,
    db: Session = Depends(get_db),
):
    """Record a sale, reduce on-hand inventory, and preserve a full date snapshot."""
    return sales_service.record_sale(db, payload)


@router.get(
    "/stock-movements",
    response_model=list[StockMovementResponse],
)
def list_stock_movements(
    store_id: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return stock movement history, newest first."""

    query = select(StockMovement).order_by(
        StockMovement.occurred_at.desc()
    )

    if store_id:
        query = query.where(StockMovement.store_id == store_id)

    if product_id:
        query = query.where(StockMovement.product_id == product_id)

    if movement_type:
        query = query.where(StockMovement.movement_type == movement_type)

    return db.scalars(query).all()


@router.get("", response_model=list[DailySaleRow])
def list_sales(
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Max rows to return",
    ),
    db: Session = Depends(get_db),
):
    rows = sales_repository.get_sales_rows(
        db,
        product_id=product_id,
        store_id=store_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
    )

    return [DailySaleRow.model_validate(r) for r in rows[:limit]]


@router.get("/top-products", response_model=TopProductsResponse)
def top_products(
    limit: int = Query(10, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_top_products(
        db,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/bottom-products", response_model=TopProductsResponse)
def bottom_products(
    limit: int = Query(10, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_bottom_products(
        db,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/trends", response_model=SalesTrendResponse)
def trends(
    granularity: str = Query(
        "daily",
        pattern="^(daily|weekly|monthly)$",
    ),
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_sales_trend(
        db,
        granularity=granularity,
        product_id=product_id,
        store_id=store_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/by-category",
    response_model=list[CategorySalesSummary],
)
def by_category(
    db: Session = Depends(get_db),
):
    return sales_service.get_category_analysis(db)


@router.get(
    "/by-store",
    response_model=list[StoreSalesSummary],
)
def by_store(
    db: Session = Depends(get_db),
):
    return sales_service.get_store_analysis(db)


@router.get("/profitability/by-store")
def profitability_by_store(
    store_id: str | None = None,
    product_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_store_profitability(
        db, store_id=store_id, product_id=product_id, category=category,
        start_date=start_date, end_date=end_date,
    )


@router.get("/profitability")
def profitability(
    group_by: str = "total",
    sort_order: str = "descending",
    store_id: str | None = None,
    product_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_profitability_analysis(
        db, group_by=group_by, sort_order=sort_order, store_id=store_id, product_id=product_id,
        category=category, start_date=start_date, end_date=end_date,
    )
