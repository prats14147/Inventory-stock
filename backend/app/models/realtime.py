"""
backend/app/models/realtime.py

Tables for the Tier 1 real-time layer: a stream of live sales events
(produced by the demo data simulator) and the proactive stockout alerts
derived from them.

DELIBERATE SEPARATION FROM THE ANALYTICAL TABLES: live events are written to
their own table and NEVER mutate `daily_sales` / `daily_inventory`. The
historical dataset stays the single source of truth for analytics, ML
features, and forecasting (spec section 14), so a live demo can run for
hours without corrupting a single number any model was trained or validated
on. Live events are, by construction, not part of any backtest -- see
docs/limitations.md.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LiveSalesEvent(Base):
    """One synthetic point-of-sale event emitted by the simulator."""

    __tablename__ = "live_sales_events"
    __table_args__ = (
        Index("ix_live_sales_events_product_time", "product_id", "event_time"),
        Index("ix_live_sales_events_time", "event_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    store_id: Mapped[str] = mapped_column(String(20), ForeignKey("stores.store_id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(20), ForeignKey("products.product_id"), nullable=False)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    # Where the event came from ("simulator" today; a real POS integration
    # would write its own value here without touching any other table).
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="simulator")

    store = relationship("Store")
    product = relationship("Product")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_time": self.event_time.isoformat(),
            "store_id": self.store_id,
            "product_id": self.product_id,
            "units_sold": self.units_sold,
            "unit_price": self.unit_price,
            "source": self.source,
        }


class StockoutAlert(Base):
    """A proactive stockout alert raised for a product.

    `projected_inventory` = last recorded inventory minus live units sold
    since that record's date, i.e. what the shelf looks like *right now*
    rather than at the end of the historical dataset. Every field is a
    number produced by a documented query/formula, never by the LLM.
    """

    __tablename__ = "stockout_alerts"
    __table_args__ = (
        Index("ix_stockout_alerts_product_created", "product_id", "created_at"),
        Index("ix_stockout_alerts_acknowledged", "acknowledged"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    product_id: Mapped[str] = mapped_column(String(20), ForeignKey("products.product_id"), nullable=False)

    # "CRITICAL" (cannot cover forecast lead-time demand) or "WARNING"
    # (covers demand but not the safety-stock buffer).
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="STOCKOUT_RISK")
    message: Mapped[str] = mapped_column(Text, nullable=False)

    current_inventory: Mapped[float] = mapped_column(Float, nullable=False)
    live_units_sold: Mapped[float] = mapped_column(Float, nullable=False)
    projected_inventory: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_lead_time_demand: Mapped[float] = mapped_column(Float, nullable=False)
    required_inventory: Mapped[float] = mapped_column(Float, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)

    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="simulator")

    product = relationship("Product")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "product_id": self.product_id,
            "severity": self.severity,
            "kind": self.kind,
            "message": self.message,
            "current_inventory": self.current_inventory,
            "live_units_sold": self.live_units_sold,
            "projected_inventory": self.projected_inventory,
            "forecast_lead_time_demand": self.forecast_lead_time_demand,
            "required_inventory": self.required_inventory,
            "lead_time_days": self.lead_time_days,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "trigger": self.trigger,
        }
