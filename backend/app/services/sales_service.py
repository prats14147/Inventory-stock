"""backend/app/services/sales_service.py"""

from datetime import date, datetime

from sqlalchemy import case, func, literal, select
from sqlalchemy.orm import Session

from app.models import DailyInventory, DailySales, Product
from app.models.stock_movement import StockMovement, SALE
from app.models.sales import SalesTransaction
from app.repositories import product_repository, sales_repository
from app.repositories import inventory_repository
from app.schemas.sales import (
    CategorySalesSummary,
    ProductSalesRank,
    SalesListResponse,
    SalesRecord,
    SalesTrendPoint,
    SalesTrendResponse,
    StoreSalesSummary,
    TopProductsResponse,
    RecordSaleRequest,
    RecordSaleResponse,
)
from app.services.errors import InvalidRequestError, NotFoundError
from app.repositories.sales_repository import clear_history_cache
from app.services.stockout_service import clear_risk_cache

VALID_GRANULARITIES = {"daily", "weekly", "monthly"}
MAX_LIMIT = 1000


def record_sale(db: Session, payload: RecordSaleRequest) -> RecordSaleResponse:
    """Record a sale and deduct stock; shared by REST and confirmed chat actions."""
    latest_date = inventory_repository.get_latest_date(db)
    if latest_date is None:
        raise NotFoundError("No inventory exists yet. Add product stock before recording a sale.")
    sale_date = payload.date or date.today()
    if sale_date < latest_date:
        raise InvalidRequestError(f"Sales must be recorded on or after the latest inventory date ({latest_date}).")
    if sale_date > latest_date:
        for old in inventory_repository.get_all_current_inventory(db, as_of=latest_date):
            db.add(DailyInventory(date=sale_date, store_id=old["store_id"], product_id=old["product_id"],
                                  inventory_level=old["inventory_level"], units_ordered=old["units_ordered"],
                                  category=old["category"], region=old["region"]))
        db.flush()
    stock = db.get(DailyInventory, (sale_date, payload.store_id, payload.product_id))
    if stock is None:
        raise NotFoundError(f"No stock record exists for product {payload.product_id} at store {payload.store_id}.")
    if payload.units_sold > stock.inventory_level:
        raise InvalidRequestError(f"Only {stock.inventory_level} units are on hand; the sale quantity is {payload.units_sold}.")
    opening_stock = stock.inventory_level
    stock.inventory_level -= payload.units_sold
    stock.category, stock.region = payload.category, payload.region
    db.add(StockMovement(occurred_at=datetime.now(), business_date=sale_date, store_id=payload.store_id,
                         product_id=payload.product_id, movement_type=SALE, quantity_delta=-payload.units_sold,
                         quantity_before=opening_stock, quantity_after=stock.inventory_level,
                         reason="Customer sale", source="sales"))
    sale = db.get(DailySales, (sale_date, payload.store_id, payload.product_id))
    product = db.get(Product, payload.product_id)
    unit_cost = payload.unit_cost if payload.unit_cost is not None else (product.cost_price if product else None)
    db.add(SalesTransaction(
        occurred_at=datetime.now(), business_date=sale_date, store_id=payload.store_id,
        product_id=payload.product_id, category=payload.category, units_sold=payload.units_sold, unit_price=payload.price,
        discount_percent=payload.discount, unit_cost=unit_cost,
    ))
    if sale is None:
        daily_total = payload.units_sold
        db.add(DailySales(date=sale_date, store_id=payload.store_id, product_id=payload.product_id,
                          category=payload.category, region=payload.region, units_sold=payload.units_sold,
                          price=payload.price, discount=payload.discount, holiday_promotion=payload.holiday_promotion,
                          weather_condition=payload.weather_condition,
                          competitor_pricing=payload.competitor_pricing if payload.competitor_pricing is not None else payload.price,
                          seasonality=payload.seasonality, demand_forecast_reference=0.0,
                          possible_stock_constrained=payload.units_sold >= opening_stock))
    else:
        daily_total = sale.units_sold + payload.units_sold
        sale.price = ((sale.price * sale.units_sold) + (payload.price * payload.units_sold)) / daily_total
        sale.discount = round(((sale.discount * sale.units_sold) + (payload.discount * payload.units_sold)) / daily_total)
        sale.units_sold = daily_total
        sale.category, sale.region = payload.category, payload.region
        sale.holiday_promotion = sale.holiday_promotion or payload.holiday_promotion
        sale.weather_condition = payload.weather_condition
        sale.competitor_pricing = payload.competitor_pricing if payload.competitor_pricing is not None else payload.price
        sale.seasonality = payload.seasonality
        sale.possible_stock_constrained = sale.possible_stock_constrained or payload.units_sold >= opening_stock
    db.commit()
    clear_history_cache()
    clear_risk_cache()
    return RecordSaleResponse(date=sale_date, product_id=payload.product_id, store_id=payload.store_id,
                              units_sold=payload.units_sold, daily_units_sold=daily_total,
                              remaining_inventory=stock.inventory_level, unit_cost=unit_cost,
                              gross_profit=(round(payload.units_sold * (payload.price * (1 - payload.discount / 100) - unit_cost), 2)
                                            if unit_cost is not None else None))


