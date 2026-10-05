"""
scripts/load_database.py

Loads data/processed/cleaned_inventory.csv into PostgreSQL:
products -> stores -> daily_inventory -> daily_sales.

Idempotent: safe to re-run (uses upsert-style ON CONFLICT DO NOTHING for
dimension tables, and truncates+reloads the fact tables so re-running
doesn't create duplicates).

Usage:
    python scripts/load_database.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402,F401
from app.models import DailyInventory, DailySales, Product, Store  # noqa: E402

PROCESSED_PATH = ROOT / "data" / "processed" / "cleaned_inventory.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("load_database")


def load_dataframe() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_PATH, parse_dates=["Date"])
    log.info("Loaded %d rows from %s", len(df), PROCESSED_PATH)
    return df


def load_dimensions(df: pd.DataFrame) -> None:
    """
    products/stores are identity-only tables: Category and Region are NOT
    stable per-product / per-store attributes in this dataset (verified in
    Phase 3 -- every product appears under all 5 categories, every store
    under all 4 regions). They're loaded onto DailySales instead.
    """
    session = SessionLocal()
    try:
        product_ids = df["Product ID"].drop_duplicates()
        store_ids = df["Store ID"].drop_duplicates()

        for pid in product_ids:
            session.merge(Product(product_id=pid))
        for sid in store_ids:
            session.merge(Store(store_id=sid))

        session.commit()
        log.info("Loaded %d products, %d stores.", len(product_ids), len(store_ids))
    finally:
        session.close()


def load_facts(df: pd.DataFrame) -> None:
    session = SessionLocal()
    try:
        # Fact tables are reloaded fresh each run to keep this idempotent.
        session.execute(text("TRUNCATE TABLE daily_sales"))
        session.execute(text("TRUNCATE TABLE daily_inventory"))
        session.commit()

        inventory_rows = [
            DailyInventory(
                date=row["Date"].date(),
                store_id=row["Store ID"],
                product_id=row["Product ID"],
                inventory_level=int(row["Inventory Level"]),
                units_ordered=int(row["Units Ordered"]),
            )
            for _, row in df.iterrows()
        ]
        sales_rows = [
            DailySales(
                date=row["Date"].date(),
                store_id=row["Store ID"],
                product_id=row["Product ID"],
                category=row["Category"],
                region=row["Region"],
                units_sold=int(row["Units Sold"]),
                price=float(row["Price"]),
                discount=int(row["Discount"]),
                holiday_promotion=bool(row["Holiday/Promotion"]),
                weather_condition=row["Weather Condition"],
                competitor_pricing=float(row["Competitor Pricing"]),
                seasonality=row["Seasonality"],
                demand_forecast_reference=float(row["Demand Forecast"]),
                possible_stock_constrained=bool(row["possible_stock_constrained"]),
                source="Sample Data",
            )
            for _, row in df.iterrows()
        ]

        log.info("Bulk inserting %d inventory rows...", len(inventory_rows))
        session.bulk_save_objects(inventory_rows)
        session.commit()

        log.info("Bulk inserting %d sales rows...", len(sales_rows))
        session.bulk_save_objects(sales_rows)
        session.commit()
    finally:
        session.close()


def main() -> None:
    Base.metadata.create_all(bind=engine)  # no-op if Alembic already created tables
    df = load_dataframe()
    load_dimensions(df)
    load_facts(df)
    log.info("Database load complete.")


if __name__ == "__main__":
    main()
