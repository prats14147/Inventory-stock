"""Fallback parser using the same structured plan contract as Gemini.

Rule-based classification is the offline fallback. If rules cannot identify a
request, an optional LLM may return the shared ``RequestPlan`` JSON schema;
unregistered tools and low-confidence plans are never accepted as executable
intent.
"""

from __future__ import annotations

import logging

from app.nlp.entities import Entities
from app.nlp.intent import Intent
from app.nlp.request_planner import MIN_CONFIDENCE_TO_ROUTE, plan_intent, plan_request
from app.nlp.rules import rule_based_parse

log = logging.getLogger("nlp.parser")


def parse(message: str, llm_client=None, context: dict | None = None) -> tuple[Intent, Entities, str]:
    """Return ``(intent, entities, method)`` using shared Gemini/fallback semantics."""
    intent, entities = rule_based_parse(message)
    if intent != Intent.UNKNOWN:
        return intent, entities, "rules"
    if llm_client is None:
        return Intent.UNKNOWN, entities, "rules"

    plan = plan_request(message, llm_client, context)
    if plan is None or plan.confidence < MIN_CONFIDENCE_TO_ROUTE:
        return Intent.UNKNOWN, entities, "rules"

    intent = plan_intent(plan)
    if intent == Intent.UNKNOWN:
        return intent, entities, "llm"
    if plan.request_type == "read":
        try:
            entities = Entities(**plan.arguments)
        except (TypeError, ValueError) as exc:
            log.warning("Validated planner arguments could not map to entities: %s", exc)
            return Intent.UNKNOWN, Entities(), "rules"
    else:
        mentioned = entities
        # Action identifiers must come from the user's words, never Gemini.
        entities.product_id = mentioned.product_id
        entities.store_id = mentioned.store_id
        entities.product_reference = mentioned.product_reference
    return intent, entities, "llm"