def get_revenue_analysis(
    db: Session,
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    group_by: str | None = None,
    sort_order: str = "descending",
) -> dict:
    """Calculate recorded net sales after percentage discounts (not profit)."""
    _validate_date_range(start_date, end_date)
    if product_id and not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")
    net_line_value = DailySales.units_sold * DailySales.price * (1 - DailySales.discount / 100.0)
    gross_line_value = DailySales.units_sold * DailySales.price
    group_columns = {"product": DailySales.product_id, "store": DailySales.store_id, "category": DailySales.category}
    group_column = group_columns.get(group_by) if group_by else None
    if group_by and group_column is None:
        raise InvalidRequestError("group_by must be product, store, or category.")
    if sort_order not in {"ascending", "descending"}:
        raise InvalidRequestError("sort_order must be ascending or descending.")
    base_select = [
        func.coalesce(func.sum(net_line_value), 0.0),
        func.coalesce(func.sum(gross_line_value), 0.0),
        func.count(),
    ]
    stmt = select(*(([group_column.label("group_value")] if group_column is not None else []) + base_select))
    if product_id:
        stmt = stmt.where(DailySales.product_id == product_id)
    if store_id:
        stmt = stmt.where(DailySales.store_id == store_id)
    if category:
        stmt = stmt.where(DailySales.category == category)
    if start_date:
        stmt = stmt.where(DailySales.date >= start_date)
    if end_date:
        stmt = stmt.where(DailySales.date <= end_date)
    if group_column is not None:
        stmt = stmt.group_by(group_column)
        grouped_rows = db.execute(stmt).all()
        key_field = {"product": "product_id", "store": "store_id", "category": "category"}[group_by]
        items = []
        for grouped_row in grouped_rows:
            key, grouped_net, grouped_gross, grouped_count = grouped_row
            items.append({key_field: key, "group_value": key,
                          "net_sales_revenue": round(float(grouped_net), 2),
                          "gross_sales_value": round(float(grouped_gross), 2),
                          "daily_records_count": int(grouped_count)})
        items.sort(key=lambda item: item["net_sales_revenue"], reverse=sort_order == "descending")
        return {"items": items, "group_by": group_by, "sort_order": sort_order, "filters": {
            "product_id": product_id, "store_id": store_id, "category": category,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }, "discounts_included": True,
          "definition": "Net recorded sales = units sold × listed price × (1 − discount percent). This is revenue, not profit."}
    net, gross, rows = db.execute(stmt).one()
    return {
        "net_sales_revenue": round(float(net), 2),
        "gross_sales_value": round(float(gross), 2),
        "daily_records_count": int(rows),
        "discounts_included": True,
        "filters": {"product_id": product_id, "store_id": store_id, "category": category,
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None},
        "definition": "Net recorded sales = units sold × listed price × (1 − discount percent). This is revenue, not profit.",
    }


