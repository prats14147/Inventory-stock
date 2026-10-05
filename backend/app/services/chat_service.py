"""
backend/app/services/chat_service.py

Orchestrates: message -> parse (rules, then LLM if needed) -> validate ->
backend tool call (spec section 33) -> structured result -> natural-
language response.

NO-HALLUCINATION POLICY (spec section 55), enforced structurally:
  - Every intent that needs a product ID is checked against the real
    database via product_repository.product_exists BEFORE any number is
    computed. Unknown products get a fixed "not found" message -- the
    LLM never sees a chance to invent a substitute value.
  - Tool functions return ONLY data computed by Phase 4-6 services
    (real DB queries / real saved ML models). The LLM (when available)
    is only asked to phrase that data in words -- see
    RESPONSE_GENERATION_SYSTEM_PROMPT -- and a deterministic template
    formatter is used whenever the LLM is unavailable, so the system
    never silently depends on the LLM to produce a legitimate answer.

CONVERSATION MEMORY (Phase 11):
  - Session-based multi-turn context with entity carryover
  - Pronoun resolution ("it", "that product") via EntityTracker
  - Topic management via TopicStack
  - Optional LLM summarization for long conversations
"""

from __future__ import annotations

import json
import logging
import uuid
import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.config import get_settings
from app.nlp import (
    parser,
    ContextManager,
    EntityTracker,
    SessionData,
    get_session_store,
    create_context_manager,
)
from app.nlp.entities import Entities
from app.nlp.intent import PRODUCT_REQUIRED_INTENTS, Intent
from app.nlp.request_planner import plan_request, prefer_explicit_stock_action
from app.nlp.llm_client import LLMUnavailableError
from app.nlp.prompts import RESPONSE_GENERATION_SYSTEM_PROMPT
from app.nlp.rules import extract_entities, is_stock_write_request, looks_like_follow_up
from app.nlp.tool_registry import TOOL_DEFINITIONS, TOOLS_BY_NAME
from app.repositories import product_repository
from app.models import DailyInventory, DailySales, Product
from app.models.stock_movement import StockMovement
from app.repositories import inventory_repository
from app.schemas.sales import RecordSaleRequest
from app.schemas.inventory import StockAdjustmentRequest
from app.schemas.chat import ChatResponse
from app.schemas.conversation import ChatRequest, ChatResponse as ConversationChatResponse
from app.services import forecast_service, inventory_service, reorder_service, sales_service, stockout_service
from app.services import project_knowledge_service
from app.services.errors import InvalidRequestError, NotFoundError

log = logging.getLogger("chat_service")


# --- Constants --------------------------------------------------------------

HELP_TEXT = (
    "I can answer questions about current stock, low stock, best/slow sellers, "
    "sales trends, revenue, and store gross profit/loss by product/store/category and time period, forecasts, stockout "
    "risk, and reorder quantities. Try \"How many units did P0001 sell last week?\" "
    "or \"Show weekly sales for P0001 at S001 this month.\" Profit uses costs saved with recorded sales; older "
    "imported sales without costs are excluded. For stock changes, say "
    "\"received 10 units of P0001 at S001\" or \"I sold 3 units of P0001 at S001\". "
    "If you say \"deduct\" or \"remove\", I will ask whether it was a sale or another kind of adjustment. "
    "I show a confirmation preview before changing stock."
)

_SALE_QUANTITY_RE = re.compile(
    r"\b(?:sold|sale\s+of|sell|deduct|remove|subtract|reduce)\s+(?:about\s+|around\s+|approximately\s+)?(\d+)\s*(?:units?|items?|stocks?|stoks?)?\b|"
    r"\b(\d+)\s*(?:units?|items?|products?|stocks?|stoks?)\b", re.I,
)
_SALE_PRICE_RE = re.compile(
    r"\b(?:unit\s+)?price\s*(?:is|of|:|=)?\s*\$?\s*(\d+(?:\.\d{1,2})?)\b|"
    r"\b(?:at|for)\s+\$?\s*(\d+(?:\.\d{1,2})?)\b|\$\s*(\d+(?:\.\d{1,2})?)",
    re.I,
)
_SALE_COST_RE = re.compile(r"\bcost(?:\s+price)?\s*(?:is|of|:|=)?\s*\$?\s*(\d+(?:\.\d{1,2})?)\b", re.I)
_SALE_REQUEST_RE = re.compile(
    r"\b(?:(?:i|we)\s+(?:just\s+)?sold|record\s+(?:a\s+)?sale|log\s+(?:a\s+)?sale)\b|"
    r"\b(?:i|we)\s+(?:just\s+)?sold\s+(?:about\s+|around\s+)?\d+\s+(?:stocks?|items?|products?)\b|"
    r"\b\d+\s+(?:units?|items?|products?|stocks?|stoks?)\s+(?:of\s+)?(?:product\s+)?P0*\d+\b"
    r".{0,80}\b(?:(?:was|were|has\s+been|have\s+been)\s+)?sold\b|"
    r"\b(?:sold\s+to\s+(?:a\s+)?(?:customer|cutomer)|(?:customer|cutomer)\s+(?:bought|purchased))\b", re.I,
)
_INVENTORY_ACTION_RE = re.compile(
    r"\b(?:receiv(?:e|ed|ing)|reciev(?:e|ed|ing)|restock(?:ed|ing)?|deliver(?:ed|ing)?|damag(?:e|ed)|broken|expired|wast(?:e|ed)|"
    r"remove|subtract|reduce|decrease|deduct|adjust|add\s+(?:stocks?|inventory))\b", re.I
)
_RECEIVE_ACTION_RE = re.compile(
    r"\b(?:receiv(?:e|ed|ing)|reciev(?:e|ed|ing)|restock(?:ed|ing)?|deliver(?:ed|ing)?|"
    r"add\s+(?:(?:\w+\s+){0,4})?(?:stocks?|inventory|product\s+quantity|quantity)|"
    r"add\s+(?:(?:about|around|approximately)\s+)?\d+\s*(?:units?|items?|stocks?))\b", re.I
)
_STOCK_REDUCTION_ACTION_RE = re.compile(
    r"\b(?:deduct|remove|subtract|reduce|decrease|damage(?:d)?|broken|expired|wast(?:e|ed)|lost|missing)\b",
    re.I,
)
_STOCK_HISTORY_QUERY_RE = re.compile(
    r"\b(?:stock|inventory)\s+(?:history|movements?|changes|adjustments?)\b|"
    r"\b(?:show|list|when|what|how many)\b.{0,50}\b(?:receive(?:d)?|deliver(?:ed)?|damaged|broken|expired|wasted|adjusted|removed)\b",
    re.I,
)
_ACTION_QUANTITY_RE = re.compile(r"\b(\d+)\s*(?:units?|items?)?\b", re.I)
_SEMANTIC_STOCK_VERB_RE = re.compile(
    r"\b(?:put|place|bring|got|arrived|increase|increased|bump|bumped|top\s+up|"
    r"take\s+(?:off|out)|knock\s+off|add|receive|received|recieved|sell|sold|"
    r"deduct|remove|subtract|reduce|decrease)\b",
    re.I,
)
_SEMANTIC_STOCK_OBJECT_RE = re.compile(
    r"\b(?:stock|stocks|inventory|units?|items?|quantity|shelf|shelves|on.hand)\b|\b[PS]\d+\b",
    re.I,
)
_PROJECT_QUESTION_RE = re.compile(
    r"\b(?:explain|how does (?:the )?(?:chatbot|model|forecast page|system)|"
    r"how is (?:the )?(?:demand )?forecast(?:ing)?(?: model)?|how is (?:the )?(?:stockout risk|reorder)|"
    r"why (?:does|is) (?:the )?(?:chatbot|forecast model)|"
    r"what does (?:units ordered|stockout risk|the chatbot|the forecast page)|"
    r"what is (?:this|the) (?:project|app|chatbot|model|dataset)|"
    r"in (?:this )?(?:project|app|codebase)|under the hood|architecture)\b",
    re.I,
)
_YES_RE = re.compile(r"^(?:yes(?: please)?|y|confirm(?: sale)?|record it|do it|go ahead|proceed|confirmed|please confirm)[.! ]*$", re.I)
_NO_RE = re.compile(r"^(?:no(?: thanks)?|n|cancel(?: sale)?|stop|don't|do not|not now)[.! ]*$", re.I)
_SALE_CLARIFICATION_RE = re.compile(
    r"\b(?:for\s+)?sales?\b|\b(?:it was|that was)\s+(?:a\s+)?sale\b|"
    r"\bsold\s+to\s+(?:a\s+)?(?:customer|cutomer)\b|\b(?:customer|cutomer)\s+(?:bought|purchased)\b",
    re.I,
)
_ADJUSTMENT_CLARIFICATION_RE = re.compile(r"\b(?:not\s+(?:a\s+)?sale|adjustment|damaged?|broken|expired|wasted?|lost|missing|non[- ]?sale)\b", re.I)


