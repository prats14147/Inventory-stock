"""backend/app/routers/products.py"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import product_repository, sales_repository
from app.schemas.product import ProductDetailResponse, ProductListResponse
from app.services import inventory_service

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
def list_products(db: Session = Depends(get_db)):
    ids = product_repository.list_product_ids(db)
    return ProductListResponse(product_ids=ids, count=len(ids))


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(product_id: str, db: Session = Depends(get_db)):
    inventory = inventory_service.get_product_inventory(db, product_id)  # raises NotFoundError -> 404
    total_sold = sales_repository.get_total_units_sold(db, product_id)
    return ProductDetailResponse(
        product_id=product_id,
        as_of_date=inventory.as_of_date,
        current_total_inventory=inventory.total_inventory,
        total_units_sold_all_time=total_sold,
    )
