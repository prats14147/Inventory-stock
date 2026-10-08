"""backend/app/routers/sales.py"""

import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DailyInventory, DailySales, Product, Store
from app.models.stock_movement import StockMovement, SALE
from app.schemas.stock_movement import StockMovementResponse
from app.repositories import inventory_repository, sales_repository
from app.schemas.sales import (
    BulkImportRequest,
    BulkImportResponse,
    CloseSalesDayRequest,
    CloseSalesDayResponse,
    SalesDayCoverageResponse,
    CategorySalesSummary,
    CsvRowError,
    DailySaleRow,
    RecordSaleRequest,
    RecordSaleResponse,
    SalesSourcesSummaryResponse,
    SalesTrendResponse,
    StoreSalesSummary,
    TopProductsResponse,
)
from app.services import sales_service
from app.services.errors import InvalidRequestError, NotFoundError
from app.repositories.sales_repository import clear_history_cache
from app.services.stockout_service import clear_risk_cache


router = APIRouter(prefix="/api/sales", tags=["sales"])


@router.post("/close-day", response_model=CloseSalesDayResponse)
def close_sales_day(payload: CloseSalesDayRequest, db: Session = Depends(get_db)):
    """Confirm that all sales for a store and business date have been entered."""
    return sales_service.close_sales_day(db, payload)


@router.get("/day-coverage", response_model=SalesDayCoverageResponse)
def sales_day_coverage(db: Session = Depends(get_db)):
    """Show how many verified complete sales days are available per store."""
    return sales_service.get_sales_day_coverage(db)


@router.post("/record", response_model=RecordSaleResponse)
def record_sale(payload: RecordSaleRequest, db: Session = Depends(get_db)):
    """Record a sale through the shared, cost-aware inventory service."""
    return sales_service.record_sale(db, payload)


