"""
backend/app/repositories/inventory_repository.py

"Current" inventory is defined as the latest date present in the dataset
(the data is historical, 2022-01-01 to 2024-01-01, so there is no literal
present-day row -- see docs/limitations.md).
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyInventory, DailySales


def get_latest_date(db: Session) -> date | None:
    return db.execute(select(func.max(DailyInventory.date))).scalar_one_or_none()


def get_current_inventory_rows(db: Session, product_id: str, as_of: date | None = None) -> list[DailyInventory]:
    """All store-level rows for a product on the reference date (default: latest date in the data)."""
    ref_date = as_of or get_latest_date(db)
    if ref_date is None:
        return []
    stmt = select(DailyInventory).where(
        DailyInventory.product_id == product_id,
        DailyInventory.date == ref_date,
    )
    return list(db.execute(stmt).scalars().all())


def get_all_current_inventory(
    db: Session,
    as_of: date | None = None,
    category: str | None = None,
    region: str | None = None,
    below_threshold: int | None = None,
) -> list[dict]:
    """
    Current inventory across all products/stores, optionally filtered by
    category/region (joined from DailySales on the shared composite key,
    since category/region are not stable attributes of product/store --
    see docs/limitations.md).

    `below_threshold` filters on inventory_level in SQL rather than in Python:
    the low-stock path only needs the few matching rows, and pulling the whole
    reference date across the wire to discard most of it was a real cost.
    """
    ref_date = as_of or get_latest_date(db)
    if ref_date is None:
        return []

    stmt = (
        select(
            DailyInventory.date,
            DailyInventory.store_id,
            DailyInventory.product_id,
            DailyInventory.inventory_level,
            DailyInventory.units_ordered,
            func.coalesce(DailyInventory.category, DailySales.category, "Uncategorized").label("category"),
            func.coalesce(DailyInventory.region, DailySales.region, "Unassigned").label("region"),
        )
        .outerjoin(
            DailySales,
            (DailySales.date == DailyInventory.date)
            & (DailySales.store_id == DailyInventory.store_id)
            & (DailySales.product_id == DailyInventory.product_id),
        )
        .where(DailyInventory.date == ref_date)
    )
    if category:
        stmt = stmt.where(func.coalesce(DailyInventory.category, DailySales.category) == category)
    if region:
        stmt = stmt.where(func.coalesce(DailyInventory.region, DailySales.region) == region)
    if below_threshold is not None:
        stmt = stmt.where(DailyInventory.inventory_level < below_threshold)

    rows = db.execute(stmt).all()
    return [dict(row._mapping) for row in rows]


def get_low_stock_rows(
    db: Session,
    threshold: int,
    as_of: date | None = None,
) -> list[dict]:
    """Store-product combinations whose current inventory is below `threshold`."""
    return get_all_current_inventory(db, as_of=as_of, below_threshold=threshold)


def get_inventory_headline(db: Session, as_of: date | None = None) -> dict:
    """Totals for the dashboard header, in one grouped query.

    Cheaper than summing the full listing in Python: the database does the
    aggregation over the reference date only.
    """
    ref_date = as_of or get_latest_date(db)
    if ref_date is None:
        return {"as_of_date": None, "total_inventory_units": 0, "store_count": 0, "combination_count": 0}

    stmt = select(
        func.coalesce(func.sum(DailyInventory.inventory_level), 0),
        func.count(func.distinct(DailyInventory.store_id)),
        func.count(),
    ).where(DailyInventory.date == ref_date)
    total_units, store_count, combination_count = db.execute(stmt).one()
    return {
        "as_of_date": ref_date,
        "total_inventory_units": int(total_units),
        "store_count": int(store_count),
        "combination_count": int(combination_count),
    }
