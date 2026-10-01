"""backend/tests/test_sales_service.py"""

import pytest

from app.services import sales_service
from app.services.errors import InvalidRequestError, NotFoundError


def test_top_products_matches_reference(db, reference_df):
    expected = (
        reference_df.groupby("Product ID")["Units Sold"].sum().sort_values(ascending=False).head(5)
    )
    result = sales_service.get_top_products(db, limit=5)

    assert [p.product_id for p in result.products] == list(expected.index)
    assert [p.total_units_sold for p in result.products] == list(expected.values)


def test_bottom_products_matches_reference(db, reference_df):
    expected = (
        reference_df.groupby("Product ID")["Units Sold"].sum().sort_values(ascending=True).head(5)
    )
    result = sales_service.get_bottom_products(db, limit=5)

    assert [p.product_id for p in result.products] == list(expected.index)


def test_sales_trend_monthly_has_25_months(db):
    # 2022-01-01 to 2024-01-01 inclusive spans 25 calendar months
    result = sales_service.get_sales_trend(db, granularity="monthly")
    assert len(result.points) == 25


def test_sales_trend_daily_total_matches_reference(db, reference_df):
    result = sales_service.get_sales_trend(db, granularity="daily")
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
    result = sales_service.get_category_analysis(db)

    assert [c.category for c in result] == list(expected.index)
    assert [c.total_units_sold for c in result] == list(expected.values)


def test_store_analysis_matches_reference(db, reference_df):
    expected = reference_df.groupby("Store ID")["Units Sold"].sum().sort_values(ascending=False)
    result = sales_service.get_store_analysis(db)

    assert [s.store_id for s in result] == list(expected.index)
    assert [s.total_units_sold for s in result] == list(expected.values)
