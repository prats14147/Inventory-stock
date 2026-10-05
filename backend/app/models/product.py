"""backend/app/models/product.py"""

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    """
    Identity table only. In the source dataset, `Category` is NOT a fixed
    attribute of Product ID -- every product appears under all 5 categories
    across different rows (see docs/limitations.md). Category is therefore
    stored per-row on DailySales instead of here.
    """

    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    # Current catalog cost used as the default for new sale transactions.
    # Each transaction stores its own immutable cost snapshot.
    cost_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    inventory_records = relationship("DailyInventory", back_populates="product")
    sales_records = relationship("DailySales", back_populates="product")

    def __repr__(self) -> str:
        return f"<Product {self.product_id}>"
