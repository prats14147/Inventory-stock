"""
scripts/run_eda.py

Exploratory data analysis on the cleaned dataset. Reads
data/processed/cleaned_inventory.csv (produced by clean_data.py) and writes
charts + a text summary to ml/eda/.

Usage:
    python scripts/run_eda.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_PATH = ROOT / "data" / "processed" / "cleaned_inventory.csv"
EDA_DIR = ROOT / "ml" / "eda"
SUMMARY_PATH = EDA_DIR / "eda_summary.txt"

sns.set_theme(style="whitegrid")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("run_eda")


def savefig(name: str) -> None:
    path = EDA_DIR / name
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    log.info("Saved %s", path)


def dataset_overview(df: pd.DataFrame, lines: list[str]) -> None:
    lines.append("=== DATASET OVERVIEW ===")
    lines.append(f"Shape: {df.shape}")
    lines.append(f"Date range: {df['Date'].min()} to {df['Date'].max()}")
    lines.append(f"Missing values total: {int(df.isna().sum().sum())}")
    lines.append(f"Duplicate rows: {int(df.duplicated().sum())}")
    lines.append("")
    lines.append("Descriptive statistics (numeric columns):")
    lines.append(df.describe().to_string())
    lines.append("")


def product_analysis(df: pd.DataFrame, lines: list[str]) -> None:
    sales_by_product = df.groupby("Product ID")["Units Sold"].sum().sort_values(ascending=False)
    inv_by_product = df.groupby("Product ID")["Inventory Level"].mean().sort_values(ascending=False)

    lines.append("=== PRODUCT ANALYSIS ===")
    lines.append("Top 5 products by total units sold:")
    lines.append(sales_by_product.head(5).to_string())
    lines.append("")

    plt.figure(figsize=(10, 5))
    sales_by_product.plot(kind="bar", color="#4C72B0")
    plt.title("Total Units Sold by Product")
    plt.ylabel("Units Sold")
    plt.xlabel("Product ID")
    savefig("product_total_sales.png")

    plt.figure(figsize=(10, 5))
    inv_by_product.plot(kind="bar", color="#55A868")
    plt.title("Average Inventory Level by Product")
    plt.ylabel("Avg Inventory Level")
    plt.xlabel("Product ID")
    savefig("product_avg_inventory.png")

    plt.figure(figsize=(8, 5))
    sns.histplot(df["Units Sold"], bins=40, kde=True, color="#C44E52")
    plt.title("Distribution of Units Sold (all rows)")
    savefig("sales_distribution.png")


def category_analysis(df: pd.DataFrame, lines: list[str]) -> None:
    sales_by_cat = df.groupby("Category")["Units Sold"].sum().sort_values(ascending=False)
    inv_by_cat = df.groupby("Category")["Inventory Level"].mean().sort_values(ascending=False)

    lines.append("=== CATEGORY ANALYSIS ===")
    lines.append("Total units sold by category:")
    lines.append(sales_by_cat.to_string())
    lines.append("")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    sales_by_cat.plot(kind="bar", ax=axes[0], color="#4C72B0")
    axes[0].set_title("Total Sales by Category")
    inv_by_cat.plot(kind="bar", ax=axes[1], color="#55A868")
    axes[1].set_title("Avg Inventory by Category")
    savefig("category_sales_inventory.png")


def store_analysis(df: pd.DataFrame, lines: list[str]) -> None:
    sales_by_store = df.groupby("Store ID")["Units Sold"].sum().sort_values(ascending=False)
    inv_by_store = df.groupby("Store ID")["Inventory Level"].mean().sort_values(ascending=False)

    lines.append("=== STORE ANALYSIS ===")
    lines.append("Total units sold by store:")
    lines.append(sales_by_store.to_string())
    lines.append("")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    sales_by_store.plot(kind="bar", ax=axes[0], color="#4C72B0")
    axes[0].set_title("Total Sales by Store")
    inv_by_store.plot(kind="bar", ax=axes[1], color="#55A868")
    axes[1].set_title("Avg Inventory by Store")
    savefig("store_sales_inventory.png")


def time_analysis(df: pd.DataFrame, lines: list[str]) -> None:
    daily = df.groupby("Date")["Units Sold"].sum()
    weekly = daily.resample("W").sum()
    monthly = daily.resample("ME").sum()
    inv_daily = df.groupby("Date")["Inventory Level"].mean()

    lines.append("=== TIME ANALYSIS ===")
    lines.append(f"Daily sales -- mean: {daily.mean():.1f}, std: {daily.std():.1f}")
    lines.append(f"Monthly sales -- mean: {monthly.mean():.1f}, std: {monthly.std():.1f}")
    lines.append("")

    plt.figure(figsize=(12, 5))
    daily.plot(alpha=0.4, label="Daily")
    weekly.plot(label="Weekly")
    plt.title("Sales Over Time (Daily & Weekly)")
    plt.ylabel("Units Sold")
    plt.legend()
    savefig("sales_over_time_daily_weekly.png")

    plt.figure(figsize=(12, 5))
    monthly.plot(kind="bar", color="#4C72B0")
    plt.title("Monthly Sales")
    plt.ylabel("Units Sold")
    savefig("sales_over_time_monthly.png")

    plt.figure(figsize=(12, 5))
    inv_daily.plot(color="#55A868")
    plt.title("Average Inventory Level Over Time")
    plt.ylabel("Avg Inventory Level")
    savefig("inventory_over_time.png")


def relationship_analysis(df: pd.DataFrame, lines: list[str]) -> None:
    lines.append("=== RELATIONSHIPS ===")
    corr = df[["Inventory Level", "Units Sold", "Price", "Discount"]].corr()
    lines.append("Correlation matrix (Inventory, Units Sold, Price, Discount):")
    lines.append(corr.to_string())
    lines.append("")

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    sample = df.sample(min(5000, len(df)), random_state=42)

    axes[0, 0].scatter(sample["Inventory Level"], sample["Units Sold"], alpha=0.2, s=8)
    axes[0, 0].set_xlabel("Inventory Level")
    axes[0, 0].set_ylabel("Units Sold")
    axes[0, 0].set_title("Inventory vs Sales")

    axes[0, 1].scatter(sample["Price"], sample["Units Sold"], alpha=0.2, s=8, color="#C44E52")
    axes[0, 1].set_xlabel("Price")
    axes[0, 1].set_ylabel("Units Sold")
    axes[0, 1].set_title("Price vs Sales")

    axes[1, 0].scatter(sample["Discount"], sample["Units Sold"], alpha=0.2, s=8, color="#55A868")
    axes[1, 0].set_xlabel("Discount")
    axes[1, 0].set_ylabel("Units Sold")
    axes[1, 0].set_title("Discount vs Sales")

    promo_sales = df.groupby("Holiday/Promotion")["Units Sold"].mean()
    axes[1, 1].bar(["No Promotion", "Promotion"], promo_sales.values, color="#8172B2")
    axes[1, 1].set_title("Avg Sales: Promotion vs No Promotion")

    savefig("relationships_grid.png")


def main() -> None:
    EDA_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(PROCESSED_PATH, parse_dates=["Date"])
    log.info("Loaded cleaned dataset: %d rows", len(df))

    lines: list[str] = []
    dataset_overview(df, lines)
    product_analysis(df, lines)
    category_analysis(df, lines)
    store_analysis(df, lines)
    time_analysis(df, lines)
    relationship_analysis(df, lines)

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote EDA summary to %s", SUMMARY_PATH)


if __name__ == "__main__":
    main()
