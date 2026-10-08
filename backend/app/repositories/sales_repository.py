"""backend/app/repositories/sales_repository.py"""

from datetime import date

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyInventory, DailySales


def get_full_history_dataframe(db: Session) -> pd.DataFrame:
    """
    Reconstructs the full (Date, Store ID, Product ID) history as a
    DataFrame, joining DailySales and DailyInventory. Used by the ML
    feature-engineering layer at inference time so that forecasting
    always reads from the database (the source of truth, per spec
    section 14) rather than re-reading the original CSV.

    Column names match data/processed/cleaned_inventory.csv so the same
    ml/features/build_features.py functions work on either source.

    Filtered strictly to 'Sample Data' so that newly recorded genuine
    sales (Real · Manual / Real · CSV Import) are never mixed with the
    synthetic training dataset to prevent misleading forecasts.
    """
    stmt = (
        select(
            DailySales.date,
            DailySales.store_id,
            DailySales.product_id,
            DailySales.category,
            DailySales.region,
            DailySales.units_sold,
            DailySales.price,
            DailySales.discount,
            DailySales.holiday_promotion,
            DailySales.weather_condition,
            DailySales.competitor_pricing,
            DailySales.seasonality,
            DailyInventory.inventory_level,
            DailyInventory.units_ordered,
        )
        .join(
            DailyInventory,
            (DailyInventory.date == DailySales.date)
            & (DailyInventory.store_id == DailySales.store_id)
            & (DailyInventory.product_id == DailySales.product_id),
        )
        .where(DailySales.source == "Sample Data")
        .order_by(DailySales.store_id, DailySales.product_id, DailySales.date)
    )
    rows = db.execute(stmt).all()
    df = pd.DataFrame(rows, columns=[
        "Date", "Store ID", "Product ID", "Category", "Region", "Units Sold",
        "Price", "Discount", "Holiday/Promotion", "Weather Condition",
        "Competitor Pricing", "Seasonality", "Inventory Level", "Units Ordered",
    ])
    df["Date"] = pd.to_datetime(df["Date"])
    df["Holiday/Promotion"] = df["Holiday/Promotion"].astype(int)
    return df


# --- Inference-time history cache (Tier A) ----------------------------------
#
# `daily_sales` / `daily_inventory` are HISTORICAL and immutable: the dataset
# is fixed at 2022-01-01..2024-01-01, and the live simulator deliberately writes
# to its own `live_sales_events` table and never mutates these two (see
# app/models/realtime.py). So the joined history cannot change while the process
# runs, and rebuilding it per call is pure waste.
#
# It is not a small waste: the stockout/reorder list forecasts every product,
# and each forecast called this function twice -> 40 full-table joins for a
# single page load. Caching it took that page from >25s to sub-second.
#
# Tests that write to these tables must call clear_history_cache() afterwards.

_history_cache: pd.DataFrame | None = None


def clear_history_cache() -> None:
    """Drops the cached history frame. Required after any write to
    daily_sales / daily_inventory (tests, or a future data reload)."""
    global _history_cache
    _history_cache = None


def get_full_history_dataframe_cached(db: Session) -> pd.DataFrame:
    """`get_full_history_dataframe`, built once per process.

    The returned frame is shared, so callers must treat it as read-only --
    every current caller only filters/copies out of it.
    """
    global _history_cache
    if _history_cache is None:
        _history_cache = get_full_history_dataframe(db)
    return _history_cache


def get_total_units_sold(db: Session, product_id: str, source: str | None = None, genuine_only: bool = False) -> int:
    stmt = select(func.coalesce(func.sum(DailySales.units_sold), 0)).where(DailySales.product_id == product_id)
    if source:
        stmt = stmt.where(DailySales.source == source)
    elif genuine_only:
        stmt = stmt.where(DailySales.source.in_(["Real · Manual", "Real · CSV Import"]))
    return int(db.execute(stmt).scalar_one())


def _apply_source_filter(stmt, source: str | None = None, genuine_only: bool = False):
    if source:
        stmt = stmt.where(DailySales.source == source)
    elif genuine_only:
        stmt = stmt.where(DailySales.source.in_(["Real · Manual", "Real · CSV Import"]))
    return stmt


def _sales_filter_stmt(
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
):
    stmt = select(DailySales)
    if product_id:
        stmt = stmt.where(DailySales.product_id == product_id)
    if store_id:
        stmt = stmt.where(DailySales.store_id == store_id)
    if category:
        stmt = stmt.where(DailySales.category == category)
    if start_date:
        stmt = stmt.where(DailySales.date >= start_date)
    if end_date:
        stmt = stmt.where(DailySales.date <= end_date)
    stmt = _apply_source_filter(stmt, source=source, genuine_only=genuine_only)
    return stmt


