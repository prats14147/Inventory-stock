"""Product catalog API routes."""

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.repositories import product_repository, sales_repository
from app.schemas.product import (
    ProductCostRow,
    ProductCostsResponse,
    ProductCostUpdateRequest,
    ProductCreateRequest,
    ProductDetailResponse,
    ProductListResponse,
    ProductSummary,
)
from app.services import inventory_service

router = APIRouter(prefix="/api/products", tags=["products"])


def _next_product_id(db: Session) -> str:
    """Generate the next P#### product ID when one is not supplied."""
    product_ids = db.scalars(select(Product.product_id)).all()

    numbers: list[int] = []
    for product_id in product_ids:
        match = re.fullmatch(r"P(\d+)", product_id.upper())
        if match:
            numbers.append(int(match.group(1)))

    return f"P{max(numbers, default=0) + 1:04d}"


@router.post("", response_model=ProductSummary, status_code=201)
def create_product(
    payload: ProductCreateRequest,
    db: Session = Depends(get_db),
):
    """Create a new product in the canonical product catalog."""
    product_id = (
        payload.product_id.strip().upper()
        if payload.product_id
        else _next_product_id(db)
    )
    name = payload.name.strip()
    sku = payload.sku.strip().upper()
    category = payload.category.strip()

    if not product_id or not name or not sku or not category:
        raise HTTPException(
            status_code=400,
            detail="Product ID, name, SKU, and category are required.",
        )

    if db.get(Product, product_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Product {product_id} already exists.",
        )

    existing_sku = db.execute(
        select(Product).where(Product.sku == sku)
    ).scalar_one_or_none()

    if existing_sku is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"SKU {sku} is already in use by "
                f"product {existing_sku.product_id}."
            ),
        )

    product = Product(
        product_id=product_id,
        name=name,
        sku=sku,
        category=category,
        cost_price=payload.cost_price,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    return product


@router.get("", response_model=ProductListResponse)
def list_products(db: Session = Depends(get_db)):
    products = product_repository.list_products(db)

    return ProductListResponse(
        product_ids=[product.product_id for product in products],
        products=products,
        count=len(products),
    )


@router.get("/costs", response_model=ProductCostsResponse)
def list_product_costs(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Product).order_by(Product.product_id)
    ).all()

    return ProductCostsResponse(
        products=[
            ProductCostRow(
                product_id=row.product_id,
                cost_price=row.cost_price,
            )
            for row in rows
        ]
    )


@router.put("/{product_id}/cost", response_model=ProductCostRow)
def update_product_cost(
    product_id: str,
    payload: ProductCostUpdateRequest,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)

    if product is None:
        from app.services.errors import NotFoundError

        raise NotFoundError(
            f"Product '{product_id}' was not found."
        )

    product.cost_price = payload.cost_price
    db.commit()

    return ProductCostRow(
        product_id=product_id,
        cost_price=product.cost_price,
    )


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
):
    product = product_repository.get_product(db, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} not found",
        )

    inventory = inventory_service.get_product_inventory(
        db,
        product_id,
    )
    total_sold = sales_repository.get_total_units_sold(
        db,
        product_id,
    )

    return ProductDetailResponse(
        product_id=product.product_id,
        name=product.name,
        sku=product.sku,
        category=product.category,
        as_of_date=inventory.as_of_date,
        current_total_inventory=inventory.total_inventory,
        total_units_sold_all_time=total_sold,
        cost_price=product.cost_price,
    )
