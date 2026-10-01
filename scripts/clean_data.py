"""
scripts/clean_data.py

Reproducible cleaning step for the Inventory Intelligence dataset.

Raw CSV -> validation -> cleaning -> processed CSV

Design rules followed (see project README / spec):
  - Never silently discard data. Every correction is logged.
  - Demand Forecast < 0 is clipped to 0 (logged), but the column itself is
    kept only as a reference field -- it is NOT used as a model feature
    later (see ml/features) to avoid leakage.
  - "Units Sold >= Inventory Level" rows are flagged, not deleted or
    reinterpreted. Interpretation is deferred to docs/limitations.md.

Usage:
    python scripts/clean_data.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "retail_store_inventory.csv"
PROCESSED_PATH = ROOT / "data" / "processed" / "cleaned_inventory.csv"
LOG_PATH = ROOT / "data" / "processed" / "cleaning_log.txt"

EXPECTED_CATEGORIES = {"Furniture", "Toys", "Clothing", "Groceries", "Electronics"}
EXPECTED_REGIONS = {"North", "South", "East", "West"}
EXPECTED_PROMOTION_VALUES = {0, 1}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("clean_data")


def load_raw(path: Path) -> pd.DataFrame:
    log.info("Loading raw data from %s", path)
    df = pd.read_csv(path)
    log.info("Loaded %d rows, %d columns", len(df), len(df.columns))
    return df


def validate_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    n_start = len(df)

    # --- Date ---
    df["Date"] = pd.to_datetime(df["Date"], errors="raise")
    log.info("Converted Date to datetime. Range: %s to %s", df["Date"].min(), df["Date"].max())

    # --- Missing values ---
    missing = df.isna().sum()
    total_missing = int(missing.sum())
    if total_missing:
        log.warning("Found %d missing values:\n%s", total_missing, missing[missing > 0])
    else:
        log.info("No missing values found.")

    # --- Duplicate rows ---
    dup_rows = int(df.duplicated().sum())
    if dup_rows:
        log.warning("Found %d fully duplicate rows -- dropping them.", dup_rows)
        df = df.drop_duplicates()
    else:
        log.info("No fully duplicate rows found.")

    # --- Duplicate (Date, Store ID, Product ID) keys ---
    dup_keys = int(df.duplicated(subset=["Date", "Store ID", "Product ID"]).sum())
    if dup_keys:
        log.warning(
            "Found %d duplicate (Date, Store ID, Product ID) combinations. "
            "These are logged but NOT auto-dropped -- inspect manually.",
            dup_keys,
        )
    else:
        log.info("(Date, Store ID, Product ID) is unique across all rows, as expected.")

    # --- Numerical validation ---
    numeric_checks = {
        "Inventory Level": (df["Inventory Level"] < 0),
        "Units Sold": (df["Units Sold"] < 0),
        "Units Ordered": (df["Units Ordered"] < 0),
        "Price": (df["Price"] < 0),
    }
    for col, mask in numeric_checks.items():
        n_bad = int(mask.sum())
        if n_bad:
            log.warning("%d rows have negative %s -- clipping to 0.", n_bad, col)
            df.loc[mask, col] = 0
        else:
            log.info("%s: no negative values.", col)

    discount_bad = (~df["Discount"].between(0, 100)).sum()
    if discount_bad:
        log.warning("%d rows have Discount outside [0, 100] -- clipping.", int(discount_bad))
        df["Discount"] = df["Discount"].clip(0, 100)
    else:
        log.info("Discount: all values within [0, 100].")

    promo_bad = (~df["Holiday/Promotion"].isin(EXPECTED_PROMOTION_VALUES)).sum()
    if promo_bad:
        log.warning(
            "%d rows have Holiday/Promotion outside {0,1} -- inspect manually, not auto-corrected.",
            int(promo_bad),
        )
    else:
        log.info("Holiday/Promotion: all values in {0, 1}.")

    # --- Demand Forecast: negative -> 0 (kept as reference column only) ---
    neg_forecast_mask = df["Demand Forecast"] < 0
    n_neg_forecast = int(neg_forecast_mask.sum())
    pct = 100 * n_neg_forecast / len(df)
    log.info(
        "Demand Forecast < 0: %d rows (%.2f%%) -- clipping to 0. "
        "This column is reference-only and will NOT be used as a model feature.",
        n_neg_forecast,
        pct,
    )
    df.loc[neg_forecast_mask, "Demand Forecast"] = 0

    # --- Possible stock-constrained sales: flag, do not alter ---
    constrained_mask = df["Units Sold"] >= df["Inventory Level"]
    n_constrained = int(constrained_mask.sum())
    pct_c = 100 * n_constrained / len(df)
    log.info(
        "Units Sold >= Inventory Level: %d rows (%.3f%%) -- flagged via new "
        "column 'possible_stock_constrained', values NOT altered. "
        "See docs/limitations.md for interpretation.",
        n_constrained,
        pct_c,
    )
    df["possible_stock_constrained"] = constrained_mask

    # --- Categorical validation ---
    unexpected_categories = set(df["Category"].unique()) - EXPECTED_CATEGORIES
    if unexpected_categories:
        log.warning("Unexpected Category values found: %s", unexpected_categories)
    else:
        log.info("Category: all values within expected set %s", EXPECTED_CATEGORIES)

    unexpected_regions = set(df["Region"].unique()) - EXPECTED_REGIONS
    if unexpected_regions:
        log.warning("Unexpected Region values found: %s", unexpected_regions)
    else:
        log.info("Region: all values within expected set %s", EXPECTED_REGIONS)

    # Normalize whitespace/case inconsistencies defensively (logged if any found)
    for col in ["Category", "Region", "Weather Condition", "Seasonality", "Store ID", "Product ID"]:
        before = df[col].copy()
        df[col] = df[col].astype(str).str.strip()
        changed = int((before.astype(str) != df[col]).sum())
        if changed:
            log.warning("Trimmed whitespace on %d values in column '%s'.", changed, col)

    log.info("Cleaning complete. Rows: %d -> %d", n_start, len(df))
    return df


def main() -> None:
    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = load_raw(RAW_PATH)
    cleaned = validate_and_clean(df)
    cleaned.to_csv(PROCESSED_PATH, index=False)
    log.info("Wrote cleaned dataset to %s (%d rows)", PROCESSED_PATH, len(cleaned))


if __name__ == "__main__":
    main()
