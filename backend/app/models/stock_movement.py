"""backend/app/models/stock_movement.py

Append-only ledger of inventory changes. `daily_inventory.inventory_level` is
the current on-hand quantity; this table answers what it was before a change
and why it moved.
"""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

SALE = "SALE"
DELIVERY = "DELIVERY"
RETURN = "RETURN"
MANUAL_CORRECTION = "MANUAL_CORRECTION"
OPENING = "OPENING"

MOVEMENT_TYPES = (SALE, DELIVERY, RETURN, MANUAL_CORRECTION, OPENING)
ADJUSTABLE_TYPES = (DELIVERY, RETURN, MANUAL_CORRECTION)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_stock_movements_product_time", "product_id", "occurred_at"),
        Index("ix_stock_movements_store_product", "store_id", "product_id"),
        Index("ix_stock_movements_type", "movement_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    business_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    store_id: Mapped[str] = mapped_column(String(20), ForeignKey("stores.store_id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(20), ForeignKey("products.product_id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)

    store = relationship("Store")
    product = relationship("Product")

    def __repr__(self) -> str:
        return (
            f"<StockMovement {self.movement_type} {self.store_id}/{self.product_id} "
            f"{self.quantity_before}->{self.quantity_after}>"
        )
