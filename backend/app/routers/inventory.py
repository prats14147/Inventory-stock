"""backend/app/routers/inventory.py"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DailyInventory, Product, Store
from app.repositories import inventory_repository
from app.schemas.inventory import (
    CurrentInventoryRow,
    InventoryUpsertRequest,
    InventoryUpsertResponse,
    LowStockResponse,
    ProductInventoryResponse,
)
from app.services import inventory_service

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.post("", response_model=InventoryUpsertResponse)
def upsert_inventory(payload: InventoryUpsertRequest, db: Session = Depends(get_db)):
    """Add a product/store stock row or update its quantity at the current data date."""
    as_of = inventory_repository.get_latest_date(db) or date.today()

    product = db.get(Product, payload.product_id)
    if product is None:
        db.add(Product(product_id=payload.product_id))
    store = db.get(Store, payload.store_id)
    if store is None:
        db.add(Store(store_id=payload.store_id))
    db.flush()

    row = db.execute(
        select(DailyInventory).where(
            DailyInventory.date == as_of,
            DailyInventory.product_id == payload.product_id,
            DailyInventory.store_id == payload.store_id,
        )
    ).scalar_one_or_none()
    created = row is None
    if row is None:
        row = DailyInventory(
            date=as_of,
            product_id=payload.product_id,
            store_id=payload.store_id,
            inventory_level=payload.inventory_level,
            units_ordered=payload.units_ordered,
            category=payload.category,
            region=payload.region,
        )
        db.add(row)
    else:
        row.inventory_level = payload.inventory_level
        row.units_ordered = payload.units_ordered
        if payload.category is not None:
            row.category = payload.category
        if payload.region is not None:
            row.region = payload.region

    db.commit()
    return InventoryUpsertResponse(
        date=as_of,
        product_id=payload.product_id,
        store_id=payload.store_id,
        inventory_level=payload.inventory_level,
        units_ordered=payload.units_ordered,
        created=created,
    )


@router.get("", response_model=list[CurrentInventoryRow])
def list_current_inventory(
    category: str | None = None,
    region: str | None = None,
    db: Session = Depends(get_db),
):
    rows = inventory_repository.get_all_current_inventory(db, category=category, region=region)
    return [CurrentInventoryRow(**row) for row in rows]


@router.get("/low-stock", response_model=LowStockResponse)
def low_stock(
    threshold: int | None = Query(None, description="Override the default low-stock threshold"),
    db: Session = Depends(get_db),
):
    return inventory_service.get_low_stock(db, threshold=threshold)


@router.get("/{product_id}", response_model=ProductInventoryResponse)
def get_inventory(product_id: str, db: Session = Depends(get_db)):
    return inventory_service.get_product_inventory(db, product_id)  # raises NotFoundError -> 404