def count_sales_rows(
    db: Session,
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
) -> int:
    stmt = _sales_filter_stmt(
        product_id=product_id, store_id=store_id, category=category,
        start_date=start_date, end_date=end_date, source=source,
        genuine_only=genuine_only,
    )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    return int(db.execute(count_stmt).scalar_one())


def get_sales_rows(
    db: Session,
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> list[DailySales]:
    stmt = _sales_filter_stmt(
        product_id=product_id, store_id=store_id, category=category,
        start_date=start_date, end_date=end_date, source=source,
        genuine_only=genuine_only,
    )
    stmt = stmt.order_by(DailySales.date.desc(), DailySales.product_id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_ranked_products_by_sales(
    db: Session,
    limit: int = 10,
    ascending: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
) -> list[dict]:
    stmt = select(
        DailySales.product_id,
        func.sum(DailySales.units_sold).label("total_units_sold"),
    ).group_by(DailySales.product_id)

    if start_date:
        stmt = stmt.where(DailySales.date >= start_date)
    if end_date:
        stmt = stmt.where(DailySales.date <= end_date)
    stmt = _apply_source_filter(stmt, source=source, genuine_only=genuine_only)

    stmt = stmt.order_by(
        func.sum(DailySales.units_sold).asc() if ascending else func.sum(DailySales.units_sold).desc()
    ).limit(limit)

    return [dict(row._mapping) for row in db.execute(stmt).all()]


def get_sales_trend(
    db: Session,
    granularity: str = "daily",
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
) -> list[dict]:
    """
    granularity: "daily", "weekly", or "monthly".
    Uses Postgres date_trunc for weekly/monthly bucketing.
    """
    if granularity == "daily":
        bucket = DailySales.date
    elif granularity == "weekly":
        bucket = func.date_trunc("week", DailySales.date)
    elif granularity == "monthly":
        bucket = func.date_trunc("month", DailySales.date)
    else:
        raise ValueError(f"Unsupported granularity: {granularity}")

    stmt = select(
        bucket.label("period"),
        func.sum(DailySales.units_sold).label("total_units_sold"),
    ).group_by(bucket)

    if product_id:
        stmt = stmt.where(DailySales.product_id == product_id)
    if store_id:
        stmt = stmt.where(DailySales.store_id == store_id)
    if category:
        stmt = stmt.where(DailySales.category == category)
    if start_date:
        stmt = stmt.where(DailySales.date >= start_date)
    if end_date:
        stmt = stmt.where(DailySales.date <= end_date)
    stmt = _apply_source_filter(stmt, source=source, genuine_only=genuine_only)

    stmt = stmt.order_by(bucket)
    return [dict(row._mapping) for row in db.execute(stmt).all()]


def get_category_sales_summary(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
) -> list[dict]:
    stmt = (
        select(
            DailySales.category,
            func.sum(DailySales.units_sold).label("total_units_sold"),
        )
        .group_by(DailySales.category)
    )
    if start_date:
        stmt = stmt.where(DailySales.date >= start_date)
    if end_date:
        stmt = stmt.where(DailySales.date <= end_date)
    stmt = _apply_source_filter(stmt, source=source, genuine_only=genuine_only)
    stmt = stmt.order_by(func.sum(DailySales.units_sold).desc())
    return [dict(row._mapping) for row in db.execute(stmt).all()]


def get_store_sales_summary(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
) -> list[dict]:
    stmt = (
        select(
            DailySales.store_id,
            func.sum(DailySales.units_sold).label("total_units_sold"),
        )
        .group_by(DailySales.store_id)
    )
    if start_date:
        stmt = stmt.where(DailySales.date >= start_date)
    if end_date:
        stmt = stmt.where(DailySales.date <= end_date)
    stmt = _apply_source_filter(stmt, source=source, genuine_only=genuine_only)
    stmt = stmt.order_by(func.sum(DailySales.units_sold).desc())
    return [dict(row._mapping) for row in db.execute(stmt).all()]


def get_sales_sources_summary(db: Session) -> dict:
    """Summarizes counts and breakdown between sample data and genuine sales."""
    stmt = select(DailySales.source, func.count()).group_by(DailySales.source)
    counts = dict(db.execute(stmt).all())
    sample_count = counts.get("Sample Data", 0)
    manual_count = counts.get("Real · Manual", 0)
    csv_count = counts.get("Real · CSV Import", 0)
    return {
        "total_sales_count": sum(counts.values()),
        "sample_data_count": sample_count,
        "genuine_sales_count": manual_count + csv_count,
        "real_manual_count": manual_count,
        "real_csv_import_count": csv_count,
    }

