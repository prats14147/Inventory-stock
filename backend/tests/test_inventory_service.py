"""backend/tests/test_inventory_service.py"""

import uuid
from datetime import date

import pytest

from app.models.inventory import DailyInventory
from app.models.product import Product
from app.models.sales import SalesTransaction
from app.models.stock_movement import DELIVERY, MANUAL_CORRECTION, StockMovement
from app.models.store import Store
from app.repositories import inventory_repository
from app.schemas.inventory import StockAdjustmentRequest
from app.services import inventory_service
from app.services.errors import InvalidRequestError, NotFoundError


def test_get_product_inventory_matches_reference(db, reference_df):
    product_id = "P0001"
    latest_date = reference_df["Date"].max()

    expected_total = reference_df[
        (reference_df["Product ID"] == product_id) & (reference_df["Date"] == latest_date)
    ]["Inventory Level"].sum()

    result = inventory_service.get_product_inventory(db, product_id, as_of=latest_date.date())

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

    result = inventory_service.get_low_stock(db, threshold=threshold, as_of=latest_date.date())

    assert result.threshold == threshold
    assert result.count == expected_count
    assert len(result.items) == expected_count
    # every returned item should actually be below the threshold
    assert all(item.inventory_level < threshold for item in result.items)


def test_delivery_and_damage_adjustments_change_stock_without_recording_sales(db, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    product_id, store_id = f"T{suffix}", f"T{suffix}"
    as_of = inventory_repository.get_latest_date(db) or date.today()
    db.add_all([Product(product_id=product_id), Store(store_id=store_id)])
    stock = DailyInventory(date=as_of, store_id=store_id, product_id=product_id,
                           inventory_level=10, units_ordered=30, category="Testing", region="Test")
    db.add(stock)
    db.flush()
    # The application service normally commits. Keep this test's changes in
    # the fixture transaction so closing the session rolls them back.
    monkeypatch.setattr(db, "commit", lambda: db.flush())

    received = inventory_service.adjust_stock(db, StockAdjustmentRequest(
        product_id=product_id, store_id=store_id, movement_type=DELIVERY,
        quantity_delta=20, reason="Stock received",
    ))
    damaged = inventory_service.adjust_stock(db, StockAdjustmentRequest(
        product_id=product_id, store_id=store_id, movement_type=MANUAL_CORRECTION,
        quantity_delta=-2, reason="Damaged goods",
    ))

    assert received.quantity_after == 30
    db.refresh(stock)
    assert stock.units_ordered == 10
    assert damaged.quantity_after == 28
    assert db.query(StockMovement).filter_by(product_id=product_id).count() == 2
    assert db.query(SalesTransaction).filter_by(product_id=product_id).count() == 0
    with pytest.raises(InvalidRequestError):
        inventory_service.adjust_stock(db, StockAdjustmentRequest(
            product_id=product_id, store_id=store_id, movement_type=MANUAL_CORRECTION,
            quantity_delta=-100, reason="Exceeds available stock",
        ))
    with pytest.raises(InvalidRequestError, match="Only 10 units are currently ordered"):
        inventory_service.adjust_stock(db, StockAdjustmentRequest(
            product_id=product_id, store_id=store_id, movement_type=DELIVERY,
            quantity_delta=11, reason="Exceeds outstanding order",
        ))
    db.refresh(stock)
    assert stock.inventory_level == 28
    assert stock.units_ordered == 10


def test_low_stock_default_threshold_from_settings(db):
    result = inventory_service.get_low_stock(db)
    assert result.threshold == 50  # matches .env.example / config default