def _is_pending_sale_reply(message: str, pending: dict) -> bool:
    """Only divert likely confirmation/detail replies while a sale is pending."""
    trimmed = message.strip()
    if (_YES_RE.fullmatch(trimmed) or _NO_RE.fullmatch(trimmed) or _SALE_REQUEST_RE.search(trimmed)
            or (re.search(r"\b(?:sold|stoks?|stocks?|items?)\b", trimmed, re.I)
                and not re.search(r"\b(?:how|what|show|check|current|much|many)\b", trimmed, re.I))):
        return True
    if re.fullmatch(r"P\d+|S\d+|\d+(?:\s+units?)?|\$\s*\d+(?:\.\d{1,2})?", trimmed, re.I):
        return True
    if not re.search(r"\b(?:product(?:\s+id)?|sku|store(?:\s+id)?|quantity|price)\b", trimmed, re.I):
        return False
    return any(
        (field in {"product_id", "store_id", "units_sold"} and not pending.get(field))
        or (field == "price" and pending.get(field) is None)
        for field in ("product_id", "store_id", "units_sold", "price")
    ) or bool(re.search(r"\b(?:change|make it|instead|update|set)\b", trimmed, re.I))


def _is_pending_adjustment_reply(message: str, pending: dict) -> bool:
    trimmed = message.strip()
    if _YES_RE.fullmatch(trimmed) or _NO_RE.fullmatch(trimmed):
        return True
    if re.fullmatch(r"P\d+|S\d+|\d+", trimmed, re.I):
        return True
    if _INVENTORY_ACTION_RE.search(trimmed):
        return True
    if re.search(r"\b(?:product(?:\s+id)?|sku|store(?:\s+id)?|quantity|units?)\b", trimmed, re.I):
        return not re.search(r"\b(?:how|what|show|check|current|much|many|stock level)\b", trimmed, re.I)
    return False

CONTEXT_COMMANDS = {
    "reset", "clear context", "start over",
    "show history", "show context",
    "forget",
    "back to",
}


# --- Tool functions (spec section 33) --------------------------------------

