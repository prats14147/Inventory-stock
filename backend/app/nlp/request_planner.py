"""Constrained Gemini interpretation for inventory chat requests.

Gemini proposes a registered read capability or a stock action. Callers still
validate entities and values against the database and require confirmation for
every write.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.nlp.entities import Entities
from app.nlp.rules import extract_entities
from app.nlp.tool_registry import TOOLS_BY_NAME

log = logging.getLogger("nlp.request_planner")


class RequestPlan(BaseModel):
    request_type: Literal["read", "sale", "receive", "decrease", "unclear", "not_inventory"]
    tool: str | None = None
    arguments: dict = Field(default_factory=dict)
    quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    unit_price: float | None = Field(default=None, ge=0)
    unit_cost: float | None = Field(default=None, ge=0)
    reason: Literal["sale", "receipt", "damage", "loss", "waste", "correction", "unknown"] = "unknown"
    confidence: float = Field(ge=0, le=1)


_SYSTEM_PROMPT = """You are the request interpreter for an inventory-management application.
Return only JSON matching this shape:
{"request_type":"read|sale|receive|decrease|unclear|not_inventory","tool":null,"arguments":{},"quantity":null,"unit_price":null,"unit_cost":null,"reason":"sale|receipt|damage|loss|waste|correction|unknown","confidence":0.0}

For read requests choose exactly one tool name from this allowlist:
__REGISTERED_TOOLS__
Use that tool's matching filters in arguments. Never invent IDs, dates, or quantities.
For stock changes, classify what the user means, including typos, passive voice,
and conversational phrasing:
- goods received / add / increase / restock => receive
- sold to a customer / customer bought => sale
- remove / deduct / reduce => decrease; reason=unknown unless explicitly sold or a reason such as damage is stated
- forecasts and questions about stock/sales/profit => read, using the closest tool
- questions about how the software/project itself works => not_inventory
Quantity means units, not numbers inside P/S identifiers. Capture selling price only
when the user explicitly states it. Do not use product cost as selling price.
If the message is a short clarification (for example "for sales"), interpret it
using the supplied conversation context. For a read request, use a registered tool.
If meaning remains unclear, use unclear with low confidence. Do not answer the user
and do not claim anything was changed. This is only a structured proposal."""


def plan_request(message: str, llm_client, context: dict | None = None) -> RequestPlan | None:
    if llm_client is None:
        return None
    tool_menu = "\n".join(f"- {t.name}: {t.description}" for t in TOOLS_BY_NAME.values())
    payload = json.dumps({"message": message, "conversation_context": context or {}}, ensure_ascii=False)
    try:
        raw = llm_client.complete_json(_SYSTEM_PROMPT.replace("__REGISTERED_TOOLS__", tool_menu), payload)
        if isinstance(raw, str):
            raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.I)
            raw = json.loads(raw)
        plan = RequestPlan.model_validate(raw)
    except Exception as exc:
        log.info("Gemini request planning unavailable: %s", exc)
        return None

    if plan.request_type == "read":
        if plan.tool not in TOOLS_BY_NAME:
            return None
        args = plan.arguments if isinstance(plan.arguments, dict) else {}
        mentioned = extract_entities(message)
        # IDs and common filters must be grounded in the user's words. Session
        # context can fill missing IDs below, but Gemini cannot invent them.
        grounded = Entities(**{k: v for k, v in args.items() if k in Entities.model_fields})
        for key in ("product_id", "store_id", "category"):
            if getattr(grounded, key) != getattr(mentioned, key):
                setattr(grounded, key, getattr(mentioned, key))
        grounded.date_range = mentioned.date_range
        grounded.date = mentioned.date
        grounded.forecast_horizon = mentioned.forecast_horizon
        grounded.group_by = mentioned.group_by
        grounded.sort_order = mentioned.sort_order
        plan.arguments = grounded.model_dump(exclude_none=True)
    else:
        mentioned = extract_entities(message)
        # The model may normalize the action and quantity but may not create IDs.
        plan.arguments = {
            **plan.arguments,
            "product_id": mentioned.product_id,
            "store_id": mentioned.store_id,
        }
    return plan if plan.confidence >= 0.65 else None


def prefer_explicit_stock_action(message: str, plan: RequestPlan | None = None) -> RequestPlan | None:
    """Keep explicit transaction wording from being mistaken for a stock query.

    Gemini is still the general interpreter. This narrow guard handles common
    terse phrasing such as "P0002 stock 4000 sold at S003" and misspelled
    "delievery ... stock of 3000". The result only enters the normal preview
    handlers; it can never write stock directly.
    """
    if re.search(r"\b(?:how many|how much|what|show|list|when|trend|forecast|history)\b", message, re.I):
        return plan

    entities = extract_entities(message)
    if not (entities.product_id and entities.store_id):
        return plan

    without_ids = re.sub(r"\b[PS]\d+\b", " ", message, flags=re.I)
    quantity_match = re.search(
        r"\b(?:stock|quantity|amount)\s+(?:of|is|:)?\s*([\d,]+)\b|"
        r"\b([\d,]+)\s*(?:units?|items?|products?|stocks?|stoks?)\b",
        without_ids,
        re.I,
    )
    if not quantity_match:
        return plan
    quantity = int(next(value for value in quantity_match.groups() if value).replace(",", ""))
    if quantity <= 0:
        return plan

    if re.search(r"\b(?:sold|sell|selling)\b", message, re.I):
        return RequestPlan(request_type="sale", quantity=quantity, reason="sale", confidence=1.0,
                           arguments={"product_id": entities.product_id, "store_id": entities.store_id})

    # Accept frequent misspellings while keeping plain stock questions on the
    # read path. This requires both a receipt term and a quantity plus IDs.
    if re.search(r"\b(?:receiv\w*|reciev\w*|restock\w*|deliver\w*|delievery|delieverd)\b", message, re.I):
        return RequestPlan(request_type="receive", quantity=quantity, reason="receipt", confidence=1.0,
                           arguments={"product_id": entities.product_id, "store_id": entities.store_id})

    # "sales of P... with stock of 4000" is a terse sale entry, while ordinary
    # sales questions without a transaction quantity remain read requests.
    if re.search(r"\bsales?\s+of\b", message, re.I) and re.search(r"\bstock\s+(?:of|is|:)", message, re.I):
        return RequestPlan(request_type="sale", quantity=quantity, reason="sale", confidence=1.0,
                           arguments={"product_id": entities.product_id, "store_id": entities.store_id})

    return plan
