"""
backend/app/services/dashboard_service.py

Builds the whole dashboard payload in one pass (Tier A).

The dashboard used to fire five requests on mount, three of which each ran the
stockout/reorder engine across every product. This assembles the same figures
from the same services in a single call, and the risk rows come from the
in-process cache, so a warm dashboard is a handful of cheap queries.

Deliberately NOT a new calculation layer: every number is produced by
inventory_service / sales_service / stockout_service / reorder_service, so this
cannot drift from the individual pages.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories import inventory_repository, product_repository
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    LowStockItem,
    NeedsAttentionItem,
    RiskCounts,
    SalesSparklinePoint,
    StockMovementFeedItem,
)
from app.services import inventory_service, reorder_service, sales_service, stockout_service
from app.services.errors import NotFoundError
from app.models import DailyInventory, DailySales
from app.models.stock_movement import StockMovement

# How many at-risk products the "needs attention" block lists. The full set is
# always available on the Stockout page -- this is a "what do I do first" list,
# so a short one is the point.
NEEDS_ATTENTION_LIMIT = 8
LOW_STOCK_PREVIEW_LIMIT = 5
SPARKLINE_DAYS = 7
STOCK_MOVEMENTS_FEED_LIMIT = 10


def get_dashboard_summary(db: Session) -> DashboardSummaryResponse:
    started = time.perf_counter()
    settings = get_settings()

    product_ids = product_repository.list_product_ids(db)
    headline = inventory_repository.get_inventory_headline(db)
    inventory_listing = inventory_service.get_current_inventory_listing(db)
    product_store_pairs = sorted(
        {(row.product_id, row.store_id) for row in inventory_listing.items}
    )
    cached_before_compute = {
        (pid, sid): stockout_service.was_cached(pid, store_id=sid)
        for pid, sid in product_store_pairs
    }
    low_stock = inventory_service.get_low_stock(db)
    low_stock_count = low_stock.count
    category_sales = sales_service.get_category_analysis(db)
    top_products = sales_service.get_top_products(db, limit=5).products

    risks = []
    for pid, sid in product_store_pairs:
        try:
            risks.append(stockout_service.calculate_stockout_risk(db, pid, store_id=sid))
        except NotFoundError:
            # New products have inventory but no sales history to forecast yet.
            continue
    served_from_cache = all(
        cached_before_compute.get((r.product_id, r.store_id or ""), False)
        for r in risks
    )

    high = [r for r in risks if r.risk.value == "HIGH"]
    medium = [r for r in risks if r.risk.value == "MEDIUM"]
    low = [r for r in risks if r.risk.value == "LOW"]

    # Triage order: HIGH before MEDIUM, then the biggest shortfall first.
    at_risk = sorted(
        [*high, *medium],
        key=lambda r: (0 if r.risk.value == "HIGH" else 1, r.current_inventory - r.required_inventory),
    )

    needs_attention: list[NeedsAttentionItem] = []
    for risk in at_risk[:NEEDS_ATTENTION_LIMIT]:
        try:
            reorder = reorder_service.calculate_reorder(
                db, risk.product_id, risk.lead_time_days, store_id=risk.store_id
            )
            qty = reorder.recommended_reorder_quantity
            product_name = reorder.name
            product_sku = reorder.sku
            product_category = reorder.category
        except Exception:  # noqa: BLE001
            # A watchlist/digest row is better than a 500 on the whole dashboard.
            qty = 0.0
            product = product_repository.get_product(db, risk.product_id)
            product_name = product.name if product else risk.product_id
            product_sku = product.sku if product else risk.product_id
            product_category = product.category if product else "Unknown"
        needs_attention.append(
            NeedsAttentionItem(
                product_id=risk.product_id,
                name=product_name,
                sku=product_sku,
                category=product_category,
                store_id=risk.store_id or "",
                risk=risk.risk,
                current_inventory=risk.current_inventory,
                required_inventory=risk.required_inventory,
                recommended_reorder_quantity=qty,
                reason=risk.reason,
            )
        )

    # Low-stock preview uses the same risk/coverage order as the full list.
    low_stock_items: list[LowStockItem] = []
    for item in low_stock.items[:LOW_STOCK_PREVIEW_LIMIT]:
        product = product_repository.get_product(db, item.product_id)
        low_stock_items.append(
            LowStockItem(
                product_id=item.product_id,
                name=product.name if product else item.product_id,
                sku=product.sku if product else item.product_id,
                category=product.category if product else "Unknown",
                store_id=item.store_id,
                inventory_level=item.inventory_level,
                threshold=low_stock.threshold,
                risk_level=item.risk_level,
                forecast_daily_demand=item.forecast_daily_demand,
                estimated_days_of_stock=item.estimated_days_of_stock,
                reason=item.reason,
            )
        )

    # 7-day sales sparkline (total units sold per day across all products)
    as_of_date = headline.get("as_of_date")
    sales_sparkline: list[SalesSparklinePoint] = []
    if as_of_date:
        for i in range(SPARKLINE_DAYS - 1, -1, -1):
            day = as_of_date - timedelta(days=i)
            total = db.execute(
                select(func.coalesce(func.sum(DailySales.units_sold), 0)).where(DailySales.date == day)
            ).scalar_one()
            sales_sparkline.append(SalesSparklinePoint(date=day, units_sold=int(total)))

    # Recent stock movements feed
    movements = db.execute(
        select(StockMovement)
        .order_by(StockMovement.occurred_at.desc())
        .limit(STOCK_MOVEMENTS_FEED_LIMIT)
    ).scalars().all()

    stock_movements_feed: list[StockMovementFeedItem] = []
    for m in movements:
        product = product_repository.get_product(db, m.product_id)
        stock_movements_feed.append(
            StockMovementFeedItem(
                product_id=m.product_id,
                name=product.name if product else m.product_id,
                store_id=m.store_id,
                movement_type=m.movement_type,
                quantity_delta=m.quantity_delta,
                quantity_before=m.quantity_before,
                quantity_after=m.quantity_after,
                reason=m.reason,
                occurred_at=m.occurred_at.isoformat(),
            )
        )

    compute_ms = int((time.perf_counter() - started) * 1000)

    return DashboardSummaryResponse(
        as_of_date=headline["as_of_date"],
        product_count=len(product_ids),
        store_count=headline["store_count"],
        total_inventory_units=headline["total_inventory_units"],
        low_stock_count=low_stock_count,
        low_stock_threshold=low_stock.threshold,
        risk_counts=RiskCounts(
            high=len(high),
            medium=len(medium),
            low=len(low),
            at_risk=len(high) + len(medium),
        ),
        needs_attention=needs_attention,
        low_stock_preview=low_stock_items,
        sales_sparkline=sales_sparkline,
        stock_movements_feed=stock_movements_feed,
        category_sales=category_sales,
        top_products=top_products,
        compute_ms=compute_ms,
        served_from_cache=served_from_cache,
    )