def _tool_current_inventory(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        result = inventory_service.get_current_inventory_listing(db)
        items = result.items
        return {
            "as_of_date": result.as_of_date.isoformat() if result.as_of_date else None,
            "total_inventory_units": sum(item.inventory_level for item in items),
            "product_count": len({item.product_id for item in items}),
            "store_count": len({item.store_id for item in items}),
            "combination_count": len(items),
        }
    return inventory_service.get_product_inventory(db, entities.product_id).model_dump(mode="json")


def _tool_low_stock(db: Session, entities: Entities) -> dict:
    result = inventory_service.get_low_stock(db)
    if entities.product_id:
        if not product_repository.product_exists(db, entities.product_id):
            raise NotFoundError(f"Product '{entities.product_id}' was not found in the current inventory data.")
        result.items = [item for item in result.items if item.product_id == entities.product_id]
        result.count = len(result.items)
    return result.model_dump(mode="json")


def _tool_low_stock_fast_sellers(db: Session, entities: Entities) -> dict:
    """Compose the low-stock and recent-sales capabilities on verified data."""
    low_stock = inventory_service.get_low_stock(db)
    if entities.product_id:
        if not product_repository.product_exists(db, entities.product_id):
            raise NotFoundError(f"Product '{entities.product_id}' was not found in the current inventory data.")
        low_stock.items = [item for item in low_stock.items if item.product_id == entities.product_id]
    latest_sales_date = db.scalar(select(func.max(DailySales.date)))
    if latest_sales_date is None:
        return {"items": [], "as_of_date": low_stock.as_of_date.isoformat() if low_stock.as_of_date else None,
                "sales_window": None, "note": "No sales history is available to measure sales velocity."}
    start_date = latest_sales_date - timedelta(days=29)
    ranked = sales_service.get_top_products(
        db, limit=1000, start_date=start_date, end_date=latest_sales_date
    ).products
    velocities = {item.product_id: item.total_units_sold for item in ranked}
    items = [
        {**row.model_dump(mode="json"), "units_sold_in_30_days": velocities[row.product_id]}
        for row in low_stock.items if row.product_id in velocities and velocities[row.product_id] > 0
    ]
    items.sort(key=lambda item: item["units_sold_in_30_days"], reverse=True)
    return {"items": items, "as_of_date": low_stock.as_of_date.isoformat() if low_stock.as_of_date else None,
            "sales_window": {"start_date": start_date.isoformat(), "end_date": latest_sales_date.isoformat()},
            "note": "Sales velocity uses the latest 30 calendar days present in sales history; stock uses the latest inventory date."}


def _tool_stock_history(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    if entities.product_id and not product_repository.product_exists(db, entities.product_id):
        raise NotFoundError(f"Product '{entities.product_id}' was not found in the current inventory data.")
    query = select(StockMovement).order_by(StockMovement.occurred_at.desc()).limit(50)
    if entities.product_id:
        query = query.where(StockMovement.product_id == entities.product_id)
    if entities.store_id:
        query = query.where(StockMovement.store_id == entities.store_id)
    if start_date:
        query = query.where(StockMovement.business_date >= start_date)
    if end_date:
        query = query.where(StockMovement.business_date <= end_date)
    rows = db.scalars(query).all()
    return {"items": [{
        "business_date": row.business_date.isoformat(), "store_id": row.store_id,
        "product_id": row.product_id, "movement_type": row.movement_type,
        "quantity_delta": row.quantity_delta, "quantity_before": row.quantity_before,
        "quantity_after": row.quantity_after, "reason": row.reason,
    } for row in rows], "count": len(rows), "limit": 50,
        "filters": {"product_id": entities.product_id, "store_id": entities.store_id,
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None}}


def _tool_top_selling(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    return sales_service.get_top_products(db, limit=10, start_date=start_date, end_date=end_date).model_dump(mode="json")


def _tool_bottom_selling(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    return sales_service.get_bottom_products(db, limit=10, start_date=start_date, end_date=end_date).model_dump(mode="json")


def _tool_sales_trend(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    result = sales_service.get_sales_trend(
        db,
        granularity=entities.granularity or "monthly",
        product_id=entities.product_id,
        store_id=entities.store_id,
        category=entities.category,
        start_date=start_date,
        end_date=end_date,
    )
    return result.model_dump(mode="json")


def _tool_revenue_analysis(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    return sales_service.get_revenue_analysis(
        db, product_id=entities.product_id, store_id=entities.store_id,
        category=entities.category, start_date=start_date, end_date=end_date,
        group_by=entities.group_by, sort_order=entities.sort_order or "descending",
    )


def _tool_store_profitability(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    return sales_service.get_store_profitability(
        db, store_id=entities.store_id, product_id=entities.product_id,
        category=entities.category, start_date=start_date, end_date=end_date,
        group_by=entities.group_by or "store", sort_order=entities.sort_order or "descending",
    )


def _tool_financial_analysis(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    return sales_service.get_profitability_analysis(
        db, group_by=entities.group_by or "total", product_id=entities.product_id,
        store_id=entities.store_id, category=entities.category,
        start_date=start_date, end_date=end_date,
        sort_order=entities.sort_order or "descending",
    )


def _date_filters(entities: Entities) -> tuple[date | None, date | None]:
    date_range = entities.date_range or {}
    try:
        start = date.fromisoformat(date_range["start_date"]) if date_range.get("start_date") else None
        end = date.fromisoformat(date_range["end_date"]) if date_range.get("end_date") else None
    except (TypeError, ValueError) as exc:
        raise InvalidRequestError("I couldn't understand that date. Please use a date such as 2026-10-01.") from exc
    return start, end


def _tool_product_info(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like information about?")
    inventory = inventory_service.get_product_inventory(db, entities.product_id)
    trend = sales_service.get_sales_trend(db, granularity="monthly", product_id=entities.product_id)
    return {
        "inventory": inventory.model_dump(mode="json"),
        "monthly_sales_trend": trend.model_dump(mode="json"),
    }


def _tool_forecast_demand(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like a demand forecast for?")
    horizon = entities.forecast_horizon or get_settings().default_forecast_horizon
    result = forecast_service.forecast_product_demand(db, entities.product_id, horizon=horizon)
    result["target_date"] = result["target_date"].isoformat()
    return result


def _tool_stockout_risk(db: Session, entities: Entities) -> dict:
    if entities.product_id:
        return stockout_service.calculate_stockout_risk(db, entities.product_id).model_dump(mode="json")
    listing = inventory_service.get_current_inventory_listing(db)
    product_ids = sorted({row.product_id for row in listing.items})
    results = [stockout_service.calculate_stockout_risk(db, product_id).model_dump(mode="json")
               for product_id in product_ids]
    at_risk = [item for item in results if item["risk"] != "LOW"]
    at_risk.sort(key=lambda item: (0 if item["risk"] == "HIGH" else 1, item["product_id"]))
    return {"items": at_risk, "products_checked": len(results), "as_of_date": listing.as_of_date.isoformat() if listing.as_of_date else None}


def _tool_reorder_recommendation(db: Session, entities: Entities) -> dict:
    if entities.product_id:
        return reorder_service.calculate_reorder(db, entities.product_id).model_dump(mode="json")
    listing = inventory_service.get_current_inventory_listing(db)
    product_ids = sorted({row.product_id for row in listing.items})
    results = [reorder_service.calculate_reorder(db, product_id).model_dump(mode="json")
               for product_id in product_ids]
    recommendations = [item for item in results if item["recommended_reorder_quantity"] > 0]
    recommendations.sort(key=lambda item: item["recommended_reorder_quantity"], reverse=True)
    return {"items": recommendations, "products_checked": len(results), "as_of_date": listing.as_of_date.isoformat() if listing.as_of_date else None}


def _tool_category_analysis(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    return {
        "categories": [c.model_dump(mode="json") for c in sales_service.get_category_analysis(db, start_date, end_date)],
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }


def _tool_store_analysis(db: Session, entities: Entities) -> dict:
    start_date, end_date = _date_filters(entities)
    return {
        "stores": [s.model_dump(mode="json") for s in sales_service.get_store_analysis(db, start_date, end_date)],
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }


TOOL_EXECUTORS_BY_NAME = {
    "get_current_stock": _tool_current_inventory,
    "get_low_stock": _tool_low_stock,
    "get_low_stock_fast_sellers": _tool_low_stock_fast_sellers,
    "get_stock_history": _tool_stock_history,
    "get_sales_summary": _tool_sales_trend,
    "get_revenue": _tool_revenue_analysis,
    "get_gross_profit": _tool_financial_analysis,
    "get_top_selling_products": _tool_top_selling,
    "get_slow_selling_products": _tool_bottom_selling,
    "get_category_analysis": _tool_category_analysis,
    "get_store_analysis": _tool_store_analysis,
    "forecast_demand": _tool_forecast_demand,
    "get_stockout_risk": _tool_stockout_risk,
    "get_reorder_recommendation": _tool_reorder_recommendation,
    "get_product_info": _tool_product_info,
}
TOOLS = {definition.intent: TOOL_EXECUTORS_BY_NAME[definition.name] for definition in TOOL_DEFINITIONS}
# A phrase-matched legacy alias remains for existing sessions and clients.
TOOLS[Intent.STORE_PROFITABILITY] = _tool_store_profitability


# --- Exceptions -------------------------------------------------------------

class MissingEntityError(Exception):
    """Raised when an intent needs an entity (e.g. product_id) that wasn't extracted."""


# --- Deterministic template fallback (used when no LLM / LLM unavailable) --

def _template_response(intent: Intent, entities: Entities, data: dict) -> str:
    if intent == Intent.CURRENT_STOCK:
        if "total_inventory_units" in data:
            return (f"Current inventory has {data['total_inventory_units']:,} units across "
                    f"{data['product_count']} products and {data['store_count']} stores "
                    f"(as of {data['as_of_date']}).")
        return f"{data['product_id']} currently has {data['total_inventory']:.0f} units in stock (as of {data['as_of_date']}, across {len(data['stores'])} stores)."
    if intent == Intent.LOW_STOCK:
        return f"{data['count']} store-product combinations are below the low-stock threshold of {data['threshold']} units (as of {data['as_of_date']})."
    if intent == Intent.LOW_STOCK_FAST_SELLING:
        if not data["items"]:
            return data.get("note") or "No products matched both low stock and positive sales in the measured period."
        summary = "; ".join(
            f"{item['product_id']} at {item['store_id']} ({item['inventory_level']} on hand, "
            f"{item['units_sold_in_30_days']} sold in the 30-day sales window)"
            for item in data["items"][:8]
        )
        return f"Low-stock items with recent sales: {summary}. {data['note']}"
    if intent == Intent.STOCK_HISTORY:
        if not data["items"]:
            return "I couldn't find stock movements for those product, store, or date filters."
        recent = "; ".join(
            f"{item['business_date']} {item['product_id']} at {item['store_id']}: "
            f"{item['movement_type'].lower().replace('_', ' ')} {item['quantity_delta']:+d} "
            f"({item['quantity_before']} → {item['quantity_after']}, {item['reason']})"
            for item in data["items"][:5]
        )
        return f"Recent stock movements: {recent}. Showing up to {data['limit']} records."
    if intent == Intent.TOP_SELLING:
        top = data["products"][:3]
        if not top:
            return "I couldn't find sales records for that date range. Try a wider period."
        names = ", ".join(f"{p['product_id']} ({p['total_units_sold']:.0f} units)" for p in top)
        return f"The top-selling products{_period_label(data.get('start_date'), data.get('end_date'))} are: {names}."
    if intent == Intent.BOTTOM_SELLING:
        bottom = data["products"][:3]
        if not bottom:
            return "I couldn't find sales records for that date range. Try a wider period."
        names = ", ".join(f"{p['product_id']} ({p['total_units_sold']:.0f} units)" for p in bottom)
        return f"The lowest-selling products{_period_label(data.get('start_date'), data.get('end_date'))} are: {names}."
    if intent == Intent.DEMAND_FORECAST:
        return (
            f"Forecast demand for {data['product_id']} over the next {data['model_horizon_days']} days "
            f"(by {data['target_date']}) is approximately {data['forecast_total_units']:.0f} units across all stores."
        )
    if intent == Intent.STOCKOUT_RISK:
        if "items" in data:
            if not data["items"]:
                return f"None of the {data['products_checked']} products checked are currently at medium or high stockout risk (inventory as of {data['as_of_date']})."
            summary = "; ".join(f"{item['product_id']} ({item['risk'].lower()} risk)" for item in data["items"][:8])
            return f"Products at medium or high stockout risk as of {data['as_of_date']}: {summary}. {data['products_checked']} products checked."
        return f"{data['product_id']} has {data['risk']} stockout risk. {data['reason']}"
    if intent == Intent.REORDER_RECOMMENDATION:
        if "items" in data:
            if not data["items"]:
                return f"No positive reorder quantity is recommended for the {data['products_checked']} products checked as of {data['as_of_date']}."
            summary = "; ".join(f"{item['product_id']}: {item['recommended_reorder_quantity']:.0f} units" for item in data["items"][:10])
            return f"Recommended reorders as of {data['as_of_date']}: {summary}. These use the configured lead-time assumption."
        return (
            f"{data['product_id']} currently has {data['current_inventory']:.0f} units. Estimated demand over the "
            f"{data['assumptions']['lead_time_days']}-day lead time is {data['forecast_lead_time_demand']:.1f} units, "
            f"with a safety stock of {data['safety_stock']:.1f}. Recommended reorder quantity: "
            f"{data['recommended_reorder_quantity']:.0f} units."
        )
    if intent == Intent.CATEGORY_ANALYSIS:
        top = data["categories"][:3]
        if not top:
            return "I couldn't find category sales records for that date range. Try a wider period."
        names = ", ".join(f"{c['category']} ({c['total_units_sold']:.0f} units)" for c in top)
        return f"Top categories by units sold{_period_label(data.get('start_date'), data.get('end_date'))}: {names}."
    if intent == Intent.STORE_ANALYSIS:
        top = data["stores"][:3]
        if not top:
            return "I couldn't find store sales records for that date range. Try a wider period."
        names = ", ".join(f"{s['store_id']} ({s['total_units_sold']:.0f} units)" for s in top)
        return f"Top stores by units sold{_period_label(data.get('start_date'), data.get('end_date'))}: {names}."
    if intent == Intent.SALES_TREND:
        n_points = len(data["points"])
        if not n_points:
            return "I couldn't find sales records for those filters. Try another product, store, or date range."
        filters = data.get("filters", {})
        selected = [str(filters[key]) for key in ("product_id", "store_id", "category") if filters.get(key)]
        scope = " for " + ", ".join(selected) if selected else ""
        period = _period_label(filters.get("start_date"), filters.get("end_date"))
        return f"Here's the {data['granularity']} sales trend{scope}{period} ({n_points} data points, measured in units sold)."
    if intent == Intent.REVENUE_ANALYSIS:
        if data.get("items") is not None:
            if not data["items"]:
                return "I couldn't find sales for that group or date range."
            key = {"product": "product_id", "store": "store_id", "category": "category"}.get(data.get("group_by"), "group_value")
            direction = "lowest" if data.get("sort_order") == "ascending" else "highest"
            return "Recorded net revenue by " + str(data["group_by"]) + f" ({direction} first): " + "; ".join(
                f"{item.get(key, item['group_value'])} ${item['net_sales_revenue']:,.2f}" for item in data["items"][:10]
            ) + "."
        filters = data.get("filters", {})
        scope = ", ".join(str(filters[key]) for key in ("product_id", "store_id", "category") if filters.get(key))
        date_range = _period_label(filters.get("start_date"), filters.get("end_date"))
        suffix = f" for {scope}" if scope else ""
        return (f"Recorded net sales revenue{suffix}{date_range} is ${data['net_sales_revenue']:,.2f} after listed discounts "
                f"(gross value ${data['gross_sales_value']:,.2f}, {data['daily_records_count']} daily records). This is revenue, not profit.")
    if intent == Intent.STORE_PROFITABILITY:
        items = data["items"]
        if not items:
            return "I don't have transaction-level sales recorded yet. Imported sample sales do not include product cost, so they cannot be used to calculate real profit or loss."
        known = [item for item in items if item["gross_profit_or_loss"] is not None]
        if not known:
            return "I found recorded sales, but none have a saved cost price yet. Add product cost prices and record sales to calculate store profit or loss."
        summary = "; ".join(
            f"{item['store_id']}: ${abs(item['gross_profit_or_loss']):,.2f} {item['condition']} "
            f"({item['cost_coverage_percent']:.0f}% of units have cost data)"
            for item in known[:5]
        )
        return f"Store gross profit/loss on sales with known costs: {summary}. Historical sales without cost are excluded from profit."
    if intent == Intent.FINANCIAL_ANALYSIS:
        items = data["items"]
        known = [item for item in items if item["gross_profit_or_loss"] is not None]
        if not known:
            return "I don't have recorded sales with product cost data for that period, so I can't calculate gross profit yet. Imported historical sales don't include costs."
        group_by = data.get("group_by", "total")
        if group_by == "total":
            item = known[0]
            amount = item["gross_profit_or_loss"]
            label = "profit" if amount > 0 else "loss" if amount < 0 else "break-even"
            margin = (f" Gross margin is {item['gross_margin_percent']:.1f}%."
                      if item["gross_margin_percent"] is not None else "")
            return (f"Gross {label} for recorded sales{_period_label(data['filters'].get('start_date'), data['filters'].get('end_date'))} "
                    f"is ${abs(amount):,.2f}.{margin} Cost coverage is {item['cost_coverage_percent']:.0f}%. This excludes operating expenses and sales without saved costs.")
        best = known[:5]
        label_field = {"product": "product_id", "store": "store_id", "category": "category"}.get(group_by, "group_value")
        def margin_label(item: dict) -> str:
            margin = item["gross_margin_percent"]
            return f"{margin:.1f}% margin" if margin is not None else "margin unavailable"
        summary = "; ".join(
            f"{item.get(label_field, item['group_value'])}: ${item['gross_profit_or_loss']:,.2f} gross profit/loss "
            f"({margin_label(item)}, "
            f"{item['cost_coverage_percent']:.0f}% cost coverage)" for item in best
        )
        direction = "lowest" if data.get("sort_order") == "ascending" else "highest"
        return f"Gross profit/loss by {group_by}, {direction} first{_period_label(data['filters'].get('start_date'), data['filters'].get('end_date'))}: {summary}. Historical sales without costs are excluded."
    if intent == Intent.PRODUCT_INFO:
        inv = data["inventory"]
        return f"{inv['product_id']}: {inv['total_inventory']:.0f} units in stock as of {inv['as_of_date']}."
    return "Here's what I found."


def _period_label(start_date, end_date) -> str:
    if start_date and end_date:
        return f" from {start_date} to {end_date}"
    if start_date:
        return f" since {start_date}"
    if end_date:
        return f" through {end_date}"
    return ""


def _llm_phrase_response(llm_client, message: str, intent: Intent, data: dict, on_token=None) -> str | None:
    """Phrase verified `data` in words using the LLM.

    When `on_token` is supplied and the client supports it, the text arrives
    incrementally and each chunk is forwarded to the caller (live UI). The
    returned string is still the full text, so both paths behave identically.
    """
    if llm_client is None:
        return None
    try:
        payload = json.dumps({"user_question": message, "intent": intent.value, "verified_data": data})
        if on_token is not None and hasattr(llm_client, "stream_text"):
            chunks: list[str] = []
            for chunk in llm_client.stream_text(RESPONSE_GENERATION_SYSTEM_PROMPT, payload):
                chunks.append(chunk)
            response = "".join(chunks).strip()
        else:
            response = llm_client.complete_text(RESPONSE_GENERATION_SYSTEM_PROMPT, payload).strip()
        if response and not _response_numbers_are_verified(response, data):
            log.warning("Discarding LLM response containing numbers absent from verified backend data")
            return None
        if response and on_token is not None:
            on_token(response)
        return response or None
    except Exception as e:  # noqa: BLE001 - a response provider failure must not fail a verified answer
        log.warning("LLM unavailable for response phrasing, using template: %s", e)
        return None


def _response_numbers_are_verified(response: str, data: dict) -> bool:
    """Reject model phrasing that introduces numeric values absent from tool data."""
    numeric_pattern = re.compile(r"(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?%?")

    def values(text: str) -> set[Decimal]:
        result = set()
        for token in numeric_pattern.findall(text):
            try:
                result.add(Decimal(token.replace(",", "").rstrip("%")))
            except InvalidOperation:
                continue
        return result

    verified = values(json.dumps(data, ensure_ascii=False, default=str))
    return values(response).issubset(verified)


# --- Context-Aware Chat Handler --------------------------------------------

# Progress stages reported to streaming callers (WebSocket). Deliberately
# coarse and mechanical: each stage maps to a real phase of the pipeline, so
# the live UI shows what the system is actually doing instead of a spinner.
STAGE_PARSING = "analyzing_request"
STAGE_QUERYING = "querying_database"
STAGE_PHRASING = "phrasing_response"


def _notify(callback, payload) -> None:
    """Invoke a progress callback, swallowing its errors.

    Progress reporting is a UI nicety: a broken callback must never turn a
    correct, verified answer into an error response.
    """
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:  # noqa: BLE001
        log.warning("Progress callback failed", exc_info=True)


class ChatSessionManager:
    """Manages chat sessions with conversation memory."""

    def __init__(self, llm_client=None):
        self.session_store = get_session_store()
        self.llm_client = llm_client
        self.context_manager = create_context_manager(llm_client)
        # Per-session context managers (in-memory, short-lived)
        self._context_managers: dict[str, ContextManager] = {}

    def _get_or_create_context_manager(self, session_id: str) -> ContextManager:
        """Get or create a ContextManager for a session."""
        if session_id not in self._context_managers:
            self._context_managers[session_id] = create_context_manager(self.llm_client)
            # Restore context from session store if available
            session = self.session_store.get_session(session_id)
            if session and session.turns:
                self._restore_context(session_id, session)
        return self._context_managers[session_id]

    def _restore_context(self, session_id: str, session: SessionData) -> None:
        """Restore entity tracker and topic stack from session history."""
        cm = self._context_managers[session_id]
        for turn in session.turns:
            entities = Entities(**turn.get("entities", {}))
            intent_str = turn.get("intent")
            intent = Intent(intent_str) if intent_str else None
            cm.entity_tracker.update(entities, turn.get("turn_index", 0))
            cm.topic_stack.update_current(turn.get("turn_index", 0), entities)
        cm.turn_count = len(session.turns)
        cm.summary = session.summary

    def _carryover_intent(self, session: SessionData, message: str) -> Optional[Intent]:
        """Reuse the previous product-scoped intent for a context-only follow-up.

        The rules layer matches keywords, so a pronoun/ordinal follow-up such
        as "Forecast it" or "How much at that store?" is either matched by its
        own keyword or comes back as UNKNOWN. This method covers the remaining
        case: when the message only makes sense with conversation context and
        the last classified turn was product-scoped, carry that intent forward
        rather than replying with a generic "I'm not sure what you're asking".
        """
        if not looks_like_follow_up(message):
            return None

        for turn in reversed(session.turns):
            raw_intent = turn.get("intent")
            if not raw_intent:
                continue
            try:
                previous = Intent(raw_intent)
            except ValueError:
                continue
            if previous == Intent.UNKNOWN:
                continue  # keep walking back to the last real intent
            # Last *classified* turn wasn't product-scoped (e.g. a ranking
            # question) -- carrying it forward would answer the wrong
            # question, so stop here.
            reusable = PRODUCT_REQUIRED_INTENTS | {
                Intent.REVENUE_ANALYSIS, Intent.FINANCIAL_ANALYSIS,
                Intent.STORE_PROFITABILITY, Intent.SALES_TREND,
                Intent.TOP_SELLING, Intent.BOTTOM_SELLING,
                Intent.STOCK_HISTORY,
            }
            return previous if previous in reusable else None
        return None

    def _handle_chat_sale(self, db: Session, session: SessionData, message: str) -> tuple[str, dict, Intent]:
        """Prepare or confirm a sale. Stock is never changed during preparation."""
        pending = dict(session.metadata.get("pending_sale") or {})
        if pending and _NO_RE.fullmatch(message.strip()):
            session.metadata.pop("pending_sale", None)
            self.session_store.save_session(session)
            return "Sale cancelled. No stock or sales history was changed.", {"sale_status": "cancelled"}, Intent.RECORD_SALE

        if pending and _YES_RE.fullmatch(message.strip()):
            try:
                result = sales_service.record_sale(db, RecordSaleRequest(**pending))
            except (InvalidRequestError, NotFoundError) as exc:
                db.rollback()
                return f"I couldn't record that sale: {exc} Please update the details or cancel it.", {
                    "sale_status": "needs_attention", "pending_sale": pending,
                }, Intent.RECORD_SALE
            session.metadata.pop("pending_sale", None)
            self.session_store.save_session(session)
            data = {"sale_status": "recorded", **result.model_dump(mode="json")}
            return (f"Sale recorded: {result.units_sold} units of {result.product_id} at {result.store_id}. "
                    f"There are now {result.remaining_inventory} units on hand; sales history has been updated."), data, Intent.RECORD_SALE

        entities = extract_entities(message)
        awaiting_field = pending.get("awaiting_field")
        quantity_match = None if awaiting_field in {"price", "unit_cost"} else _SALE_QUANTITY_RE.search(message)
        bare_quantity = re.fullmatch(r"\s*(\d+)\s*(?:units?|items?)?\s*", message, re.I)
        quantity = int(next(value for value in quantity_match.groups() if value)) if quantity_match else (
            int(bare_quantity.group(1)) if pending and bare_quantity and awaiting_field is None else None
        )
        cost_match = _SALE_COST_RE.search(message)
        unit_cost = float(cost_match.group(1)) if cost_match else None
        price_match = _SALE_PRICE_RE.search(_SALE_COST_RE.sub("", message))
        price = float(next(value for value in price_match.groups() if value)) if price_match else None
        bare_money = re.fullmatch(r"\s*\$?\s*(\d+(?:\.\d{1,2})?)\s*", message)
        if awaiting_field == "price":
            price = price if price is not None else float(bare_money.group(1)) if bare_money else None
        elif awaiting_field == "unit_cost":
            unit_cost = unit_cost if unit_cost is not None else price if price is not None else float(bare_money.group(1)) if bare_money else None
            price = None
        draft = {
            "product_id": entities.product_id or pending.get("product_id"),
            "store_id": entities.store_id or pending.get("store_id"),
            "units_sold": quantity or pending.get("units_sold"),
            "price": price if price is not None else pending.get("price"),
            "unit_cost": unit_cost if unit_cost is not None else pending.get("unit_cost"),
            "category": pending.get("category"),
            "region": pending.get("region"),
            "discount": int(pending.get("discount", 0)),
            "holiday_promotion": bool(pending.get("holiday_promotion", False)),
            "weather_condition": pending.get("weather_condition", "Unknown"),
            "competitor_pricing": pending.get("competitor_pricing"),
            "seasonality": pending.get("seasonality", "Unknown"),
        }
        draft.pop("awaiting_field", None)
        missing = [label for field, label in (("product_id", "product ID (for example P0001)"),
                                                ("store_id", "store ID (for example S001)"),
                                                ("units_sold", "quantity")) if not draft[field]]
        if missing:
            session.metadata["pending_sale"] = draft
            self.session_store.save_session(session)
            return "To prepare the sale, please provide the " + ", ".join(missing) + ". Stock will not change until you confirm.", {
                "sale_status": "collecting_details", "pending_sale": draft,
            }, Intent.RECORD_SALE
        if not product_repository.product_exists(db, draft["product_id"]):
            return f"I couldn't find product '{draft['product_id']}' in inventory. Check the product ID and try again.", {"sale_status": "invalid_product"}, Intent.RECORD_SALE
        latest_date = inventory_repository.get_latest_date(db)
        stock = db.get(DailyInventory, (latest_date, draft["store_id"], draft["product_id"])) if latest_date else None
        if stock is None:
            return f"There is no current stock record for {draft['product_id']} at {draft['store_id']}. No sale was recorded.", {"sale_status": "no_stock_record"}, Intent.RECORD_SALE
        if draft["price"] is None:
            session.metadata["pending_sale"] = {**draft, "awaiting_field": "price"}
            self.session_store.save_session(session)
            return ("What was the actual selling price per unit for this customer sale? "
                    "I won't reuse a price from an older sale; stock has not changed."), {
                "sale_status": "collecting_details", "pending_sale": {**draft, "awaiting_field": "price"},
            }, Intent.RECORD_SALE
        if draft["unit_cost"] is None:
            product = db.get(Product, draft["product_id"])
            if product is not None and product.cost_price is not None:
                draft["unit_cost"] = float(product.cost_price)
            else:
                session.metadata["pending_sale"] = {**draft, "awaiting_field": "unit_cost"}
                self.session_store.save_session(session)
                return "I don't have a cost price saved for this product. What is its unit cost? I need that to track profit; stock has not changed.", {
                    "sale_status": "collecting_details", "pending_sale": {**draft, "awaiting_field": "unit_cost"},
                }, Intent.RECORD_SALE
        draft["category"] = stock.category or "Uncategorized"
        draft["region"] = stock.region or "Unassigned"
        if draft["units_sold"] > stock.inventory_level:
            session.metadata["pending_sale"] = draft
            self.session_store.save_session(session)
            return f"Only {stock.inventory_level} units are currently available for {draft['product_id']} at {draft['store_id']}. Adjust the quantity or cancel; nothing has changed yet.", {
                "sale_status": "quantity_exceeds_stock", "pending_sale": draft, "available_units": stock.inventory_level,
            }, Intent.RECORD_SALE
        session.metadata["pending_sale"] = draft
        self.session_store.save_session(session)
        projected_profit = draft["units_sold"] * (draft["price"] * (1 - draft["discount"] / 100) - draft["unit_cost"])
        data = {"sale_status": "awaiting_confirmation", "pending_sale": draft,
                "available_units": stock.inventory_level,
                "remaining_after_sale": stock.inventory_level - draft["units_sold"],
                "projected_gross_profit": round(projected_profit, 2)}
        return (f"Please confirm: record {draft['units_sold']} units of {draft['product_id']} at {draft['store_id']} "
                f"at ${draft['price']:.2f} each (unit cost ${draft['unit_cost']:.2f})? Current stock is {stock.inventory_level}; "
                f"after the sale it will be {stock.inventory_level - draft['units_sold']}. Estimated gross "
                f"{'profit' if projected_profit >= 0 else 'loss'}: ${abs(projected_profit):.2f}."), data, Intent.RECORD_SALE

    def _handle_stock_adjustment(self, db: Session, session: SessionData, message: str) -> tuple[str, dict, Intent]:
        """Preview and confirm a delivery or non-sale inventory correction."""
        pending = dict(session.metadata.get("pending_stock_adjustment") or {})
        trimmed = message.strip()
        if pending and _NO_RE.fullmatch(trimmed):
            session.metadata.pop("pending_stock_adjustment", None)
            self.session_store.save_session(session)
            return "Stock adjustment cancelled. Inventory was not changed.", {"adjustment_status": "cancelled"}, Intent.ADJUST_STOCK

        if pending and _YES_RE.fullmatch(trimmed):
            try:
                result = inventory_service.adjust_stock(
                    db, StockAdjustmentRequest(**pending), source="chatbot_confirmation"
                )
            except (InvalidRequestError, NotFoundError) as exc:
                db.rollback()
                session.metadata.pop("pending_stock_adjustment", None)
                self.session_store.save_session(session)
                return f"I couldn't apply that stock change: {exc} No stock was changed. Please submit a corrected request.", {
                    "adjustment_status": "needs_attention", "error": str(exc),
                }, Intent.ADJUST_STOCK
            session.metadata.pop("pending_stock_adjustment", None)
            self.session_store.save_session(session)
            data = {"adjustment_status": "recorded", **result.model_dump(mode="json")}
            change = "increased" if result.quantity_delta > 0 else "reduced"
            return (f"Stock updated: {result.product_id} at {result.store_id} was {change} by "
                    f"{abs(result.quantity_delta)} units; {result.quantity_after} remain. This was recorded as "
                    f"{result.movement_type.lower().replace('_', ' ')}, not as a sale."), data, Intent.ADJUST_STOCK

        entities = extract_entities(message)
        awaiting_field = pending.get("awaiting_field")
        if awaiting_field == "product_id" and not entities.product_id:
            candidate = re.search(r"\b(?:product\s+id|sku)\s*[:#-]?\s*([A-Za-z0-9][\w-]*)", message, re.I)
            entities.product_id = candidate.group(1) if candidate else (trimmed if re.fullmatch(r"[A-Za-z0-9][\w-]*", trimmed) else None)
        if awaiting_field == "store_id" and not entities.store_id:
            candidate = re.search(r"\bstore(?:\s+id)?\s*[:#-]?\s*(S\d+)\b", message, re.I)
            raw_store_id = candidate.group(1) if candidate else (trimmed if re.fullmatch(r"S\d+", trimmed, re.I) else None)
            if raw_store_id:
                digits = raw_store_id[1:]
                entities.store_id = f"S{int(digits):03d}" if len(digits) <= 4 else raw_store_id.upper()
        receives = bool(_RECEIVE_ACTION_RE.search(message)) or pending.get("movement_type") == "DELIVERY"
        movement_type = "DELIVERY" if receives else "MANUAL_CORRECTION"
        quantity_text = re.sub(r"\b[PS]\d+\b", " ", message, flags=re.I)
        quantity_match = None if awaiting_field in {"product_id", "store_id"} else _ACTION_QUANTITY_RE.search(quantity_text)
        quantity = int(quantity_match.group(1)) if quantity_match else pending.get("quantity")
        product_id = entities.product_id or pending.get("product_id")
        store_id = entities.store_id or pending.get("store_id")
        reason_match = re.search(r"\b(damaged|damage|broken|expired|waste|wasted|lost|missing|correction|corrected)\b", message, re.I)
        reason = ("Stock received" if receives else
                  f"Stock {reason_match.group(1).lower()}" if reason_match else
                  pending.get("reason", "Manual stock reduction"))
        if quantity is None:
            session.metadata["pending_stock_adjustment"] = {**pending, "movement_type": movement_type, "reason": reason, "awaiting_field": "quantity"}
            self.session_store.save_session(session)
            return "How many units should I change? I won't change stock until you confirm the preview.", {
                "adjustment_status": "collecting_details", "pending_adjustment": pending,
            }, Intent.ADJUST_STOCK
        if not product_id:
            draft = {**pending, "quantity": quantity, "movement_type": movement_type, "reason": reason, "awaiting_field": "product_id"}
            session.metadata["pending_stock_adjustment"] = draft
            self.session_store.save_session(session)
            return "Which product ID is this for? I won't change stock until you confirm the preview.", {
                "adjustment_status": "collecting_details", "pending_adjustment": draft,
            }, Intent.ADJUST_STOCK
        if not store_id:
            draft = {**pending, "quantity": quantity, "product_id": product_id, "movement_type": movement_type, "reason": reason, "awaiting_field": "store_id"}
            session.metadata["pending_stock_adjustment"] = draft
            self.session_store.save_session(session)
            return f"Which store ID should I update for {product_id}? I won't change stock until you confirm the preview.", {
                "adjustment_status": "collecting_details", "pending_adjustment": draft,
            }, Intent.ADJUST_STOCK

        rows = inventory_repository.get_current_inventory_rows(db, product_id)
        stock = next((row for row in rows if row.store_id == store_id), None)
        if stock is None:
            return f"I couldn't find current stock for {product_id} at {store_id}; nothing was changed.", {
                "adjustment_status": "not_found", "product_id": product_id, "store_id": store_id,
            }, Intent.ADJUST_STOCK
        if receives:
            delta = quantity
        else:
            delta = -quantity
        after = stock.inventory_level + delta
        if after < 0:
            return f"Only {stock.inventory_level} units are on hand at {store_id}; I can't remove {quantity}. Nothing was changed.", {
                "adjustment_status": "insufficient_stock", "available_units": stock.inventory_level,
            }, Intent.ADJUST_STOCK
        draft = {
            "product_id": product_id, "store_id": store_id,
            "movement_type": movement_type, "quantity_delta": delta, "reason": reason,
        }
        session.metadata["pending_stock_adjustment"] = draft
        self.session_store.save_session(session)
        verb = "add" if delta > 0 else "reduce"
        return (f"Please confirm: {verb} {abs(delta)} units of {product_id} at {store_id} ({reason}). "
                f"Current stock is {stock.inventory_level}; afterward it will be {after}. "
                "This will change inventory only; it will not create a sale or revenue."), {
                    "adjustment_status": "awaiting_confirmation", "pending_adjustment": draft,
                    "quantity_before": stock.inventory_level, "quantity_after": after,
                }, Intent.RECEIVE_STOCK if receives else Intent.ADJUST_STOCK

    def _get_or_create_session(self, session_id: Optional[str], user_id: Optional[str] = None) -> SessionData:
        """Get existing session or create new one.

        If a session_id is requested but no session exists with it (fresh
        browser, expired Redis TTL, wiped localStorage) the id is ADOPTED
        for the new session rather than replaced with a random one. This is
        what makes refresh/resume stable: the frontend's stored id stays
        valid, and the conversation simply continues from an empty history.
        """
        if session_id:
            session = self.session_store.get_session(session_id)
            if session:
                return session
            log.warning("Session %s not found, creating new with requested id", session_id)
            return self.session_store.create_session(user_id, session_id=session_id)

        # Create new session
        return self.session_store.create_session(user_id)

    def handle_message(
        self,
        db: Session,
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        on_stage: Optional[Callable[[str], None]] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> ConversationChatResponse:
        """
        Main entry point for handling a chat message with conversation memory.

        `on_stage` / `on_token` are optional progress hooks used by the
        WebSocket streaming endpoint (app/routers/ws.py). They are pure
        observability: leaving them out (REST path, tests) changes nothing
        about the returned response.
        """
        # 1. Get or create session
        session = self._get_or_create_session(session_id, user_id)
        session_id = session.session_id

        # 2. Get context manager for this session
        cm = self._get_or_create_context_manager(session_id)

        # 3. Check for context commands
        cmd_response = cm.handle_command(message)
        if cmd_response is not None:
            # Save command turn
            self._save_turn(session_id, message, cmd_response, None, "command", {})
            return ConversationChatResponse(
                message=cmd_response,
                intent=None,
                entities={},
                parse_method="command",
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        # Sale writes are a deliberate two-step action: prepare a preview,
        # then call the same transaction as Sales > Record a sale only after
        # an explicit confirmation for this session.
        pending_sale = session.metadata.get("pending_sale") or {}
        pending_adjustment = session.metadata.get("pending_stock_adjustment") or {}
        pending_clarification = session.metadata.get("pending_action_clarification") or {}
        planned_request = None

        # Let Gemini interpret fresh turns before keyword routing. Follow-up
        # answers and confirmations stay deterministic so the model cannot
        # reinterpret "yes", a quantity, or a clarification as a new request.
        if not (pending_sale or pending_adjustment):
            planned_request = plan_request(message, self.llm_client, cm.get_context_for_llm())
            planned_request = prefer_explicit_stock_action(message, planned_request)

        # A new command in the opposite direction must not inherit the
        # movement type from an earlier, unconfirmed preview. For example,
        # "deduct 25 ..." after a pending delivery must start a new request,
        # not reuse DELIVERY and turn the deduction into an addition.
        incoming_receive = bool(_RECEIVE_ACTION_RE.search(message))
        incoming_reduction = bool(_STOCK_REDUCTION_ACTION_RE.search(message))
        pending_is_delivery = pending_adjustment.get("movement_type") == "DELIVERY"
        if pending_adjustment and (
            (pending_is_delivery and incoming_reduction)
            or (not pending_is_delivery and incoming_receive)
        ):
            session.metadata.pop("pending_stock_adjustment", None)
            pending_adjustment = {}
            self.session_store.save_session(session)

        if pending_clarification and _SALE_CLARIFICATION_RE.search(message):
            session.metadata.pop("pending_action_clarification", None)
            product_id = pending_clarification.get("product_id")
            store_id = pending_clarification.get("store_id")
            quantity = pending_clarification.get("quantity")
            sale_request = "I sold" + (f" {quantity} units" if quantity else "")
            sale_request += (f" of {product_id}" if product_id else "") + (f" at {store_id}" if store_id else "")
            sale_request += f". {message}"
            response_text, data, intent = self._handle_chat_sale(db, session, sale_request)
            self._save_turn(session_id, message, response_text, intent, "rules", data, extract_entities(sale_request))
            return ConversationChatResponse(message=response_text, intent=intent,
                entities=extract_entities(sale_request).model_dump(), parse_method="rules", data=data,
                session_id=session_id, context=cm.get_context_for_llm())
        if pending_clarification and _RECEIVE_ACTION_RE.search(message):
            session.metadata.pop("pending_action_clarification", None)
            combined_request = f"{pending_clarification.get('message', '')} {message}"
            response_text, data, intent = self._handle_stock_adjustment(db, session, combined_request)
            self._save_turn(session_id, message, response_text, intent, "rules", data, extract_entities(combined_request))
            return ConversationChatResponse(message=response_text, intent=intent,
                entities=extract_entities(combined_request).model_dump(), parse_method="rules", data=data,
                session_id=session_id, context=cm.get_context_for_llm())
        if pending_clarification and _ADJUSTMENT_CLARIFICATION_RE.search(message):
            session.metadata.pop("pending_action_clarification", None)
            combined_request = f"{pending_clarification.get('message', '')} {message}"
            response_text, data, intent = self._handle_stock_adjustment(db, session, combined_request)
            self._save_turn(session_id, message, response_text, intent, "rules", data, extract_entities(combined_request))
            return ConversationChatResponse(message=response_text, intent=intent,
                entities=extract_entities(combined_request).model_dump(), parse_method="rules", data=data,
                session_id=session_id, context=cm.get_context_for_llm())
        if pending_adjustment and _SALE_REQUEST_RE.search(message):
            response_text = "There is a stock adjustment waiting for confirmation. Confirm or cancel it before starting a sale."
            self._save_turn(session_id, message, response_text, Intent.UNKNOWN, "rules", {})
            return ConversationChatResponse(message=response_text, intent=Intent.UNKNOWN, entities={},
                parse_method="rules", data=None, session_id=session_id, context=cm.get_context_for_llm())
        if (pending_sale and _INVENTORY_ACTION_RE.search(message)
                and not _STOCK_HISTORY_QUERY_RE.search(message)
                and not _is_pending_sale_reply(message, pending_sale)):
            response_text = "There is a sale waiting for confirmation or details. Finish or cancel it before starting a stock adjustment."
            self._save_turn(session_id, message, response_text, Intent.UNKNOWN, "rules", {})
            return ConversationChatResponse(message=response_text, intent=Intent.UNKNOWN, entities={},
                parse_method="rules", data=None, session_id=session_id, context=cm.get_context_for_llm())
        if pending_adjustment and (_YES_RE.fullmatch(message.strip()) or _NO_RE.fullmatch(message.strip())):
            response_text, data, action_intent = self._handle_stock_adjustment(db, session, message)
            self._save_turn(session_id, message, response_text, action_intent, "rules", data, extract_entities(message))
            return ConversationChatResponse(message=response_text, intent=action_intent,
                entities=extract_entities(message).model_dump(), parse_method="rules", data=data,
                session_id=session_id, context=cm.get_context_for_llm())

        # Structured action plans are proposals only. Reuse the established
        # backend validation and preview/confirmation handlers for all writes.
        if planned_request and planned_request.request_type in {"sale", "receive", "decrease"}:
            proposed = planned_request.arguments
            product_id = proposed.get("product_id") or pending_clarification.get("product_id")
            store_id = proposed.get("store_id") or pending_clarification.get("store_id")
            quantity = planned_request.quantity or pending_clarification.get("quantity")
            quantity_text = f"{quantity} units" if quantity is not None else ""
            product_text = f"of product {product_id}" if product_id else ""
            store_text = f"at store {store_id}" if store_id else ""
            details = " ".join(part for part in (quantity_text, product_text, store_text) if part)
            source = message
            session.metadata.pop("pending_action_clarification", None)
            if planned_request.request_type == "sale" or (
                planned_request.request_type == "decrease" and planned_request.reason == "sale"
            ):
                canonical = f"I sold {details}. {source}"
                if planned_request.unit_price is not None and not _SALE_PRICE_RE.search(source):
                    canonical += f" at ${planned_request.unit_price:.2f}"
                if planned_request.unit_cost is not None and not _SALE_COST_RE.search(source):
                    canonical += f" cost ${planned_request.unit_cost:.2f}"
                response_text, data, action_intent = self._handle_chat_sale(db, session, canonical)
            elif planned_request.request_type == "receive":
                response_text, data, action_intent = self._handle_stock_adjustment(
                    db, session, f"received {details}. {source}"
                )
            elif planned_request.reason in {"damage", "loss", "waste", "correction"}:
                reason_words = {"damage": "damaged", "loss": "lost", "waste": "wasted", "correction": "manual correction"}
                response_text, data, action_intent = self._handle_stock_adjustment(
                    db, session, f"remove {details} {reason_words[planned_request.reason]}. {source}"
                )
            else:
                clarification = {
                    "message": source, "product_id": product_id,
                    "store_id": store_id, "quantity": quantity,
                }
                session.metadata["pending_action_clarification"] = clarification
                self.session_store.save_session(session)
                response_text = (
                    "I understood that you want to decrease stock. Were these units sold to a customer, "
                    "or removed for another reason? I won't change anything until you clarify."
                )
                data = {"adjustment_status": "needs_action_type", "pending_action": clarification}
                action_intent = Intent.UNKNOWN
            if isinstance(data, dict):
                data.setdefault("request_plan", planned_request.model_dump(mode="json"))
            self._save_turn(session_id, message, response_text, action_intent, "gemini_plan", data,
                            extract_entities(message))
            return ConversationChatResponse(message=response_text, intent=action_intent,
                entities=extract_entities(message).model_dump(), parse_method="gemini_plan", data=data,
                session_id=session_id, context=cm.get_context_for_llm())
        if _RECEIVE_ACTION_RE.search(message) and not _STOCK_HISTORY_QUERY_RE.search(message):
            response_text, data, action_intent = self._handle_stock_adjustment(db, session, message)
            self._save_turn(session_id, message, response_text, action_intent, "rules", data, extract_entities(message))
            return ConversationChatResponse(message=response_text, intent=action_intent,
                entities=extract_entities(message).model_dump(), parse_method="rules", data=data,
                session_id=session_id, context=cm.get_context_for_llm())
        if (_INVENTORY_ACTION_RE.search(message)
                and re.search(r"\b(?:remove|subtract|reduce|deduct|decrease)\b", message, re.I)
                and not (_SALE_REQUEST_RE.search(message)
                         or re.search(r"\b(?:sale|sold|customer|damag(?:e|ed)|broken|expired|wast(?:e|ed)|lost|missing)\b", message, re.I))
                and not pending_sale and not pending_adjustment):
            extracted = extract_entities(message)
            qty_match = _ACTION_QUANTITY_RE.search(re.sub(r"\b[PS]\d+\b", " ", message, flags=re.I))
            session.metadata["pending_action_clarification"] = {
                "message": message, "product_id": extracted.product_id, "store_id": extracted.store_id,
                "quantity": int(qty_match.group(1)) if qty_match else None,
            }
            self.session_store.save_session(session)
            response_text = "Should I record those units as a customer sale, or as a non-sale stock adjustment (for example, damaged or missing stock)? I won't change anything until you confirm the type."
            self._save_turn(session_id, message, response_text, Intent.UNKNOWN, "rules", {})
            return ConversationChatResponse(message=response_text, intent=Intent.UNKNOWN, entities=extracted.model_dump(),
                parse_method="rules", data=None, session_id=session_id, context=cm.get_context_for_llm())
        if _SALE_REQUEST_RE.search(message) or (pending_sale and _is_pending_sale_reply(message, pending_sale)):
            result = self._handle_chat_sale(db, session, message)
            response_text, data, intent = result
            self._save_turn(session_id, message, response_text, intent, "rules", data, extract_entities(message))
            return ConversationChatResponse(message=response_text, intent=intent,
                entities=extract_entities(message).model_dump(), parse_method="rules", data=data,
                session_id=session_id, context=cm.get_context_for_llm())

        # Deterministic stock routing remains available when Gemini is unavailable.
        if not _STOCK_HISTORY_QUERY_RE.search(message) and (
            _INVENTORY_ACTION_RE.search(message)
            or (pending_adjustment and _is_pending_adjustment_reply(message, pending_adjustment))
        ):
            response_text, data, action_intent = self._handle_stock_adjustment(db, session, message)
            self._save_turn(session_id, message, response_text, action_intent, "rules", data, extract_entities(message))
            return ConversationChatResponse(message=response_text, intent=action_intent,
                entities=extract_entities(message).model_dump(), parse_method="rules", data=data,
                session_id=session_id, context=cm.get_context_for_llm())

        if is_stock_write_request(message) and not _STOCK_HISTORY_QUERY_RE.search(message):
            entities_for_clarification = extract_entities(message)
            quantity_match = _ACTION_QUANTITY_RE.search(re.sub(r"\b[PS]\d+\b", " ", message, flags=re.I))
            session.metadata["pending_action_clarification"] = {
                "message": message,
                "product_id": entities_for_clarification.product_id,
                "store_id": entities_for_clarification.store_id,
                "quantity": int(quantity_match.group(1)) if quantity_match else None,
            }
            self.session_store.save_session(session)
            response_text = "I can record customer sales, deliveries, and stock adjustments separately. Tell me whether the units were sold, received, damaged, or removed for another reason."
            self._save_turn(session_id, message, response_text, Intent.UNKNOWN, "rules", {})
            return ConversationChatResponse(message=response_text, intent=Intent.UNKNOWN, entities={},
                parse_method="rules", data=None, session_id=session_id, context=cm.get_context_for_llm())

        # Prefer checked-in documentation for explicit "how does this project
        # work?" questions so a generic analytics intent doesn't ask for an SKU.
        if (not (planned_request and planned_request.request_type == "read")
                and _PROJECT_QUESTION_RE.search(message)
                and not re.search(r"\bP0*\d{1,4}\b", message, re.I)):
            knowledge = project_knowledge_service.answer(message, self.llm_client)
            if knowledge:
                response_text, data = knowledge["message"], knowledge["data"]
                self._save_turn(session_id, message, response_text, Intent.UNKNOWN, "knowledge", data, extract_entities(message))
                return ConversationChatResponse(message=response_text, intent=Intent.UNKNOWN,
                    entities=extract_entities(message).model_dump(), parse_method="knowledge", data=data,
                    session_id=session_id, context=cm.get_context_for_llm())

        # 4. Parse message with context injection
        # First, inject context into entities
        _notify(on_stage, STAGE_PARSING)
        if planned_request and planned_request.request_type == "read":
            intent = TOOLS_BY_NAME[planned_request.tool].intent
            entities = Entities(**planned_request.arguments)
            method = "gemini_plan"
        else:
            intent, entities, method = parser.parse(
                message, llm_client=None, context=cm.get_context_for_llm()
            )

        # Inject conversation context (resolves pronouns, carries entities)
        entities = cm.inject_context(message, entities)

        # 4b. Context-only follow-ups ("How much at that store?") carry the
        # previous product-scoped intent forward instead of becoming UNKNOWN.
        if intent == Intent.UNKNOWN:
            carried_intent = self._carryover_intent(session, message)
            if carried_intent is not None:
                intent, method = carried_intent, "context"

        # 5. Handle HELP and UNKNOWN
        if intent == Intent.HELP:
            response_text = HELP_TEXT
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        if intent == Intent.UNKNOWN:
            if re.search(r"\b(profit|margin)\b", message, re.I):
                response_text = "I can calculate gross profit/loss for recorded sales when their cost price is available. Add a product cost under Inventory, then record sales with selling price and cost. Historical imported sales have no cost data, so their profit cannot be calculated."
                self._save_turn(session_id, message, response_text, intent, "rules", {})
                return ConversationChatResponse(message=response_text, intent=intent,
                    entities=entities.model_dump(), parse_method="rules", data=None,
                    session_id=session_id, context=cm.get_context_for_llm())
            knowledge = project_knowledge_service.answer(message, self.llm_client)
            if knowledge:
                response_text = knowledge["message"]
                data = knowledge["data"]
                self._save_turn(session_id, message, response_text, intent, "knowledge", data, entities)
                return ConversationChatResponse(
                    message=response_text,
                    intent=intent,
                    entities=entities.model_dump(),
                    parse_method="knowledge",
                    data=data,
                    session_id=session_id,
                    context=cm.get_context_for_llm(),
                )
            response_text = "I'm not sure what you're asking. " + HELP_TEXT
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        # 6. Validate product entity against real database
        if intent in PRODUCT_REQUIRED_INTENTS and entities.product_id:
            if not product_repository.product_exists(db, entities.product_id):
                response_text = f"I couldn't find product '{entities.product_id}' in the current inventory data."
                self._save_turn(session_id, message, response_text, intent, method, {})
                return ConversationChatResponse(
                    message=response_text,
                    intent=intent,
                    entities=entities.model_dump(),
                    parse_method=method,
                    data=None,
                    session_id=session_id,
                    context=cm.get_context_for_llm(),
                )

        if entities.product_reference and intent in {
            Intent.CURRENT_STOCK, Intent.REVENUE_ANALYSIS, Intent.FINANCIAL_ANALYSIS,
            Intent.STORE_PROFITABILITY, Intent.DEMAND_FORECAST, Intent.STOCKOUT_RISK,
            Intent.REORDER_RECOMMENDATION, Intent.SALES_TREND, Intent.TOP_SELLING,
            Intent.BOTTOM_SELLING, Intent.PRODUCT_INFO,
            Intent.LOW_STOCK, Intent.LOW_STOCK_FAST_SELLING,
            Intent.STOCK_HISTORY,
        }:
            response_text = (f"I can't match the product name '{entities.product_reference}' to a catalog entry. "
                             "This catalog currently identifies products by product ID; please provide its P-code so I can check the right item.")
            self._save_turn(session_id, message, response_text, intent, method, {}, entities)
            return ConversationChatResponse(message=response_text, intent=intent,
                entities=entities.model_dump(), parse_method=method, data=None,
                session_id=session_id, context=cm.get_context_for_llm())

        # 7. Execute tool
        tool = TOOLS.get(intent)
        if tool is None:
            response_text = HELP_TEXT
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        try:
            _notify(on_stage, STAGE_QUERYING)
            data = tool(db, entities)
        except MissingEntityError as e:
            response_text = str(e)
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )
        except NotFoundError as e:
            response_text = str(e)
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )
        except InvalidRequestError as e:
            response_text = str(e)
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        # 8. Generate response (LLM phrasing or template)
        _notify(on_stage, STAGE_PHRASING)
        response_text = _llm_phrase_response(self.llm_client, message, intent, data, on_token=on_token)
        if response_text is None:
            response_text = _template_response(intent, entities, data)

        # 9. Update conversation context
        cm.process_turn(
            session_id=session_id,
            user_message=message,
            entities=entities,
            intent=intent,
            parse_method=method,
            response=response_text,
            data=data,
        )

        # 10. Save turn to session store
        self._save_turn(session_id, message, response_text, intent, method, data, entities)

        # 11. Return response with context
        return ConversationChatResponse(
            message=response_text,
            intent=intent,
            entities=entities.model_dump(),
            parse_method=method,
            data=data,
            session_id=session_id,
            context=cm.get_context_for_llm(),
        )

    def _save_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        intent: Optional[Intent],
        parse_method: str,
        data: dict,
        entities: Optional[Entities] = None,
    ) -> None:
        """Save a turn to the session store."""
        session = self.session_store.get_session(session_id)
        turn = {
            "turn_index": len(session.turns) if session else 0,
            "user_message": user_message,
            "assistant_response": assistant_response,
            "intent": intent.value if intent else None,
            "entities": entities.model_dump() if entities else {},
            "parse_method": parse_method,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.session_store.add_turn(session_id, turn)

    def get_session_info(self, session_id: str) -> Optional[dict]:
        """Get session info for API."""
        session = self.session_store.get_session(session_id)
        if not session:
            return None
        cm = self._context_managers.get(session_id)
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "turn_count": len(session.turns),
            "summary": session.summary,
            "preview": _preview_turns(session.turns),
            "active_entities": cm.entity_tracker.get_active_entities() if cm else {},
            "current_topic": cm.topic_stack.peek().name if cm and cm.topic_stack.peek() else None,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        """List sessions for a user."""
        sessions = self.session_store.list_sessions(user_id, limit)
        result = []
        for session in sessions:
            cm = self._context_managers.get(session.session_id)
            result.append({
                "session_id": session.session_id,
                "user_id": session.user_id,
                "turn_count": len(session.turns),
                "summary": session.summary,
                "preview": _preview_turns(session.turns),
                "active_entities": cm.entity_tracker.get_active_entities() if cm else {},
                "current_topic": cm.topic_stack.peek().name if cm and cm.topic_stack.peek() else None,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            })
        return result

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        self.session_store.delete_session(session_id)
        self._context_managers.pop(session_id, None)
        return True

    def get_session_history(self, session_id: str) -> Optional[dict]:
        """Get full session history."""
        session = self.session_store.get_session(session_id)
        if not session:
            return None
        cm = self._context_managers.get(session_id)
        return {
            "session_id": session.session_id,
            "turns": session.turns,
            "summary": session.summary,
            "context": cm.get_context_for_llm() if cm else {},
        }


PREVIEW_MAX_LENGTH = 80


def _preview_turns(turns: list[dict]) -> Optional[str]:
    """First user message, truncated -- a cheap sidebar label."""
    for turn in turns:
        text = (turn.get("user_message") or "").strip()
        if text:
            return text if len(text) <= PREVIEW_MAX_LENGTH else text[:PREVIEW_MAX_LENGTH] + "…"
    return None


# --- Global instance (for backward compatibility) ---------------------------

_chat_session_manager: Optional[ChatSessionManager] = None


def get_chat_session_manager(llm_client=None) -> ChatSessionManager:
    """Get or create the global chat session manager.

    A supplied `llm_client` wins even when a manager already exists without
    one (e.g. an earlier stateless call in the same process created the
    default manager). Otherwise `handle_chat_message(llm_client=...)` would
    silently ignore the caller's client -- both a test-ordering hazard and a
    real API footgun.
    """
    global _chat_session_manager
    if _chat_session_manager is None or (llm_client is not None and _chat_session_manager.llm_client is None):
        _chat_session_manager = ChatSessionManager(llm_client)
    return _chat_session_manager


def set_chat_session_manager(manager: ChatSessionManager) -> None:
    """Override the global chat session manager (for testing)."""
    global _chat_session_manager
    _chat_session_manager = manager


# --- Backward-compatible entry point ----------------------------------------

def handle_chat_message(
    db: Session,
    message: str,
    llm_client=None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> ChatResponse:
    """
    Backward-compatible entry point.
    Returns the original ChatResponse schema (without session_id/context).
    """
    manager = get_chat_session_manager(llm_client)
    response = manager.handle_message(db, message, session_id, user_id)

    # Convert to legacy ChatResponse
    return ChatResponse(
        message=response.message,
        intent=response.intent,
        entities=Entities(**response.entities) if response.entities else Entities(),
        parse_method=response.parse_method,
        data=response.data,
    )
