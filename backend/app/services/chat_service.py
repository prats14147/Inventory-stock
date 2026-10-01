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
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.nlp import parser
from app.nlp.entities import Entities
from app.nlp.intent import PRODUCT_REQUIRED_INTENTS, Intent
from app.nlp.llm_client import LLMUnavailableError
from app.nlp.prompts import RESPONSE_GENERATION_SYSTEM_PROMPT
from app.repositories import product_repository
from app.schemas.chat import ChatResponse
from app.services import forecast_service, inventory_service, reorder_service, sales_service, stockout_service
from app.services.errors import InvalidRequestError, NotFoundError

log = logging.getLogger("chat_service")


class MissingEntityError(Exception):
    """Raised when an intent needs an entity (e.g. product_id) that wasn't extracted."""


HELP_TEXT = (
    "I can help with: current stock for a product, which products are low on stock, "
    "top or bottom selling products, sales trends, demand forecasts, stockout risk, "
    "and reorder recommendations. Try asking something like \"How much stock does "
    "P0001 have?\" or \"Should I reorder P0007?\""
)


# --- Tool functions (spec section 33) --------------------------------------

def _tool_current_inventory(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like to check the stock for?")
    return inventory_service.get_product_inventory(db, entities.product_id).model_dump(mode="json")


def _tool_low_stock(db: Session, entities: Entities) -> dict:
    return inventory_service.get_low_stock(db).model_dump(mode="json")


def _tool_top_selling(db: Session, entities: Entities) -> dict:
    return sales_service.get_top_products(db, limit=10).model_dump(mode="json")


def _tool_bottom_selling(db: Session, entities: Entities) -> dict:
    return sales_service.get_bottom_products(db, limit=10).model_dump(mode="json")


def _tool_sales_trend(db: Session, entities: Entities) -> dict:
    result = sales_service.get_sales_trend(
        db, granularity="monthly", product_id=entities.product_id, category=entities.category
    )
    return result.model_dump(mode="json")


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
    if not entities.product_id:
        raise MissingEntityError("Which product would you like to check stockout risk for?")
    return stockout_service.calculate_stockout_risk(db, entities.product_id).model_dump(mode="json")


def _tool_reorder_recommendation(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like a reorder recommendation for?")
    return reorder_service.calculate_reorder(db, entities.product_id).model_dump(mode="json")


def _tool_category_analysis(db: Session, entities: Entities) -> dict:
    return {"categories": [c.model_dump(mode="json") for c in sales_service.get_category_analysis(db)]}


def _tool_store_analysis(db: Session, entities: Entities) -> dict:
    return {"stores": [s.model_dump(mode="json") for s in sales_service.get_store_analysis(db)]}


TOOLS = {
    Intent.CURRENT_STOCK: _tool_current_inventory,
    Intent.LOW_STOCK: _tool_low_stock,
    Intent.TOP_SELLING: _tool_top_selling,
    Intent.BOTTOM_SELLING: _tool_bottom_selling,
    Intent.SALES_TREND: _tool_sales_trend,
    Intent.PRODUCT_INFO: _tool_product_info,
    Intent.DEMAND_FORECAST: _tool_forecast_demand,
    Intent.STOCKOUT_RISK: _tool_stockout_risk,
    Intent.REORDER_RECOMMENDATION: _tool_reorder_recommendation,
    Intent.CATEGORY_ANALYSIS: _tool_category_analysis,
    Intent.STORE_ANALYSIS: _tool_store_analysis,
}


# --- Deterministic template fallback (used when no LLM / LLM unavailable) --

def _template_response(intent: Intent, entities: Entities, data: dict) -> str:
    if intent == Intent.CURRENT_STOCK:
        return f"{data['product_id']} currently has {data['total_inventory']:.0f} units in stock (as of {data['as_of_date']}, across {len(data['stores'])} stores)."
    if intent == Intent.LOW_STOCK:
        return f"{data['count']} store-product combinations are below the low-stock threshold of {data['threshold']} units (as of {data['as_of_date']})."
    if intent == Intent.TOP_SELLING:
        top = data["products"][:3]
        names = ", ".join(f"{p['product_id']} ({p['total_units_sold']:.0f} units)" for p in top)
        return f"The top-selling products are: {names}."
    if intent == Intent.BOTTOM_SELLING:
        bottom = data["products"][:3]
        names = ", ".join(f"{p['product_id']} ({p['total_units_sold']:.0f} units)" for p in bottom)
        return f"The lowest-selling products are: {names}."
    if intent == Intent.DEMAND_FORECAST:
        return (
            f"Forecast demand for {data['product_id']} over the next {data['model_horizon_days']} days "
            f"(by {data['target_date']}) is approximately {data['forecast_total_units']:.0f} units across all stores."
        )
    if intent == Intent.STOCKOUT_RISK:
        return f"{data['product_id']} has {data['risk']} stockout risk. {data['reason']}"
    if intent == Intent.REORDER_RECOMMENDATION:
        return (
            f"{data['product_id']} currently has {data['current_inventory']:.0f} units. Estimated demand over the "
            f"{data['assumptions']['lead_time_days']}-day lead time is {data['forecast_lead_time_demand']:.1f} units, "
            f"with a safety stock of {data['safety_stock']:.1f}. Recommended reorder quantity: "
            f"{data['recommended_reorder_quantity']:.0f} units."
        )
    if intent == Intent.CATEGORY_ANALYSIS:
        top = data["categories"][:3]
        names = ", ".join(f"{c['category']} ({c['total_units_sold']:.0f} units)" for c in top)
        return f"Top categories by units sold: {names}."
    if intent == Intent.STORE_ANALYSIS:
        top = data["stores"][:3]
        names = ", ".join(f"{s['store_id']} ({s['total_units_sold']:.0f} units)" for s in top)
        return f"Top stores by units sold: {names}."
    if intent == Intent.SALES_TREND:
        n_points = len(data["points"])
        return f"Here's the {data['granularity']} sales trend ({n_points} data points)."
    if intent == Intent.PRODUCT_INFO:
        inv = data["inventory"]
        return f"{inv['product_id']}: {inv['total_inventory']:.0f} units in stock as of {inv['as_of_date']}."
    return "Here's what I found."


def _llm_phrase_response(llm_client, message: str, intent: Intent, data: dict) -> str | None:
    if llm_client is None:
        return None
    try:
        payload = json.dumps({"user_question": message, "intent": intent.value, "verified_data": data})
        return llm_client.complete_text(RESPONSE_GENERATION_SYSTEM_PROMPT, payload).strip()
    except LLMUnavailableError as e:
        log.warning("LLM unavailable for response phrasing, using template: %s", e)
        return None


# --- Main entry point --------------------------------------------------

def handle_chat_message(db: Session, message: str, llm_client=None) -> ChatResponse:
    intent, entities, method = parser.parse(message, llm_client=llm_client)

    if intent == Intent.HELP:
        return ChatResponse(message=HELP_TEXT, intent=intent, entities=entities, parse_method=method, data=None)

    if intent == Intent.UNKNOWN:
        return ChatResponse(
            message="I'm not sure what you're asking. " + HELP_TEXT,
            intent=intent,
            entities=entities,
            parse_method=method,
            data=None,
        )

    # Validate product entity against the real database BEFORE computing
    # anything -- never let a made-up or misspelled product ID reach a
    # backend calculation (spec section 31 / 55).
    if intent in PRODUCT_REQUIRED_INTENTS and entities.product_id:
        if not product_repository.product_exists(db, entities.product_id):
            return ChatResponse(
                message=f"I couldn't find product '{entities.product_id}' in the current inventory data.",
                intent=intent,
                entities=entities,
                parse_method=method,
                data=None,
            )

    tool = TOOLS.get(intent)
    if tool is None:
        return ChatResponse(message=HELP_TEXT, intent=intent, entities=entities, parse_method=method, data=None)

    try:
        data = tool(db, entities)
    except MissingEntityError as e:
        return ChatResponse(message=str(e), intent=intent, entities=entities, parse_method=method, data=None)
    except NotFoundError as e:
        return ChatResponse(message=str(e), intent=intent, entities=entities, parse_method=method, data=None)
    except InvalidRequestError as e:
        return ChatResponse(message=str(e), intent=intent, entities=entities, parse_method=method, data=None)

    response_text = _llm_phrase_response(llm_client, message, intent, data)
    if response_text is None:
        response_text = _template_response(intent, entities, data)

    return ChatResponse(message=response_text, intent=intent, entities=entities, parse_method=method, data=data)
