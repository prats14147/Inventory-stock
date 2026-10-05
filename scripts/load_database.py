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
    Load the product catalog and store identities.

    The original dataset does not provide a stable category for each
    Product ID, so the product name, SKU, and standard category below
    are application-level catalog metadata.
    """

    product_catalog = {
        "P0001": {"name": "Wireless Headphones", "sku": "WH-001", "category": "Electronics"},
        "P0002": {"name": "Cotton T-Shirt", "sku": "TS-002", "category": "Clothing"},
        "P0003": {"name": "Wooden Chair", "sku": "CH-003", "category": "Furniture"},
        "P0004": {"name": "Smartphone", "sku": "SP-004", "category": "Electronics"},
        "P0005": {"name": "Running Shoes", "sku": "RS-005", "category": "Clothing"},
        "P0006": {"name": "LED Desk Lamp", "sku": "DL-006", "category": "Electronics"},
        "P0007": {"name": "Kitchen Blender", "sku": "KB-007", "category": "Electronics"},
        "P0008": {"name": "Teddy Bear", "sku": "TB-008", "category": "Toys"},
        "P0009": {"name": "Office Desk", "sku": "OD-009", "category": "Furniture"},
        "P0010": {"name": "Organic Rice", "sku": "OR-010", "category": "Groceries"},
        "P0011": {"name": "Bluetooth Speaker", "sku": "BS-011", "category": "Electronics"},
        "P0012": {"name": "Denim Jeans", "sku": "DJ-012", "category": "Clothing"},
        "P0013": {"name": "Bookshelf", "sku": "BS-013", "category": "Furniture"},
        "P0014": {"name": "Board Game", "sku": "BG-014", "category": "Toys"},
        "P0015": {"name": "Coffee Beans", "sku": "CB-015", "category": "Groceries"},
        "P0016": {"name": "Winter Jacket", "sku": "WJ-016", "category": "Clothing"},
        "P0017": {"name": "Dining Table", "sku": "DT-017", "category": "Furniture"},
        "P0018": {"name": "Action Figure", "sku": "AF-018", "category": "Toys"},
        "P0019": {"name": "Fresh Juice", "sku": "FJ-019", "category": "Groceries"},
        "P0020": {"name": "Wireless Mouse", "sku": "WM-020", "category": "Electronics"},
    }

    session = SessionLocal()

    try:
        product_ids = df["Product ID"].drop_duplicates()
        store_ids = df["Store ID"].drop_duplicates()

        for pid in product_ids:
            details = product_catalog.get(pid)

            if details is None:
                raise ValueError(
                    f"No product catalog details configured for {pid}"
                )

            session.merge(
                Product(
                    product_id=pid,
                    name=details["name"],
                    sku=details["sku"],
                    category=details["category"],
                )
            )

        for sid in store_ids:
            session.merge(Store(store_id=sid))

        session.commit()

        log.info(
            "Loaded %d products, %d stores.",
            len(product_ids),
            len(store_ids),
        )

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
