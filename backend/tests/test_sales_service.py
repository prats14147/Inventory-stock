"""backend/tests/test_sales_service.py"""

import uuid
from datetime import date

import pytest

from app.models.product import Product
from app.models.sales import SalesTransaction
from app.models.store import Store
from app.services import sales_service
from app.services.errors import InvalidRequestError, NotFoundError


def test_top_products_matches_reference(db, reference_df):
    start_date = reference_df["Date"].min().date()
    end_date = reference_df["Date"].max().date()
    expected = (
        reference_df.groupby("Product ID")["Units Sold"].sum().sort_values(ascending=False).head(5)
    )
    result = sales_service.get_top_products(db, limit=5, start_date=start_date, end_date=end_date)

    assert [p.product_id for p in result.products] == list(expected.index)
    assert [p.total_units_sold for p in result.products] == list(expected.values)


def test_bottom_products_matches_reference(db, reference_df):
    start_date = reference_df["Date"].min().date()
    end_date = reference_df["Date"].max().date()
    expected = (
        reference_df.groupby("Product ID")["Units Sold"].sum().sort_values(ascending=True).head(5)
    )
    result = sales_service.get_bottom_products(db, limit=5, start_date=start_date, end_date=end_date)

    assert [p.product_id for p in result.products] == list(expected.index)


def test_sales_trend_monthly_has_25_months(db):
    # 2022-01-01 to 2024-01-01 inclusive spans 25 calendar months
    result = sales_service.get_sales_trend(db, granularity="monthly", start_date=date(2022, 1, 1), end_date=date(2024, 1, 1))
    assert len(result.points) == 25


def test_sales_trend_daily_total_matches_reference(db, reference_df):
    result = sales_service.get_sales_trend(db, granularity="daily", start_date=reference_df["Date"].min().date(), end_date=reference_df["Date"].max().date())
    total_from_service = sum(p.total_units_sold for p in result.points)
    total_from_reference = int(reference_df["Units Sold"].sum())
    assert total_from_service == total_from_reference


def test_sales_trend_invalid_granularity(db):
    with pytest.raises(InvalidRequestError):
        sales_service.get_sales_trend(db, granularity="yearly")


def test_sales_trend_invalid_date_range(db):
    with pytest.raises(InvalidRequestError):
        sales_service.get_sales_trend(db, start_date="2023-06-01", end_date="2023-01-01")


def test_sales_trend_unknown_product(db):
    with pytest.raises(NotFoundError):
        sales_service.get_sales_trend(db, product_id="P9999")


def test_category_analysis_matches_reference(db, reference_df):
    expected = reference_df.groupby("Category")["Units Sold"].sum().sort_values(ascending=False)
    result = sales_service.get_category_analysis(db, start_date=reference_df["Date"].min().date(), end_date=reference_df["Date"].max().date())

    assert [c.category for c in result] == list(expected.index)
    assert [c.total_units_sold for c in result] == list(expected.values)


def test_store_analysis_matches_reference(db, reference_df):
    expected = reference_df.groupby("Store ID")["Units Sold"].sum().sort_values(ascending=False)
    result = sales_service.get_store_analysis(db, start_date=reference_df["Date"].min().date(), end_date=reference_df["Date"].max().date())

    assert [s.store_id for s in result] == list(expected.index)
    assert [s.total_units_sold for s in result] == list(expected.values)


def test_profitability_calculates_total_and_product_group_without_committing(db):
    suffix = uuid.uuid4().hex[:8]
    product_id, losing_product_id, store_id = f"T{suffix}", f"L{suffix}", f"T{suffix}"
    db.add_all([Product(product_id=product_id), Product(product_id=losing_product_id), Store(store_id=store_id)])
    db.flush()
    db.add(SalesTransaction(
        business_date=date.today(), store_id=store_id,
        product_id=product_id, category="Testing", units_sold=2,
        unit_price=100, discount_percent=0, unit_cost=50,
    ))
    db.add(SalesTransaction(
        business_date=date.today(), store_id=store_id,
        product_id=losing_product_id, category="Testing", units_sold=2,
        unit_price=20, discount_percent=0, unit_cost=50,
    ))
    db.flush()

    total = sales_service.get_profitability_analysis(db, group_by="total", product_id=product_id)
    grouped = sales_service.get_profitability_analysis(db, group_by="product", store_id=store_id, sort_order="ascending")

    assert total["items"][0]["gross_profit_or_loss"] == 100
    assert total["items"][0]["gross_margin_percent"] == 50
    assert total["items"][0]["known_cost_of_goods_sold"] == 100
    assert grouped["items"][0]["product_id"] == losing_product_id
    assert grouped["items"][0]["gross_profit_or_loss"] == -60
    assert grouped["items"][-1]["product_id"] == product_id
