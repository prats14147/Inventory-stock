"""backend/app/routers/sales.py"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import sales_repository
from app.schemas.sales import (
    CategorySalesSummary,
    DailySaleRow,
    SalesTrendResponse,
    StoreSalesSummary,
    TopProductsResponse,
)
from app.services import sales_service

router = APIRouter(prefix="/api/sales", tags=["sales"])


@router.get("", response_model=list[DailySaleRow])
def list_sales(
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    db: Session = Depends(get_db),
):
    rows = sales_repository.get_sales_rows(
        db, product_id=product_id, store_id=store_id, category=category, start_date=start_date, end_date=end_date
    )
    return [DailySaleRow.model_validate(r) for r in rows[:limit]]


@router.get("/top-products", response_model=TopProductsResponse)
def top_products(
    limit: int = Query(10, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_top_products(db, limit=limit, start_date=start_date, end_date=end_date)


@router.get("/bottom-products", response_model=TopProductsResponse)
def bottom_products(
    limit: int = Query(10, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_bottom_products(db, limit=limit, start_date=start_date, end_date=end_date)


@router.get("/trends", response_model=SalesTrendResponse)
def trends(
    granularity: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
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


@router.get("/by-category", response_model=list[CategorySalesSummary])
def by_category(db: Session = Depends(get_db)):
    return sales_service.get_category_analysis(db)


@router.get("/by-store", response_model=list[StoreSalesSummary])
def by_store(db: Session = Depends(get_db)):
    return sales_service.get_store_analysis(db)
