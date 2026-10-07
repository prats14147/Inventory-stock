"""Daily confirmation that sales entry is complete for a store."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SalesDayClosure(Base):
    __tablename__ = "sales_day_closures"

    business_date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[str] = mapped_column(String(20), ForeignKey("stores.store_id"), primary_key=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
