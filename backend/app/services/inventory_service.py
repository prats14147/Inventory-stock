"""backend/app/services/inventory_service.py"""

from datetime import date, datetime

from sqlalchemy import select
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
    StockAdjustmentRequest,
    StockAdjustmentResponse,
)
from app.models import DailyInventory
from app.models.stock_movement import ADJUSTABLE_TYPES, StockMovement
from app.services.errors import InvalidRequestError, NotFoundError
from app.repositories import inventory_repository


def get_product_inventory(db: Session, product_id: str, as_of: date | None = None) -> ProductInventoryResponse:
    if not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")

    rows = inventory_repository.get_current_inventory_rows(db, product_id, as_of=as_of)
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


def get_low_stock(db: Session, threshold: int | None = None, as_of: date | None = None) -> LowStockResponse:
    settings = get_settings()
    effective_threshold = threshold if threshold is not None else settings.low_stock_threshold

    as_of_date = as_of or inventory_repository.get_latest_date(db)
    rows = inventory_repository.get_low_stock_rows(db, effective_threshold, as_of=as_of)

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


def adjust_stock(db: Session, payload: StockAdjustmentRequest, source: str = "inventory_adjustment") -> StockAdjustmentResponse:
    """Apply a non-sale stock movement and append it to the movement ledger."""
    if payload.movement_type not in ADJUSTABLE_TYPES:
        raise InvalidRequestError("movement_type must be DELIVERY, RETURN, or MANUAL_CORRECTION.")
    if payload.quantity_delta == 0:
        raise InvalidRequestError("quantity_delta cannot be zero.")

    as_of = inventory_repository.get_latest_date(db) or date.today()
    row = db.execute(select(DailyInventory).where(
        DailyInventory.date == as_of,
        DailyInventory.product_id == payload.product_id,
        DailyInventory.store_id == payload.store_id,
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Inventory record not found for this product and store.")

    before = row.inventory_level
    after = before + payload.quantity_delta
    if after < 0:
        raise InvalidRequestError("Stock cannot become negative.")
    if payload.movement_type in {"DELIVERY", "RETURN"} and payload.quantity_delta < 0:
        raise InvalidRequestError(f"{payload.movement_type} quantity must be positive.")
    if payload.movement_type == "DELIVERY":
        # A receipt always adds the physically received units to on-hand stock.
        # Units ordered is an outstanding-order count, not a cap on what can
        # physically arrive; over-deliveries are allowed and the remainder is
        # floored at zero rather than making the outstanding quantity negative.
        row.units_ordered = max(0, row.units_ordered - payload.quantity_delta)
    row.inventory_level = after
    db.add(StockMovement(
        occurred_at=datetime.now(), business_date=as_of, store_id=payload.store_id,
        product_id=payload.product_id, movement_type=payload.movement_type,
        quantity_delta=payload.quantity_delta, quantity_before=before,
        quantity_after=after, reason=payload.reason, source=source,
    ))
    db.commit()

    from app.services.stockout_service import clear_risk_cache
    clear_risk_cache()
    return StockAdjustmentResponse(
        date=as_of, product_id=payload.product_id, store_id=payload.store_id,
        movement_type=payload.movement_type, quantity_delta=payload.quantity_delta,
        quantity_before=before, quantity_after=after, reason=payload.reason,
    )