def get_store_profitability(
    db: Session,
    store_id: str | None = None,
    product_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    group_by: str = "store",
    sort_order: str = "descending",
) -> dict:
    """Compare gross profit using saved transaction costs, grouped safely."""
    _validate_date_range(start_date, end_date)
    group_columns = {
        "store": SalesTransaction.store_id,
        "product": SalesTransaction.product_id,
        "category": SalesTransaction.category,
        "total": literal("all"),
    }
    group_column = group_columns.get(group_by)
    if group_column is None:
        raise InvalidRequestError("group_by must be one of: total, store, product, category.")
    if sort_order not in {"ascending", "descending"}:
        raise InvalidRequestError("sort_order must be ascending or descending.")
    if product_id and not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")
    units = SalesTransaction.units_sold
    net_line = units * SalesTransaction.unit_price * (1 - SalesTransaction.discount_percent / 100.0)
    has_cost = SalesTransaction.unit_cost.is_not(None)
    stmt = select(
        group_column.label("group_value"),
        func.count().label("transaction_count"),
        func.coalesce(func.sum(units), 0).label("units_sold"),
        func.coalesce(func.sum(case((has_cost, units), else_=0)), 0).label("units_with_cost"),
        func.coalesce(func.sum(net_line), 0.0).label("net_sales_revenue"),
        func.coalesce(func.sum(case((has_cost, net_line), else_=0.0)), 0.0).label("costed_net_revenue"),
        func.coalesce(func.sum(case((has_cost, units * SalesTransaction.unit_cost), else_=0.0)), 0.0).label("known_cost_of_goods_sold"),
    )
    if group_by != "total":
        stmt = stmt.group_by(group_column)
    if store_id:
        stmt = stmt.where(SalesTransaction.store_id == store_id)
    if product_id:
        stmt = stmt.where(SalesTransaction.product_id == product_id)
    if category:
        stmt = stmt.where(SalesTransaction.category == category)
    if start_date:
        stmt = stmt.where(SalesTransaction.business_date >= start_date)
    if end_date:
        stmt = stmt.where(SalesTransaction.business_date <= end_date)
    items = []
    for row in db.execute(stmt).all():
        result = row._mapping
        units_sold = int(result["units_sold"])
        units_with_cost = int(result["units_with_cost"])
        costed_revenue = float(result["costed_net_revenue"])
        cost_of_goods = float(result["known_cost_of_goods_sold"])
        gross_profit = round(costed_revenue - cost_of_goods, 2)
        items.append({
            "group_value": result["group_value"],
            **({"store_id": result["group_value"]} if group_by == "store" else {}),
            **({"product_id": result["group_value"]} if group_by == "product" else {}),
            **({"category": result["group_value"]} if group_by == "category" else {}),
            "transaction_count": int(result["transaction_count"]),
            "units_sold": units_sold,
            "units_with_cost": units_with_cost,
            "units_without_cost": units_sold - units_with_cost,
            "cost_coverage_percent": round(100 * units_with_cost / units_sold, 1) if units_sold else 0.0,
            "net_sales_revenue": round(float(result["net_sales_revenue"]), 2),
            "costed_net_revenue": round(costed_revenue, 2),
            "known_cost_of_goods_sold": round(cost_of_goods, 2),
            "gross_profit_or_loss": gross_profit if units_with_cost else None,
            "gross_margin_percent": round(100 * gross_profit / costed_revenue, 1) if costed_revenue else None,
            "condition": ("unknown" if not units_with_cost else "profit" if gross_profit > 0
                          else "loss" if gross_profit < 0 else "break_even"),
        })
    unknown_sort_value = float("-inf") if sort_order == "descending" else float("inf")
    items.sort(key=lambda item: item["gross_profit_or_loss"] if item["gross_profit_or_loss"] is not None else unknown_sort_value,
               reverse=sort_order == "descending")
    return {"items": items, "group_by": group_by, "sort_order": sort_order, "filters": {"store_id": store_id, "product_id": product_id,
             "category": category, "start_date": start_date.isoformat() if start_date else None,
             "end_date": end_date.isoformat() if end_date else None},
            "cost_note": "Profit/loss uses transaction-level costs captured when a sale was recorded. Historical imported sales without cost data are excluded from profit; they are not guessed."}


