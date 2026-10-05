"""backend/tests/test_genuine_sales.py

Tests for separating genuine sales from synthetic sample data:
- Database tagging with 'Real · Manual' and 'Real · CSV Import'
- Preservation of sample data with 'Sample Data'
- Bulk CSV import with record validation, duplicate detection, and invalid row reporting
- Sales filtering by source and genuine-only
- Strict separation in forecasting history to avoid misleading forecasts
"""

from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.main import app
from app.models import DailyInventory, DailySales, Product, Store
from app.repositories import inventory_repository, sales_repository
from app.services import forecast_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_sales():
    """Ensure any genuine test sales are cleaned up after each test."""
    yield
    db = SessionLocal()
    try:
        db.execute(delete(DailySales).where(DailySales.source != "Sample Data"))
        # Clean up any test inventory snapshots beyond 2024-01-01
        db.execute(delete(DailyInventory).where(DailyInventory.date > date(2024, 1, 1)))
        db.commit()
        sales_repository.clear_history_cache()
    finally:
        db.close()


def test_manual_sale_marked_real_manual(db):
    """Manually recorded sale must have source='Real · Manual' and be saved in DB."""
    # Ensure current inventory exists
    latest_date = inventory_repository.get_latest_date(db)
    assert latest_date is not None

    payload = {
        "product_id": "P0001",
        "store_id": "S001",
        "units_sold": 2,
        "price": 45.0,
        "category": "Electronics",
        "region": "North",
        "date": latest_date.isoformat(),
    }

    res = client.post("/api/sales/record", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "Real · Manual"

    # Verify directly in database
    record = db.get(DailySales, (latest_date, "S001", "P0001"))
    assert record is not None
    assert record.source == "Real · Manual"


def test_bulk_csv_import_valid_records(db):
    """Bulk CSV import must validate, record 'Real · CSV Import', and persist."""
    csv_data = """date,store_id,product_id,units_sold,price,category,region
2025-02-10,S001,P0001,10,39.99,Electronics,North
2025-02-11,S002,P0002,4,19.99,Toys,South
"""
    res = client.post("/api/sales/bulk-import", json={"csv_content": csv_data})
    assert res.status_code == 200
    body = res.json()
    assert body["total_rows"] == 2
    assert body["imported_count"] == 2
    assert body["duplicates_count"] == 0
    assert body["invalid_count"] == 0
    assert len(body["errors"]) == 0

    # Verify in DB
    row1 = db.get(DailySales, (date(2025, 2, 10), "S001", "P0001"))
    assert row1 is not None
    assert row1.source == "Real · CSV Import"
    assert row1.units_sold == 10

    row2 = db.get(DailySales, (date(2025, 2, 11), "S002", "P0002"))
    assert row2 is not None
    assert row2.source == "Real · CSV Import"
    assert row2.units_sold == 4


def test_bulk_csv_import_duplicate_detection_file_and_db(db):
    """Detects duplicate rows within the same CSV upload and against existing DB records."""
    # First, insert an existing record
    existing_sale = DailySales(
        date=date(2025, 3, 1),
        store_id="S001",
        product_id="P0001",
        category="Electronics",
        region="North",
        units_sold=5,
        price=50.0,
        discount=0,
        holiday_promotion=False,
        weather_condition="Unknown",
        competitor_pricing=50.0,
        seasonality="Unknown",
        demand_forecast_reference=0.0,
        possible_stock_constrained=False,
        source="Real · Manual",
    )
    db.add(existing_sale)
    db.commit()

    # Upload CSV containing:
    # Row 1: duplicate of the existing DB record
    # Row 2: new valid record
    # Row 3: duplicate of Row 2 in this same file
    csv_data = """date,store_id,product_id,units_sold,price,category,region
2025-03-01,S001,P0001,5,50.0,Electronics,North
2025-03-02,S002,P0003,12,25.0,Furniture,East
2025-03-02,S002,P0003,3,25.0,Furniture,East
"""
    res = client.post("/api/sales/bulk-import", json={"csv_content": csv_data})
    assert res.status_code == 200
    body = res.json()
    assert body["total_rows"] == 3
    assert body["imported_count"] == 1  # Only row 2 imported
    assert body["duplicates_count"] == 2
    assert body["invalid_count"] == 0

    duplicate_reasons = [e["reason"] for e in body["errors"] if e["error_type"] == "duplicate"]
    assert any("already exists in database" in r for r in duplicate_reasons)
    assert any("already found in row 2 of this file" in r for r in duplicate_reasons)


def test_bulk_csv_import_validation_and_invalid_row_reporting():
    """Reports invalid rows with exact row numbers and error descriptions."""
    csv_data = """date,store_id,product_id,units_sold,price,category,region,discount
2025-04-01,INVALID_STORE,P0001,5,20.0,Clothing,North,0
2025-04-02,S001,INVALID_PRODUCT,5,20.0,Clothing,North,0
not-a-date,S001,P0001,5,20.0,Clothing,North,0
2025-04-04,S001,P0001,-5,20.0,Clothing,North,0
2025-04-05,S001,P0001,5,-10.0,Clothing,North,0
2025-04-06,S001,P0001,5,20.0,Clothing,North,150
2025-04-07,S001,P0001,8,22.0,Clothing,North,10
"""
    res = client.post("/api/sales/bulk-import", json={"csv_content": csv_data})
    assert res.status_code == 200
    body = res.json()
    assert body["total_rows"] == 7
    assert body["imported_count"] == 1  # Only row 7 is valid
    assert body["invalid_count"] == 6

    error_rows = {e["row"]: e["reason"] for e in body["errors"]}
    assert "Unknown store_id" in error_rows[1]
    assert "Unknown product_id" in error_rows[2]
    assert "Invalid date format" in error_rows[3]
    assert "units_sold must be a positive integer" in error_rows[4]
    assert "price must be >= 0" in error_rows[5]
    assert "discount must be between 0 and 100" in error_rows[6]


def test_sources_summary_endpoint(db):
    """GET /api/sales/sources accurately tallies sample data vs genuine manual and CSV sales."""
    db.add(
        DailySales(
            date=date(2025, 5, 1),
            store_id="S001",
            product_id="P0001",
            category="Toys",
            region="West",
            units_sold=3,
            price=15.0,
            discount=0,
            holiday_promotion=False,
            weather_condition="Sunny",
            competitor_pricing=15.0,
            seasonality="Spring",
            demand_forecast_reference=0.0,
            possible_stock_constrained=False,
            source="Real · Manual",
        )
    )
    db.add(
        DailySales(
            date=date(2025, 5, 2),
            store_id="S002",
            product_id="P0002",
            category="Toys",
            region="West",
            units_sold=7,
            price=25.0,
            discount=0,
            holiday_promotion=False,
            weather_condition="Rainy",
            competitor_pricing=25.0,
            seasonality="Spring",
            demand_forecast_reference=0.0,
            possible_stock_constrained=False,
            source="Real · CSV Import",
        )
    )
    db.commit()

    res = client.get("/api/sales/sources")
    assert res.status_code == 200
    body = res.json()
    assert body["sample_data_count"] == 73100
    assert body["real_manual_count"] >= 1
    assert body["real_csv_import_count"] >= 1
    assert body["genuine_sales_count"] == body["real_manual_count"] + body["real_csv_import_count"]
    assert body["total_sales_count"] == body["sample_data_count"] + body["genuine_sales_count"]


def test_sales_filtering_by_source(db):
    """GET /api/sales respects source and genuine_only query parameters."""
    db.add(
        DailySales(
            date=date(2025, 6, 1),
            store_id="S001",
            product_id="P0001",
            category="Electronics",
            region="North",
            units_sold=9,
            price=100.0,
            discount=0,
            holiday_promotion=False,
            weather_condition="Clear",
            competitor_pricing=100.0,
            seasonality="Summer",
            demand_forecast_reference=0.0,
            possible_stock_constrained=False,
            source="Real · Manual",
        )
    )
    db.add(
        DailySales(
            date=date(2025, 6, 2),
            store_id="S001",
            product_id="P0002",
            category="Electronics",
            region="North",
            units_sold=11,
            price=50.0,
            discount=0,
            holiday_promotion=False,
            weather_condition="Clear",
            competitor_pricing=50.0,
            seasonality="Summer",
            demand_forecast_reference=0.0,
            possible_stock_constrained=False,
            source="Real · CSV Import",
        )
    )
    db.commit()

    # Filter by source="Real · Manual"
    r_man = client.get("/api/sales", params={"source": "Real · Manual"})
    assert r_man.status_code == 200
    assert all(row["source"] == "Real · Manual" for row in r_man.json())

    # Filter by source="Real · CSV Import"
    r_csv = client.get("/api/sales", params={"source": "Real · CSV Import"})
    assert r_csv.status_code == 200
    assert all(row["source"] == "Real · CSV Import" for row in r_csv.json())

    # Filter genuine_only=True
    r_gen = client.get("/api/sales", params={"genuine_only": True})
    assert r_gen.status_code == 200
    assert len(r_gen.json()) >= 2
    assert all(row["source"] in ("Real · Manual", "Real · CSV Import") for row in r_gen.json())

    # Filter source="Sample Data"
    r_samp = client.get("/api/sales", params={"source": "Sample Data", "limit": 10})
    assert r_samp.status_code == 200
    assert all(row["source"] == "Sample Data" for row in r_samp.json())


def test_forecasting_does_not_mix_real_and_synthetic_data(db):
    """Forecasting history query must select only 'Sample Data' so real sales never pollute model features."""
    # Add a real sale with distinct extreme volume
    db.add(
        DailySales(
            date=date(2025, 7, 1),
            store_id="S001",
            product_id="P0001",
            category="Groceries",
            region="East",
            units_sold=99999,
            price=1.0,
            discount=0,
            holiday_promotion=False,
            weather_condition="Stormy",
            competitor_pricing=1.0,
            seasonality="Winter",
            demand_forecast_reference=0.0,
            possible_stock_constrained=False,
            source="Real · Manual",
        )
    )
    db.commit()
    sales_repository.clear_history_cache()

    # Inspect the history DataFrame queried by ML forecasting
    history_df = sales_repository.get_full_history_dataframe(db)

    # 1. Real sale (units_sold=99999, date=2025-07-01) must NOT be present
    assert not any(history_df["Units Sold"] == 99999)
    assert history_df["Date"].max() == date(2024, 1, 1)

    # 2. Test forecast endpoint response includes provenance and baseline warning
    r_fc = client.get("/api/forecast/P0001", params={"horizon": 14})
    assert r_fc.status_code == 200
    fc_data = r_fc.json()
    assert "Synthetic Sample Dataset" in fc_data["data_source"]
    assert fc_data["is_synthetic_model"] is True
    assert "approximately 5%" in fc_data["warning"] or "~5%" in fc_data["warning"]
