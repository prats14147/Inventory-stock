"""Structured semantic parsing for stock-changing chat requests.

The model only proposes an interpretation. It does not choose a database
operation, validate inventory, or execute a write; chat_service performs
those checks and still requires explicit confirmation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.nlp.rules import extract_entities

log = logging.getLogger("nlp.action_parser")


class StockActionPlan(BaseModel):
    operation: Literal["sale", "receive", "decrease", "unknown", "not_stock_action"]
    quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    reason: Literal["sale", "receipt", "damage", "loss", "waste", "correction", "unknown"] = "unknown"
    confidence: float = Field(ge=0, le=1)
    product_id: str | None = None
    store_id: str | None = None


_PROMPT = """You interpret one user's message for an inventory assistant.
Return ONLY JSON with this shape:
{"operation":"sale|receive|decrease|unknown|not_stock_action","quantity":null,"reason":"sale|receipt|damage|loss|waste|correction|unknown","confidence":0.0,"product_id":null,"store_id":null}

Interpret meaning, not exact keywords. Examples:
- "add 100 stocks", "put 100 more units on the shelf", "we got 100 units" => receive, receipt
- "I sold 25 units" => sale, sale
- "deduct 25 units" or "take 25 off the count" => decrease, unknown (the user has not said if it was a sale)
- "remove 5 because they broke" => decrease, damage
- an inventory question, forecast question, or project question => not_stock_action

Rules:
- A sale is explicit customer selling. Do not assume every decrease is a sale.
- Increase/receipt language means a positive quantity. Decrease/removal language means a negative quantity.
- Quantity must be the amount the user asks to change, not an ID number.
- Return null for missing quantity or IDs. Never invent product/store IDs.
- Keep confidence below 0.75 when the action or quantity is unclear.
- The JSON is only a proposal; it must never cause an action by itself."""


def parse_stock_action(message: str, llm_client) -> StockActionPlan | None:
    """Use the configured language model to interpret a stock command safely.

    Product and store IDs are accepted only from exact IDs present in the
    message. The model may normalize a quantity written in words, but the
    caller must validate it and show a preview before applying any change.
    """
    if llm_client is None:
        return None
    try:
        raw = llm_client.complete_json(
            _PROMPT,
            json.dumps({"message": message}, ensure_ascii=False),
        )
        if isinstance(raw, str):
            raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.I)
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            return None
        plan = StockActionPlan.model_validate(raw)
    except Exception as exc:  # malformed/provider output degrades to rule fallback
        log.info("Semantic stock parsing unavailable: %s", exc)
        return None

    # IDs must come from the user's actual message, not the model's guess.
    mentioned = extract_entities(message)
    plan.product_id = mentioned.product_id
    plan.store_id = mentioned.store_id
    if plan.confidence < 0.75:
        return None
    return plan
