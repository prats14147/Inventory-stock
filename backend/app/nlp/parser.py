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

from app.nlp.entities import Entities
from app.nlp.intent import Intent
from app.nlp.llm_client import LLMUnavailableError
from app.nlp.prompts import INTENT_EXTRACTION_SYSTEM_PROMPT
from app.nlp.rules import rule_based_parse

log = logging.getLogger("nlp.parser")


def _safe_intent(value: str | None) -> Intent:
    if value is None:
        return Intent.UNKNOWN
    try:
        return Intent(value.upper())
    except ValueError:
        return Intent.UNKNOWN


def _llm_parse(message: str, llm_client) -> tuple[Intent, Entities]:
    raw = llm_client.complete_json(INTENT_EXTRACTION_SYSTEM_PROMPT, message)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log.warning("LLM returned non-JSON output, discarding: %r", raw)
        return Intent.UNKNOWN, Entities()

    intent = _safe_intent(parsed.get("intent"))
    raw_entities = parsed.get("entities") or {}
    # Only accept known Entities fields -- never trust arbitrary LLM keys.
    entities = Entities(**{k: v for k, v in raw_entities.items() if k in Entities.model_fields})
    return intent, entities


def parse(message: str, llm_client=None) -> tuple[Intent, Entities, str]:
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
        llm_intent, llm_entities = _llm_parse(message, llm_client)
    except LLMUnavailableError as e:
        log.warning("LLM unavailable, falling back to rule-based UNKNOWN: %s", e)
        return Intent.UNKNOWN, entities, "rules"

    # Merge: prefer rule-extracted entities (regex is exact), fill gaps from LLM.
    merged = entities.model_copy()
    for field in Entities.model_fields:
        if getattr(merged, field) is None:
            setattr(merged, field, getattr(llm_entities, field))

    return llm_intent, merged, "llm"
