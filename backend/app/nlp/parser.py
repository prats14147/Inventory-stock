"""
backend/app/nlp/parser.py

Combines the rule-based layer (primary, always available) with an
optional LLM layer (secondary, used only when rules can't confidently
classify the message) -- the "hybrid intent/entity architecture" from
spec section 28.

Never executes arbitrary LLM output directly (spec section 31): the
LLM's JSON is parsed, and any intent/entity value outside the known enum
or expected shape is discarded rather than trusted.
"""

from __future__ import annotations

import json
import logging
import re

from app.nlp.entities import Entities
from app.nlp.intent import Intent
from app.nlp.prompts import INTENT_EXTRACTION_SYSTEM_PROMPT
from app.nlp.rules import extract_entities, rule_based_parse
from app.nlp.tool_registry import TOOLS_BY_NAME

log = logging.getLogger("nlp.parser")


def _safe_intent(value: str | None) -> Intent:
    if not isinstance(value, str):
        return Intent.UNKNOWN
    try:
        return Intent(value.upper())
    except ValueError:
        return Intent.UNKNOWN


def _llm_parse(message: str, llm_client, context: dict | None = None) -> tuple[Intent, Entities]:
    planner_input = json.dumps({"message": message, "conversation_context": context or {}}, ensure_ascii=False)
    raw = llm_client.complete_json(INTENT_EXTRACTION_SYSTEM_PROMPT, planner_input)
    if isinstance(raw, str):
        raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.IGNORECASE)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log.warning("LLM returned non-JSON output, discarding: %r", raw)
        return Intent.UNKNOWN, Entities()

    if not isinstance(parsed, dict):
        log.warning("LLM returned a JSON value that is not an object, discarding")
        return Intent.UNKNOWN, Entities()
    tool_name = parsed.get("tool")
    if tool_name is not None:
        if isinstance(tool_name, str):
            tool_name = tool_name.strip().lower()
        if tool_name == "unknown":
            return Intent.UNKNOWN, Entities()
        definition = TOOLS_BY_NAME.get(tool_name) if isinstance(tool_name, str) else None
        if definition is None:
            log.warning("LLM selected an unregistered tool, discarding: %r", tool_name)
            return Intent.UNKNOWN, Entities()
        intent = definition.intent
        raw_entities = parsed.get("arguments") or {}
    else:
        # Keep accepting the previous intent-shaped response during migration.
        intent = _safe_intent(parsed.get("intent"))
        raw_entities = parsed.get("entities") or {}
    if not isinstance(raw_entities, dict):
        log.warning("LLM returned entities with the wrong shape, discarding them")
        raw_entities = {}
    # Only accept known Entities fields -- never trust arbitrary LLM keys.
    try:
        entities = Entities(**{k: v for k, v in raw_entities.items() if k in Entities.model_fields})
    except (TypeError, ValueError) as exc:
        log.warning("LLM returned invalid entities, discarding them: %s", exc)
        entities = Entities()
    # The model may classify intent, but it must not invent an identifier.
    # Product and store IDs must appear explicitly in the user's message;
    # conversational references are resolved by the existing session context.
    mentioned = extract_entities(message)
    if entities.product_id != mentioned.product_id:
        entities.product_id = mentioned.product_id
    entities.product_reference = mentioned.product_reference
    if entities.store_id != mentioned.store_id:
        entities.store_id = mentioned.store_id
    if entities.category != mentioned.category:
        entities.category = mentioned.category
    entities.date_range = mentioned.date_range
    entities.granularity = mentioned.granularity
    entities.group_by = mentioned.group_by
    entities.sort_order = mentioned.sort_order
    return intent, entities


def parse(message: str, llm_client=None, context: dict | None = None) -> tuple[Intent, Entities, str]:
    """
    Returns (intent, entities, method) where method is "rules" or "llm",
    for observability/testing.
    """
    intent, entities = rule_based_parse(message)
    if intent != Intent.UNKNOWN:
        return intent, entities, "rules"

    if llm_client is None:
        return Intent.UNKNOWN, entities, "rules"

    try:
        llm_intent, llm_entities = _llm_parse(message, llm_client, context)
    except Exception as e:  # noqa: BLE001 - malformed provider output must not break chat
        log.warning("LLM intent parsing failed, falling back to rules: %s", e)
        return Intent.UNKNOWN, entities, "rules"

    # Merge: prefer rule-extracted entities (regex is exact), fill gaps from LLM.
    merged = entities.model_copy()
    for field in Entities.model_fields:
        if getattr(merged, field) is None:
            setattr(merged, field, getattr(llm_entities, field))

    return llm_intent, merged, "llm"
