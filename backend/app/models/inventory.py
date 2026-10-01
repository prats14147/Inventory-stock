"""backend/app/models/inventory.py"""

from datetime import date as date_type

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailyInventory(Base):
    __tablename__ = "daily_inventory"
    __table_args__ = (
        Index("ix_daily_inventory_product_date", "product_id", "date"),
        Index("ix_daily_inventory_level", "inventory_level"),
    )

    date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    store_id: Mapped[str] = mapped_column(String(20), ForeignKey("stores.store_id"), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(20), ForeignKey("products.product_id"), primary_key=True)

    inventory_level: Mapped[int] = mapped_column(Integer, nullable=False)
    units_ordered: Mapped[int] = mapped_column(Integer, nullable=False)

    store = relationship("Store", back_populates="inventory_records")
    product = relationship("Product", back_populates="inventory_records")

    def __repr__(self) -> str:
        return f"<DailyInventory {self.date} {self.store_id}/{self.product_id} lvl={self.inventory_level}>"
