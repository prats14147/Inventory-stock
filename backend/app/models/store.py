"""backend/app/models/store.py"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Store(Base):
    """
    Identity table only. In the source dataset, `Region` is NOT a fixed
    attribute of Store ID -- every store appears under all 4 regions across
    different rows (see docs/limitations.md). Region is therefore stored
    per-row on DailySales instead of here.
    """

    __tablename__ = "stores"

    store_id: Mapped[str] = mapped_column(String(20), primary_key=True)

    inventory_records = relationship("DailyInventory", back_populates="store")
    sales_records = relationship("DailySales", back_populates="store")

    def __repr__(self) -> str:
        return f"<Store {self.store_id}>"
