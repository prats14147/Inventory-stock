"""backend/app/repositories/product_repository.py"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product


def list_product_ids(db: Session) -> list[str]:
    return [row[0] for row in db.execute(select(Product.product_id).order_by(Product.product_id)).all()]


def product_exists(db: Session, product_id: str) -> bool:
    return db.execute(select(Product.product_id).where(Product.product_id == product_id)).first() is not None