def _validate_date_range(start_date: date | None, end_date: date | None) -> None:
    if start_date and end_date and start_date > end_date:
        raise InvalidRequestError(f"start_date ({start_date}) is after end_date ({end_date}).")


def get_profitability_analysis(
    db: Session,
    group_by: str = "total",
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    sort_order: str = "descending",
) -> dict:
    """Named capability for total or grouped gross-profit analysis."""
    return get_store_profitability(
        db, store_id=store_id, product_id=product_id, category=category,
        start_date=start_date, end_date=end_date, group_by=group_by,
        sort_order=sort_order,
    )


def get_top_products(
    db: Session,
    limit: int = 10,
    start_date: date | None = None,
    end_date: date | None = None,
) -> TopProductsResponse:
    _validate_date_range(start_date, end_date)
    rows = sales_repository.get_ranked_products_by_sales(
        db, limit=limit, ascending=False, start_date=start_date, end_date=end_date
    )
    return TopProductsResponse(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        products=[ProductSalesRank(**row) for row in rows],
    )


def get_bottom_products(
    db: Session,
    limit: int = 10,
    start_date: date | None = None,
    end_date: date | None = None,
) -> TopProductsResponse:
    _validate_date_range(start_date, end_date)
    rows = sales_repository.get_ranked_products_by_sales(
        db, limit=limit, ascending=True, start_date=start_date, end_date=end_date
    )
    return TopProductsResponse(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        products=[ProductSalesRank(**row) for row in rows],
    )


def get_sales_trend(
    db: Session,
    granularity: str = "daily",
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> SalesTrendResponse:
    if granularity not in VALID_GRANULARITIES:
        raise InvalidRequestError(f"granularity must be one of {VALID_GRANULARITIES}, got '{granularity}'.")
    _validate_date_range(start_date, end_date)

    if product_id and not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")

    rows = sales_repository.get_sales_trend(
        db,
        granularity=granularity,
        product_id=product_id,
        store_id=store_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
    )

    return SalesTrendResponse(
        granularity=granularity,
        filters={
            "product_id": product_id,
            "store_id": store_id,
            "category": category,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        points=[SalesTrendPoint(period=row["period"], total_units_sold=row["total_units_sold"]) for row in rows],
    )


def get_category_analysis(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[CategorySalesSummary]:
    _validate_date_range(start_date, end_date)
    rows = sales_repository.get_category_sales_summary(db, start_date=start_date, end_date=end_date)
    return [CategorySalesSummary(**row) for row in rows]


def get_store_analysis(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[StoreSalesSummary]:
    _validate_date_range(start_date, end_date)
    rows = sales_repository.get_store_sales_summary(db, start_date=start_date, end_date=end_date)
    return [StoreSalesSummary(**row) for row in rows]


def get_sales_records(
    db: Session,
    product_id: str | None = None,
    store_id: str | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> SalesListResponse:
    _validate_date_range(start_date, end_date)
    if limit > MAX_LIMIT:
        raise InvalidRequestError(f"limit must be <= {MAX_LIMIT}, got {limit}.")
    if product_id and not product_repository.product_exists(db, product_id):
        raise NotFoundError(f"Product '{product_id}' was not found in the current inventory data.")

    rows = sales_repository.get_sales_rows(
        db, product_id=product_id, store_id=store_id, category=category, start_date=start_date, end_date=end_date
    )
    page = rows[offset : offset + limit]
    items = [
        SalesRecord(
            date=r.date,
            store_id=r.store_id,
            product_id=r.product_id,
            category=r.category,
            region=r.region,
            units_sold=r.units_sold,
            price=r.price,
            discount=r.discount,
            holiday_promotion=r.holiday_promotion,
        )
        for r in page
    ]
    return SalesListResponse(items=items, count=len(rows), limit=limit, offset=offset)
