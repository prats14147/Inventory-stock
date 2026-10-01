"""backend/app/services/inventory_service.py"""

from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories import inventory_repository, product_repository
from app.schemas.inventory import (
    CurrentInventoryItem,
    CurrentInventoryListResponse,
    LowStockItem,
    LowStockResponse,
    ProductInventoryResponse,
    StoreInventory,
)
from app.services.errors import NotFoundError


def get_product_inventory(db: Session, product_id: str) -> ProductInventoryResponse:
    if not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")

    rows = inventory_repository.get_current_inventory_rows(db, product_id)
    if not rows:
        # Product exists but somehow has no inventory rows -- shouldn't
        # happen with this dataset, but handle it rather than crash.
        raise NotFoundError(f"No inventory records found for product '{product_id}'.")

    as_of_date = rows[0].date
    stores = [StoreInventory(store_id=r.store_id, inventory_level=r.inventory_level, units_ordered=r.units_ordered) for r in rows]
    total = sum(r.inventory_level for r in rows)

    return ProductInventoryResponse(
        product_id=product_id,
        as_of_date=as_of_date,
        total_inventory=total,
        stores=stores,
    )


def get_low_stock(db: Session, threshold: int | None = None) -> LowStockResponse:
    settings = get_settings()
    effective_threshold = threshold if threshold is not None else settings.low_stock_threshold

    as_of_date = inventory_repository.get_latest_date(db)
    rows = inventory_repository.get_low_stock_rows(db, effective_threshold)

    items = [LowStockItem(**row) for row in rows]
    return LowStockResponse(
        as_of_date=as_of_date,
        threshold=effective_threshold,
        items=items,
        count=len(items),
    )


def get_current_inventory_listing(
    db: Session,
    category: str | None = None,
    region: str | None = None,
) -> CurrentInventoryListResponse:
    as_of_date = inventory_repository.get_latest_date(db)
    rows = inventory_repository.get_all_current_inventory(db, category=category, region=region)
    items = [CurrentInventoryItem(**row) for row in rows]
    return CurrentInventoryListResponse(as_of_date=as_of_date, items=items, count=len(items))


def get_product_info(db: Session, product_id: str):
    """Thin aggregation of existing service calls -- current inventory plus
    the monthly sales trend -- for the /api/products/{product_id} endpoint."""
    from app.schemas.product import ProductInfoResponse
    from app.services import sales_service

    inventory = get_product_inventory(db, product_id)  # raises NotFoundError if unknown
    trend = sales_service.get_sales_trend(db, granularity="monthly", product_id=product_id)
    return ProductInfoResponse(product_id=product_id, inventory=inventory, monthly_sales_trend=trend)
