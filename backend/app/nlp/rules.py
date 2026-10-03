"""
backend/app/nlp/rules.py

Rule-based (keyword/regex) intent and entity extraction. This is the
PRIMARY NLU layer: deterministic, free, and always available (no network
call). The LLM (Groq) is used as a secondary layer for messages this
layer can't confidently classify -- see chat_service.py for how the two
combine ("hybrid" architecture per spec section 28).
"""

from __future__ import annotations

import re

from app.nlp.entities import Entities
from app.nlp.intent import Intent

KNOWN_CATEGORIES = ["Furniture", "Toys", "Clothing", "Groceries", "Electronics"]

_PRODUCT_RE = re.compile(r"\bP0*([0-9]{1,4})\b", re.IGNORECASE)
_STORE_RE = re.compile(r"\bS0*([0-9]{1,3})\b", re.IGNORECASE)
_HORIZON_RE = re.compile(r"\b(\d{1,3})\s*-?\s*day", re.IGNORECASE)

# Ordered: first matching rule wins. Order matters (more specific first).
_INTENT_RULES: list[tuple[Intent, list[str]]] = [
    (Intent.REORDER_RECOMMENDATION, ["reorder", "re-order", "should i order", "how much should i order"]),
    (Intent.STOCKOUT_RISK, ["stockout", "stock out", "run out", "risk of running out", "at risk"]),
    (Intent.DEMAND_FORECAST, ["forecast", "predict", "projected demand", "expected demand"]),
    (Intent.LOW_STOCK, ["low stock", "low on stock", "running low", "which products are low"]),
    (Intent.TOP_SELLING, ["top selling", "top-selling", "best selling", "best-selling", "top products"]),
    (Intent.BOTTOM_SELLING, ["bottom selling", "worst selling", "least selling", "slowest selling"]),
    (Intent.CATEGORY_ANALYSIS, ["by category", "category breakdown", "which category", "category analysis"]),
    (Intent.STORE_ANALYSIS, ["by store", "store breakdown", "which store", "store analysis"]),
    (Intent.SALES_TREND, ["trend", "over time", "sales history", "sales pattern"]),
    (Intent.HELP, ["help", "what can you do", "what can you help"]),
    (Intent.CURRENT_STOCK, [
        "how much stock",
        "current stock",
        "inventory level",
        "how much inventory",
        "stock do we have",
        "stock does",
        "stock for",
        "stock of",
        "stock level for",
    ]),
    (Intent.PRODUCT_INFO, ["tell me about", "information on", "info on", "details on"]),
]


# Phrases that make a message a *follow-up* to the previous turn rather than
# a standalone request: pronouns, ordinals and explicit callbacks. The rules
# layer above cannot classify these on their own (there is no keyword in them),
# so chat_service.ChatSessionManager reuses the previous product-scoped intent
# for such messages instead of dropping them as UNKNOWN.
_FOLLOW_UP_PATTERNS = [
    r"\b(?:it|its|that|those|these|them|they|same|there)\b",
    r"\b(?:what|how)\s+about\b",
    r"\b(?:the\s+)?(?:first|second|third|fourth|fifth|last|other|next|previous)(?:\s+one)?\b",
]


def looks_like_follow_up(message: str) -> bool:
    """True when `message` only makes sense with the conversation context.

    Deliberately conservative: word boundaries keep "profit"/"units" from
    being read as the pronoun "it". A False positive is harmless on its own
    -- intent carryover is only attempted when the rules layer already gave
    up (UNKNOWN) and a previous product-scoped intent exists.
    """
    return any(re.search(pattern, message, re.IGNORECASE) for pattern in _FOLLOW_UP_PATTERNS)


def extract_entities(message: str) -> Entities:
    entities = Entities()

    product_match = _PRODUCT_RE.search(message)
    if product_match:
        entities.product_id = f"P{int(product_match.group(1)):04d}"

    store_match = _STORE_RE.search(message)
    if store_match:
        entities.store_id = f"S{int(store_match.group(1)):03d}"

    for cat in KNOWN_CATEGORIES:
        if cat.lower() in message.lower():
            entities.category = cat
            break

    horizon_match = _HORIZON_RE.search(message)
    if horizon_match:
        entities.forecast_horizon = int(horizon_match.group(1))

    return entities


def classify_intent(message: str) -> Intent:
    lower = message.lower()
    for intent, keywords in _INTENT_RULES:
        if any(kw in lower for kw in keywords):
            return intent
    return Intent.UNKNOWN


def rule_based_parse(message: str) -> tuple[Intent, Entities]:
    return classify_intent(message), extract_entities(message)
