"""backend/app/routers/inventory.py"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DailyInventory, Product, Store
from app.models.stock_movement import MANUAL_CORRECTION, StockMovement
from app.repositories import inventory_repository
from app.schemas.inventory import (
    CurrentInventoryRow,
    InventoryUpsertRequest,
    InventoryUpsertResponse,
    LowStockResponse,
    ProductInventoryResponse,
    StockAdjustmentRequest,
    StockAdjustmentResponse,
)
from app.services import inventory_service

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.post("", response_model=InventoryUpsertResponse)
def upsert_inventory(payload: InventoryUpsertRequest, db: Session = Depends(get_db)):
    """Add a product/store stock row or update its quantity at the current data date."""
    as_of = inventory_repository.get_latest_date(db) or date.today()

    # Products must already exist in the product catalog.
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product {payload.product_id} not found in the product catalog.",
        )
    if payload.cost_price is not None:
        product.cost_price = payload.cost_price

    # Stores can still be created automatically.
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
            category=product.category,
            region=payload.region,
        )
        db.add(row)

    else:
        quantity_before = row.inventory_level
        quantity_after = payload.inventory_level
        quantity_delta = quantity_after - quantity_before

        row.inventory_level = quantity_after
        row.units_ordered = payload.units_ordered

        # Category now comes from the product catalog.
        row.category = product.category

        if payload.region is not None:
            row.region = payload.region

        if quantity_delta != 0:
            db.add(
                StockMovement(
                    occurred_at=datetime.now(),
                    business_date=as_of,
                    store_id=payload.store_id,
                    product_id=payload.product_id,
                    movement_type=MANUAL_CORRECTION,
                    quantity_delta=quantity_delta,
                    quantity_before=quantity_before,
                    quantity_after=quantity_after,
                    reason="Manual inventory correction",
                    source="inventory_upsert",
                )
            )

    db.commit()

    return InventoryUpsertResponse(
        date=as_of,
        product_id=payload.product_id,
        store_id=payload.store_id,
        inventory_level=payload.inventory_level,
        units_ordered=payload.units_ordered,
        created=created,
    )


@router.post("/adjust", response_model=StockAdjustmentResponse)
def adjust_inventory(
    payload: StockAdjustmentRequest,
    db: Session = Depends(get_db),
):
    """Record a delivery, return, or manual stock correction."""
    return inventory_service.adjust_stock(db, payload)


@router.get("", response_model=list[CurrentInventoryRow])
def list_current_inventory(
    category: str | None = None,
    region: str | None = None,
    db: Session = Depends(get_db),
):
    rows = inventory_repository.get_all_current_inventory(
        db,
        category=category,
        region=region,
    )
    return [CurrentInventoryRow(**row) for row in rows]


@router.get("/export/csv")
def export_inventory_csv(
    category: str | None = None,
    region: str | None = None,
    db: Session = Depends(get_db),
):
    """Export the current inventory listing as CSV."""
    import csv
    import io
    from datetime import date as _date
    from fastapi.responses import StreamingResponse

    rows = inventory_repository.get_all_current_inventory(db, category=category, region=region)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Store ID", "Product ID", "Category", "Region", "Stock on Hand", "Units Ordered"])
    for r in rows:
        writer.writerow([r.get("date"), r.get("store_id"), r.get("product_id"), r.get("category"), r.get("region"), r.get("inventory_level"), r.get("units_ordered")])
    output.seek(0)
    filename = f"inventory_export_{_date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/low-stock", response_model=LowStockResponse)
def low_stock(
    threshold: int | None = Query(
        None,
        description="Override the default low-stock threshold",
    ),
    db: Session = Depends(get_db),
):
    return inventory_service.get_low_stock(db, threshold=threshold)


@router.get("/{product_id}", response_model=ProductInventoryResponse)
def get_inventory(product_id: str, db: Session = Depends(get_db)):
    return inventory_service.get_product_inventory(
        db,
        product_id,
    )
