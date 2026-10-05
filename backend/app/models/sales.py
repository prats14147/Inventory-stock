"""backend/app/models/sales.py"""

from datetime import date as date_type, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailySales(Base):
    __tablename__ = "daily_sales"
    __table_args__ = (
        Index("ix_daily_sales_product_date", "product_id", "date"),
    )

    date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    store_id: Mapped[str] = mapped_column(String(20), ForeignKey("stores.store_id"), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(20), ForeignKey("products.product_id"), primary_key=True)

    # Row-level attributes. NOT stored on Product/Store because they are not
    # actually fixed per product/store in this dataset -- see
    # docs/limitations.md ("Category and Region are not stable dimensions").
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    units_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    discount: Mapped[int] = mapped_column(Integer, nullable=False)
    holiday_promotion: Mapped[bool] = mapped_column(Boolean, nullable=False)
    weather_condition: Mapped[str] = mapped_column(String(30), nullable=False)
    competitor_pricing: Mapped[float] = mapped_column(Float, nullable=False)
    seasonality: Mapped[str] = mapped_column(String(20), nullable=False)

    # Reference-only column from the source dataset. Negative values were
    # clipped to 0 during cleaning (Phase 2). NEVER used as a model feature
    # for our own forecasting model -- see ml/features and docs/limitations.md.
    demand_forecast_reference: Mapped[float] = mapped_column(Float, nullable=False)

    # True when Units Sold >= Inventory Level on this date -- flagged, not
    # a confirmed stockout. See docs/limitations.md.
    possible_stock_constrained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Data provenance: "Sample Data", "Real · Manual", or "Real · CSV Import"
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="Sample Data", server_default="Sample Data", index=True)

    store = relationship("Store", back_populates="sales_records")
    product = relationship("Product", back_populates="sales_records")

    def __repr__(self) -> str:
        return f"<DailySales {self.date} {self.store_id}/{self.product_id} sold={self.units_sold}>"


class SalesTransaction(Base):
    """One manually recorded sale with price and cost snapshots for profit."""

    __tablename__ = "sales_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    business_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    store_id: Mapped[str] = mapped_column(String(20), ForeignKey("stores.store_id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(20), ForeignKey("products.product_id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    product = relationship("Product")
    store = relationship("Store")
