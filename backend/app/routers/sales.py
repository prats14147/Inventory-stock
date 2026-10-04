"""backend/app/routers/sales.py"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DailyInventory, DailySales
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
from app.repositories.sales_repository import clear_history_cache
from app.services.stockout_service import clear_risk_cache

router = APIRouter(prefix="/api/sales", tags=["sales"])


@router.post("/record", response_model=RecordSaleResponse)
def record_sale(payload: RecordSaleRequest, db: Session = Depends(get_db)):
    """Record a sale, reduce on-hand inventory, and preserve a full date snapshot."""
    latest_date = inventory_repository.get_latest_date(db)
    if latest_date is None:
        raise NotFoundError("No inventory exists yet. Add product stock before recording a sale.")

    sale_date = payload.date or date.today()
    if sale_date < latest_date:
        raise InvalidRequestError(
            f"Sales must be recorded on or after the latest inventory date ({latest_date})."
        )

    if sale_date > latest_date:
        # Advance the inventory snapshot as a whole, so adding today's first
        # sale doesn't make every other product disappear from the current view.
        for old in inventory_repository.get_all_current_inventory(db, as_of=latest_date):
            db.add(
                DailyInventory(
                    date=sale_date,
                    store_id=old["store_id"],
                    product_id=old["product_id"],
                    inventory_level=old["inventory_level"],
                    units_ordered=old["units_ordered"],
                    category=old["category"],
                    region=old["region"],
                )
            )
        db.flush()

    stock = db.get(DailyInventory, (sale_date, payload.store_id, payload.product_id))
    if stock is None:
        raise NotFoundError(
            f"No stock record exists for product {payload.product_id} at store {payload.store_id}."
        )
    if payload.units_sold > stock.inventory_level:
        raise InvalidRequestError(
            f"Only {stock.inventory_level} units are on hand; the sale quantity is {payload.units_sold}."
        )

    opening_stock = stock.inventory_level
    stock.inventory_level -= payload.units_sold
    stock.category = payload.category
    stock.region = payload.region

    sale = db.get(DailySales, (sale_date, payload.store_id, payload.product_id))
    if sale is None:
        daily_total = payload.units_sold
        db.add(
            DailySales(
                date=sale_date,
                store_id=payload.store_id,
                product_id=payload.product_id,
                category=payload.category,
                region=payload.region,
                units_sold=payload.units_sold,
                price=payload.price,
                discount=payload.discount,
                holiday_promotion=payload.holiday_promotion,
                weather_condition=payload.weather_condition,
                competitor_pricing=(payload.competitor_pricing if payload.competitor_pricing is not None else payload.price),
                seasonality=payload.seasonality,
                demand_forecast_reference=0.0,
                possible_stock_constrained=payload.units_sold >= opening_stock,
            )
        )
    else:
        daily_total = sale.units_sold + payload.units_sold
        sale.price = ((sale.price * sale.units_sold) + (payload.price * payload.units_sold)) / daily_total
        sale.discount = round(((sale.discount * sale.units_sold) + (payload.discount * payload.units_sold)) / daily_total)
        sale.units_sold = daily_total
        sale.category = payload.category
        sale.region = payload.region
        sale.holiday_promotion = sale.holiday_promotion or payload.holiday_promotion
        sale.weather_condition = payload.weather_condition
        sale.competitor_pricing = payload.competitor_pricing if payload.competitor_pricing is not None else payload.price
        sale.seasonality = payload.seasonality
        sale.possible_stock_constrained = sale.possible_stock_constrained or payload.units_sold >= opening_stock

    db.commit()
    clear_history_cache()
    clear_risk_cache()
    return RecordSaleResponse(
        date=sale_date,
        product_id=payload.product_id,
        store_id=payload.store_id,
        units_sold=payload.units_sold,
        daily_units_sold=daily_total,
        remaining_inventory=stock.inventory_level,
    )


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
