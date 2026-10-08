"""backend/app/models/purchase_order.py

Draft purchase orders created from the Reorder page.

Lifecycle:
  DRAFT    -- created from a reorder recommendation; reserves the quantity by
              bumping `units_ordered` on the day's inventory row.
  RECEIVED -- fulfilled: converts into a DELIVERY stock adjustment (on-hand up,
              outstanding orders down) plus a movement-ledger entry.
  CANCELLED -- voided: releases the reservation (units_ordered back down).

The DELIVERY conversion reuses inventory_service.adjust_stock, so the same
over-delivery guard applies ("Only N units are currently ordered").
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(String(20), ForeignKey("products.product_id"), nullable=False)
    store_id: Mapped[str] = mapped_column(String(20), ForeignKey("stores.store_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "store_id": self.store_id,
            "quantity": self.quantity,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
        }
