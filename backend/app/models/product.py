"""backend/app/models/product.py"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    """
    Product catalog.

    The original dataset only provides Product ID. The name, SKU, and
    standard category below are application-level catalog metadata added
    to make products easier to identify.
    """

    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sku: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    inventory_records = relationship("DailyInventory", back_populates="product")
    sales_records = relationship("DailySales", back_populates="product")

    def __repr__(self) -> str:
        return f"<Product {self.product_id} {self.name}>"
