"""backend/app/services/sales_service.py"""

from datetime import date

from sqlalchemy.orm import Session

from app.repositories import product_repository, sales_repository
from app.schemas.sales import (
    CategorySalesSummary,
    ProductSalesRank,
    SalesListResponse,
    SalesRecord,
    SalesTrendPoint,
    SalesTrendResponse,
    StoreSalesSummary,
    TopProductsResponse,
)
from app.services.errors import InvalidRequestError, NotFoundError

VALID_GRANULARITIES = {"daily", "weekly", "monthly"}
MAX_LIMIT = 1000


def _validate_date_range(start_date: date | None, end_date: date | None) -> None:
    if start_date and end_date and start_date > end_date:
        raise InvalidRequestError(f"start_date ({start_date}) is after end_date ({end_date}).")


def get_top_products(
    db: Session,
    limit: int = 10,
    start_date: date | None = None,
    end_date: date | None = None,
) -> TopProductsResponse:
    _validate_date_range(start_date, end_date)
    rows = sales_repository.get_ranked_products_by_sales(
        db, limit=limit, ascending=False, start_date=start_date, end_date=end_date
    )
    return TopProductsResponse(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        products=[ProductSalesRank(**row) for row in rows],
    )


def get_bottom_products(
    db: Session,
    limit: int = 10,
    start_date: date | None = None,
    end_date: date | None = None,
) -> TopProductsResponse:
    _validate_date_range(start_date, end_date)
    rows = sales_repository.get_ranked_products_by_sales(
        db, limit=limit, ascending=True, start_date=start_date, end_date=end_date
    )
    return TopProductsResponse(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        products=[ProductSalesRank(**row) for row in rows],
    )


def get_sales_trend(
    db: Session,
    granularity: str = "daily",
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> SalesTrendResponse:
    if granularity not in VALID_GRANULARITIES:
        raise InvalidRequestError(f"granularity must be one of {VALID_GRANULARITIES}, got '{granularity}'.")
    _validate_date_range(start_date, end_date)

    if product_id and not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")

    rows = sales_repository.get_sales_trend(
        db,
        granularity=granularity,
        product_id=product_id,
        store_id=store_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
    )

    return SalesTrendResponse(
        granularity=granularity,
        filters={
            "product_id": product_id,
            "store_id": store_id,
            "category": category,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        points=[SalesTrendPoint(period=row["period"], total_units_sold=row["total_units_sold"]) for row in rows],
    )


def get_category_analysis(db: Session) -> list[CategorySalesSummary]:
    rows = sales_repository.get_category_sales_summary(db)
    return [CategorySalesSummary(**row) for row in rows]


def get_store_analysis(db: Session) -> list[StoreSalesSummary]:
    rows = sales_repository.get_store_sales_summary(db)
    return [StoreSalesSummary(**row) for row in rows]


def get_sales_records(
    db: Session,
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> SalesListResponse:
    _validate_date_range(start_date, end_date)
    if limit > MAX_LIMIT:
        raise InvalidRequestError(f"limit must be <= {MAX_LIMIT}, got {limit}.")
    if product_id and not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")

    rows = sales_repository.get_sales_rows(
        db, product_id=product_id, store_id=store_id, category=category, start_date=start_date, end_date=end_date
    )
    page = rows[offset : offset + limit]
    items = [
        SalesRecord(
            date=r.date,
            store_id=r.store_id,
            product_id=r.product_id,
            category=r.category,
            region=r.region,
            units_sold=r.units_sold,
            price=r.price,
            discount=r.discount,
            holiday_promotion=r.holiday_promotion,
        )
        for r in page
    ]
    return SalesListResponse(items=items, count=len(rows), limit=limit, offset=offset)
