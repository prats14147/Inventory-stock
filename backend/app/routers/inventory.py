"""backend/app/routers/inventory.py"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import inventory_repository
from app.schemas.inventory import CurrentInventoryRow, LowStockResponse, ProductInventoryResponse
from app.services import inventory_service

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


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