@router.post("/bulk-import", response_model=BulkImportResponse)
def bulk_import_sales(payload: BulkImportRequest, db: Session = Depends(get_db)):
    """Bulk import sales from CSV or structured rows, validating records and detecting duplicates."""
    raw_rows: list[dict] = []
    if payload.csv_content:
        content = payload.csv_content.strip()
        if content:
            if content.startswith("\ufeff"):
                content = content[1:]
            reader = csv.DictReader(io.StringIO(content))
            for r in reader:
                raw_rows.append(r)
    elif payload.rows:
        raw_rows = payload.rows
    else:
        raise InvalidRequestError("No CSV content or rows provided for bulk import.")

    if not raw_rows:
        return BulkImportResponse(
            total_rows=0,
            imported_count=0,
            duplicates_count=0,
            invalid_count=0,
            errors=[],
        )

    # Preload valid dimension entities
    valid_stores = set(db.execute(select(Store.store_id)).scalars().all())
    valid_products = set(db.execute(select(Product.product_id)).scalars().all())

    seen_batch_keys: dict[tuple[date, str, str], int] = {}
    errors: list[CsvRowError] = []
    valid_records: list[DailySales] = []

    def _normalize(k: str) -> str:
        return k.strip().lower().replace(" ", "_").replace("/", "_").replace("-", "_")

    for idx, raw in enumerate(raw_rows, start=1):
        # Normalize keys in row
        row_dict = {_normalize(k): v for k, v in raw.items() if k is not None}

        # Date extraction & validation
        raw_date = row_dict.get("date") or row_dict.get("sale_date") or row_dict.get("date_sold")
        if not raw_date or str(raw_date).strip() == "":
            errors.append(CsvRowError(row=idx, reason="Missing required field 'date'", error_type="validation"))
            continue

        try:
            date_str = str(raw_date).strip()
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            sale_date = date.fromisoformat(date_str)
        except Exception:
            try:
                sale_date = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
            except Exception:
                errors.append(CsvRowError(row=idx, reason=f"Invalid date format '{raw_date}'. Expected YYYY-MM-DD.", error_type="validation"))
                continue

        # Store ID validation
        store_id = row_dict.get("store_id") or row_dict.get("store")
        if not store_id or str(store_id).strip() == "":
            errors.append(CsvRowError(row=idx, reason="Missing required field 'store_id'", error_type="validation"))
            continue
        store_id = str(store_id).strip()
        if valid_stores and store_id not in valid_stores:
            errors.append(CsvRowError(row=idx, key=f"Store:{store_id}", reason=f"Unknown store_id '{store_id}'. Valid stores are: {', '.join(sorted(valid_stores))}", error_type="validation"))
            continue

        # Product ID validation
        product_id = row_dict.get("product_id") or row_dict.get("product")
        if not product_id or str(product_id).strip() == "":
            errors.append(CsvRowError(row=idx, reason="Missing required field 'product_id'", error_type="validation"))
            continue
        product_id = str(product_id).strip()
        if valid_products and product_id not in valid_products:
            errors.append(CsvRowError(row=idx, key=f"Product:{product_id}", reason=f"Unknown product_id '{product_id}'. Valid products exist in inventory.", error_type="validation"))
            continue

        # Units sold validation
        raw_units = row_dict.get("units_sold") or row_dict.get("units") or row_dict.get("quantity") or row_dict.get("qty")
        if raw_units is None or str(raw_units).strip() == "":
            errors.append(CsvRowError(row=idx, reason="Missing required field 'units_sold'", error_type="validation"))
            continue
        try:
            units_sold = int(float(str(raw_units).strip()))
            if units_sold <= 0:
                errors.append(CsvRowError(row=idx, reason=f"units_sold must be a positive integer (> 0), got {units_sold}", error_type="validation"))
                continue
        except (ValueError, TypeError):
            errors.append(CsvRowError(row=idx, reason=f"Invalid units_sold '{raw_units}'. Must be an integer.", error_type="validation"))
            continue

        # Price validation
        raw_price = row_dict.get("price") or row_dict.get("unit_price")
        if raw_price is None or str(raw_price).strip() == "":
            errors.append(CsvRowError(row=idx, reason="Missing required field 'price'", error_type="validation"))
            continue
        try:
            price = float(str(raw_price).strip())
            if price < 0:
                errors.append(CsvRowError(row=idx, reason=f"price must be >= 0, got {price}", error_type="validation"))
                continue
        except (ValueError, TypeError):
            errors.append(CsvRowError(row=idx, reason=f"Invalid price '{raw_price}'. Must be a valid number.", error_type="validation"))
            continue

        # Discount validation (optional)
        raw_discount = row_dict.get("discount")
        discount = 0
        if raw_discount is not None and str(raw_discount).strip() != "":
            try:
                discount = int(float(str(raw_discount).strip()))
                if not (0 <= discount <= 100):
                    errors.append(CsvRowError(row=idx, reason=f"discount must be between 0 and 100, got {discount}", error_type="validation"))
                    continue
            except (ValueError, TypeError):
                errors.append(CsvRowError(row=idx, reason=f"Invalid discount '{raw_discount}'. Must be an integer between 0 and 100.", error_type="validation"))
                continue

        # Holiday / promotion (optional)
        raw_holiday = row_dict.get("holiday_promotion") or row_dict.get("holiday") or row_dict.get("promotion")
        holiday_promotion = False
        if raw_holiday is not None:
            s_hol = str(raw_holiday).strip().lower()
            holiday_promotion = s_hol in ("1", "true", "yes", "t", "y")

        # Competitor pricing (optional)
        raw_comp = row_dict.get("competitor_pricing") or row_dict.get("competitor_price")
        competitor_pricing = price
        if raw_comp is not None and str(raw_comp).strip() != "":
            try:
                competitor_pricing = float(str(raw_comp).strip())
                if competitor_pricing < 0:
                    competitor_pricing = price
            except (ValueError, TypeError):
                competitor_pricing = price

        # Text attributes (category, region, weather, seasonality)
        category = str(row_dict.get("category") or "Uncategorized").strip() or "Uncategorized"
        region = str(row_dict.get("region") or "Unassigned").strip() or "Unassigned"
        weather_condition = str(row_dict.get("weather_condition") or row_dict.get("weather") or "Unknown").strip() or "Unknown"
        seasonality = str(row_dict.get("seasonality") or "Unknown").strip() or "Unknown"

        # Duplicate checking
        record_key = (sale_date, store_id, product_id)

        # 1. Duplicate within this upload file
        if record_key in seen_batch_keys:
            prev_row = seen_batch_keys[record_key]
            errors.append(
                CsvRowError(
                    row=idx,
                    key=f"{sale_date} · {store_id} · {product_id}",
                    reason=f"Duplicate entry: same date, store, and product was already found in row {prev_row} of this file.",
                    error_type="duplicate",
                )
            )
            continue
        seen_batch_keys[record_key] = idx

        # 2. Duplicate against database
        existing_record = db.get(DailySales, record_key)
        if existing_record is not None:
            errors.append(
                CsvRowError(
                    row=idx,
                    key=f"{sale_date} · {store_id} · {product_id}",
                    reason=f"Duplicate entry: record for ({sale_date}, {store_id}, {product_id}) already exists in database with source '{existing_record.source}'.",
                    error_type="duplicate",
                )
            )
            continue

        valid_records.append(
            DailySales(
                date=sale_date,
                store_id=store_id,
                product_id=product_id,
                category=category,
                region=region,
                units_sold=units_sold,
                price=price,
                discount=discount,
                holiday_promotion=holiday_promotion,
                weather_condition=weather_condition,
                competitor_pricing=competitor_pricing,
                seasonality=seasonality,
                demand_forecast_reference=0.0,
                possible_stock_constrained=False,
                source="Real · CSV Import",
            )
        )

    if valid_records:
        db.add_all(valid_records)
        db.commit()
        clear_history_cache()
        clear_risk_cache()

    duplicates_count = sum(1 for e in errors if e.error_type == "duplicate")
    invalid_count = sum(1 for e in errors if e.error_type == "validation")

    return BulkImportResponse(
        total_rows=len(raw_rows),
        imported_count=len(valid_records),
        duplicates_count=duplicates_count,
        invalid_count=invalid_count,
        errors=errors,
    )


