"""backend/tests/test_inventory_service.py"""

import pytest

from app.services import inventory_service
from app.services.errors import NotFoundError


def test_get_product_inventory_matches_reference(db, reference_df):
    product_id = "P0001"
    latest_date = reference_df["Date"].max()

    expected_total = reference_df[
        (reference_df["Product ID"] == product_id) & (reference_df["Date"] == latest_date)
    ]["Inventory Level"].sum()

    result = inventory_service.get_product_inventory(db, product_id)

    assert result.product_id == product_id
    assert result.as_of_date == latest_date.date()
    assert result.total_inventory == expected_total
    assert len(result.stores) == 5  # 5 stores in this dataset


def test_get_product_inventory_not_found(db):
    with pytest.raises(NotFoundError):
        inventory_service.get_product_inventory(db, "P9999")


def test_low_stock_matches_reference(db, reference_df):
    threshold = 50
    latest_date = reference_df["Date"].max()
    expected_count = (
        (reference_df["Date"] == latest_date) & (reference_df["Inventory Level"] < threshold)
    ).sum()

    result = inventory_service.get_low_stock(db, threshold=threshold)

    assert result.threshold == threshold
    assert result.count == expected_count
    assert len(result.items) == expected_count
    # every returned item should actually be below the threshold
    assert all(item.inventory_level < threshold for item in result.items)


def test_low_stock_default_threshold_from_settings(db):
    result = inventory_service.get_low_stock(db)
    assert result.threshold == 50  # matches .env.example / config default
