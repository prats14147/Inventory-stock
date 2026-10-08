"""
backend/app/schemas/dashboard.py

One-shot payload for the dashboard (Tier A).

Before this existed the dashboard fired five separate requests on mount, three
of which each forecast all 20 products, so the page sat behind a blank loading
screen until the slowest one returned. This collapses them into one response.

Nothing here is a new calculation: every number is produced by the same
inventory / sales / stockout services the individual pages use, so the summary
can never disagree with the page it summarises.
"""

from datetime import date

from pydantic import BaseModel

from app.schemas.sales import CategorySalesSummary, ProductSalesRank
from app.schemas.stockout import RiskLevel


class RiskCounts(BaseModel):
    high: int
    medium: int
    low: int
    at_risk: int = 0


class NeedsAttentionItem(BaseModel):
    """One product that needs a decision today, worst risk first."""

    product_id: str
    name: str
    sku: str
    category: str
    risk: RiskLevel
    current_inventory: float
    required_inventory: float
    recommended_reorder_quantity: float
    reason: str


class LowStockItem(BaseModel):
    """Low stock item for the dashboard preview."""

    product_id: str
    name: str
    sku: str
    category: str
    store_id: str
    inventory_level: int
    threshold: int


class SalesSparklinePoint(BaseModel):
    """One point in the 7-day sales sparkline."""

    date: date
    units_sold: int


class StockMovementFeedItem(BaseModel):
    """Recent stock movement for the dashboard feed."""

    product_id: str
    name: str
    store_id: str
    movement_type: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reason: str
    occurred_at: str


class DashboardSummaryResponse(BaseModel):
    as_of_date: date | None
    product_count: int
    store_count: int
    total_inventory_units: int
    low_stock_count: int
    low_stock_threshold: int
    risk_counts: RiskCounts
    needs_attention: list[NeedsAttentionItem]
    low_stock_preview: list[LowStockItem]
    sales_sparkline: list[SalesSparklinePoint]
    stock_movements_feed: list[StockMovementFeedItem]
    category_sales: list[CategorySalesSummary]
    top_products: list[ProductSalesRank]
    # Wall-clock cost of building this payload, in ms.
    compute_ms: int
    # True when the risk rows came from the in-process cache rather than being
    # recomputed -- lets the UI show that a number is cached, never silently.
    served_from_cache: bool