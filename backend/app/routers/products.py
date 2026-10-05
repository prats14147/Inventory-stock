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
    products = product_repository.list_products(db)

    return ProductListResponse(
        product_ids=[product.product_id for product in products],
        products=products,
        count=len(products),
    )


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = product_repository.get_product(db, product_id)

    if product is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} not found",
        )

    inventory = inventory_service.get_product_inventory(db, product_id)
    total_sold = sales_repository.get_total_units_sold(db, product_id)

    return ProductDetailResponse(
        product_id=product.product_id,
        name=product.name,
        sku=product.sku,
        category=product.category,
        as_of_date=inventory.as_of_date,
        current_total_inventory=inventory.total_inventory,
        total_units_sold_all_time=total_sold,
    )