@router.get("/sources", response_model=SalesSourcesSummaryResponse)
def sales_sources_summary(db: Session = Depends(get_db)):
    """Breakdown of total sales between sample data and genuine real sales."""
    return sales_repository.get_sales_sources_summary(db)
@router.get(
    "/stock-movements",
    response_model=list[StockMovementResponse],
)
def list_stock_movements(
    store_id: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return stock movement history, newest first."""

    query = select(StockMovement).order_by(
        StockMovement.occurred_at.desc()
    )

    if store_id:
        query = query.where(StockMovement.store_id == store_id)

    if product_id:
        query = query.where(StockMovement.product_id == product_id)

    if movement_type:
        query = query.where(StockMovement.movement_type == movement_type)

    return db.scalars(query).all()

@router.get("", response_model=list[DailySaleRow])
def list_sales(
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = Query(None, description="Filter by source e.g. 'Real · Manual', 'Real · CSV Import', or 'Sample Data'"),
    genuine_only: bool = Query(False, description="Filter to only genuine sales (Real · Manual and Real · CSV Import)"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Number of rows to skip"),
    db: Session = Depends(get_db),
):
    rows = sales_repository.get_sales_rows(
        db,
        product_id=product_id,
        store_id=store_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
        source=source,
        genuine_only=genuine_only,
        limit=limit,
        offset=offset,
    )

    return [DailySaleRow.model_validate(r) for r in rows]


@router.get("/top-products", response_model=TopProductsResponse)
def top_products(
    limit: int = Query(10, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
    db: Session = Depends(get_db),
):
    return sales_service.get_top_products(
        db,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        source=source,
        genuine_only=genuine_only,
    )


@router.get("/bottom-products", response_model=TopProductsResponse)
def bottom_products(
    limit: int = Query(10, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
    db: Session = Depends(get_db),
):
    return sales_service.get_bottom_products(
        db,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        source=source,
        genuine_only=genuine_only,
    )


@router.get("/trends", response_model=SalesTrendResponse)
def trends(
    granularity: str = Query(
        "daily",
        pattern="^(daily|weekly|monthly)$",
    ),
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    genuine_only: bool = False,
    db: Session = Depends(get_db),
):
    return sales_service.get_sales_trend(
        db,
        granularity=granularity,
        product_id=product_id,
        store_id=store_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
        source=source,
        genuine_only=genuine_only,
    )


@router.get(
    "/by-category",
    response_model=list[CategorySalesSummary],
)
def by_category(
    source: str | None = None,
    genuine_only: bool = False,
    db: Session = Depends(get_db),
):
    return sales_service.get_category_analysis(
        db, source=source, genuine_only=genuine_only
    )


@router.get(
    "/by-store",
    response_model=list[StoreSalesSummary],
)
def by_store(
    source: str | None = None,
    genuine_only: bool = False,
    db: Session = Depends(get_db),
):
    return sales_service.get_store_analysis(
        db, source=source, genuine_only=genuine_only
    )


@router.get("/profitability/by-store")
def profitability_by_store(
    store_id: str | None = None,
    product_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_store_profitability(
        db, store_id=store_id, product_id=product_id, category=category,
        start_date=start_date, end_date=end_date,
    )


@router.get("/profitability")
def profitability(
    group_by: str = "total",
    sort_order: str = "descending",
    store_id: str | None = None,
    product_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    return sales_service.get_profitability_analysis(
        db, group_by=group_by, sort_order=sort_order, store_id=store_id,
        product_id=product_id, category=category, start_date=start_date,
        end_date=end_date,
    )


@router.get("/export/csv")
def export_sales_csv(
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = Query(None, description="Filter by source"),
    genuine_only: bool = Query(False, description="Filter to only genuine sales"),
    db: Session = Depends(get_db),
):
    """Export sales records as CSV."""
    rows = sales_repository.get_sales_rows(
        db,
        product_id=product_id,
        store_id=store_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
        source=source,
        genuine_only=genuine_only,
    )

    import csv
    import io
    from fastapi.responses import StreamingResponse

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Store ID", "Product ID", "Category", "Region",
        "Units Sold", "Price", "Discount", "Holiday/Promotion",
        "Weather Condition", "Competitor Pricing", "Seasonality",
        "Demand Forecast Reference", "Possible Stock Constrained", "Source"
    ])
    for r in rows:
        writer.writerow([
            r.date, r.store_id, r.product_id, r.category, r.region,
            r.units_sold, r.price, r.discount, r.holiday_promotion,
            r.weather_condition, r.competitor_pricing, r.seasonality,
            r.demand_forecast_reference, r.possible_stock_constrained, r.source
        ])

    output.seek(0)
    filename = f"sales_export_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
