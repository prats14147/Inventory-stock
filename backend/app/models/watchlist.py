"""
backend/app/models/watchlist.py

User-pinned products. A watchlist row says only "this product is worth
watching" -- it deliberately stores NO inventory or risk numbers, so pinning a
product can never go stale or contradict the analytical tables. Every figure
shown next to a pinned product is computed live from the same services the
Stockout / Reorder / Forecast pages use.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WatchlistItem(Base):
    """One pinned product."""

    __tablename__ = "watchlist"

    product_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("products.product_id"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Optional free-text reason ("holiday promo", "supplier delayed", ...).
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    product = relationship("Product")

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "created_at": self.created_at.isoformat(),
            "note": self.note,
        }

    def __repr__(self) -> str:
        return f"<WatchlistItem {self.product_id}>"