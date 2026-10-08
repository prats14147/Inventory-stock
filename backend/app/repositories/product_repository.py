"""backend/app/repositories/product_repository.py"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product


def list_product_ids(db: Session) -> list[str]:
    return [
        row[0]
        for row in db.execute(
            select(Product.product_id).order_by(Product.product_id)
        ).all()
    ]


def list_products(db: Session) -> list[Product]:
    return list(
        db.scalars(
            select(Product).order_by(Product.product_id)
        ).all()
    )


def get_product(db: Session, product_id: str) -> Product | None:
    return db.get(Product, product_id)


def product_names_map(db: Session) -> dict[str, str]:
    """Every catalog product's display name keyed by product_id.

    One lightweight query over the (small) products table; the chat layer
    uses it to render human-readable names next to raw P-codes.
    """
    return {
        product_id: name
        for product_id, name in db.execute(
            select(Product.product_id, Product.name)
        ).all()
        if name
    }


def product_exists(db: Session, product_id: str) -> bool:
    return (
        db.execute(
            select(Product.product_id).where(
                Product.product_id == product_id
            )
        ).first()
        is not None
    )
