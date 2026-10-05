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
import calendar
from datetime import date, timedelta

from app.nlp.entities import Entities
from app.nlp.intent import Intent

KNOWN_CATEGORIES = ["Furniture", "Toys", "Clothing", "Groceries", "Electronics"]

_DOMAIN_TYPO_MAP = {
    "forcast": "forecast",
    "forcasting": "forecasting",
    "forecaste": "forecast",
    "inventry": "inventory",
    "invetory": "inventory",
    "stcok": "stock",
    "stok": "stock",
    "reordr": "reorder",
    "restok": "restock",
    "dedcut": "deduct",
}


def _normalize_domain_terms(message: str) -> str:
    """Correct a small, explicit set of common inventory-domain typos."""
    return re.sub(
        r"\b[\w']+\b",
        lambda match: _DOMAIN_TYPO_MAP.get(match.group(0).lower(), match.group(0)),
        message,
        flags=re.IGNORECASE,
    )

_PRODUCT_RE = re.compile(r"\bP0*([0-9]{1,4})\b", re.IGNORECASE)
_STORE_RE = re.compile(r"\bS[0-9]+\b", re.IGNORECASE)
_HORIZON_RE = re.compile(r"\b(\d{1,3})\s*-?\s*day", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_MONTH_NAMES = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
_MONTH_NAMES.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
_MONTH_PATTERN = "|".join(sorted(_MONTH_NAMES, key=len, reverse=True))
_NON_PRODUCT_REFERENCES = {
    "profit", "loss", "margin", "revenue", "sales", "stock", "inventory", "the",
    "this", "last", "next", "each", "most", "least", "selling", "made", "sold",
    "store", "stores", "category", "today", "yesterday",
}
_STOCK_WRITE_RE = re.compile(
    r"(?:\b(?:i|we)\s+(?:just\s+)?sold\b|\b(?:record|log)\s+(?:a\s+)?sale\b|"
    r"\b(?:deduct|subtract|remove|adjust|reduce|decrease)\b.{0,100}\b(?:stock|inventory|units?|items?|quantity)\b|"
    r"\b(?:restock|receiv\w*|reciev\w*|deliver\w*|add)\b.{0,100}\b(?:stock|inventory|units?|items?|quantity)\b)",
    re.IGNORECASE,
)

# Ordered: first matching rule wins. Order matters (more specific first).
_INTENT_RULES: list[tuple[Intent, list[str]]] = [
    (Intent.FINANCIAL_ANALYSIS, ["gross profit", "gross loss", "gross margin", "cogs", "cost of goods", "profit margin", "profitability", "most profitable product", "least profitable product", "product profit", "profit by product", "profit by category", "margin by store"]),
    (Intent.STORE_PROFITABILITY, ["profit by store", "profit per store", "store profit", "store profitability", "store is profitable", "store is losing", "loss by store", "store performance", "store condition", "most profitable store", "least profitable store", "which store makes the most", "which store is losing"]),
    (Intent.REVENUE_ANALYSIS, ["revenue", "sales revenue", "sales value", "sales amount", "money from sales", "money made from sales", "net sales", "how much did we earn", "how much money did i make", "how much money did we make", "how much did i make", "how much did we make", "earned from selling", "made from selling"]),
    (Intent.REORDER_RECOMMENDATION, ["reorder", "re-order", "should i order", "should we order", "how much should i order", "how many should i buy", "should we buy more", "restock quantity", "how much to restock", "what should i replenish"]),
    (Intent.STOCKOUT_RISK, ["stockout", "stock out", "run out", "running out", "sell out", "out of stock soon", "risk of running out", "at risk", "run short", "run low", "last long enough", "last until", "enough stock to last"]),
    (Intent.DEMAND_FORECAST, ["forecast", "predict", "prediction", "projected demand", "expected demand", "how much will we sell", "how many will we sell", "future demand", "sales prediction", "demand estimate", "likely to sell", "sales expected"]),
    (Intent.LOW_STOCK, ["low stock", "low on stock", "running low", "which products are low", "need restocking", "below the stock threshold", "need replenishment", "need to restock", "needs restocking", "running out of stock", "items to replenish"]),
    (Intent.TOP_SELLING, ["top selling", "top-selling", "best selling", "best-selling", "top products", "sell the most", "highest selling", "most popular", "fastest selling", "most sales", "highest sales", "best performer", "top performer"]),
    (Intent.BOTTOM_SELLING, ["bottom selling", "worst selling", "least selling", "slowest selling", "sell the least", "lowest selling", "slow movers", "slow moving", "slow-moving", "least popular"]),
    (Intent.CATEGORY_ANALYSIS, ["by category", "category breakdown", "which category", "category analysis", "compare categories", "categories sell", "category sells"]),
    (Intent.STORE_ANALYSIS, ["by store", "store breakdown", "which store", "store analysis", "compare stores", "stores sell", "store sells"]),
    (Intent.SALES_TREND, ["trend", "over time", "sales history", "sales pattern", "units sold", "how many did we sell", "what did we sell", "which products sold", "products sold", "items sold", "what sold", "sales for", "sales of", "sales from", "sales between", "sales during", "sales last", "sales this", "sold last", "sold this"]),
    (Intent.HELP, ["help", "what can you do", "what can you help"]),
    (Intent.CURRENT_STOCK, [
        "how many items are left",
        "how many products are left",
        "current inventory",
        "my inventory",
        "do i have enough stock",
        "do we have enough stock",
        "how much stock",
        "available stock",
        "stock left for",
        "how many left",
        "remaining quantity for",
        "availability of",
        "current stock",
        "inventory level",
        "how much inventory",
        "stock do we have",
        "stock does",
        "stock for",
        "stock of",
        "stock level for",
        "stock levels",
        "stock remaining",
        "quantity on hand",
        "inventory balance",
        "units available",
        "how many do we still have",
        "what is left for",
        "what's left for",
        "what is the stock",
        "what's the stock",
        "available units for",
        "on hand",
        "available units",
        "remaining stock",
        "inventory of",
        "inventory for",
        "how many units are left",
        "how many units",
        "how many are left",
        "what do we have in stock",
        "how much do we have left",
    ]),
    (Intent.PRODUCT_INFO, ["tell me about", "information on", "info on", "details on", "overview of", "give me details about"]),
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


def is_stock_write_request(message: str) -> bool:
    """Detect requests that try to change stock or record a sale in chat."""
    return bool(_STOCK_WRITE_RE.search(message))


def extract_entities(message: str) -> Entities:
    entities = Entities()
    normalized = _normalize_domain_terms(message)

    product_match = _PRODUCT_RE.search(message)
    if product_match:
        entities.product_id = f"P{int(product_match.group(1)):04d}"
    else:
        explicit_id = re.search(r"\b(?:product\s+id|sku)\s*[:#-]?\s*([A-Za-z0-9][\w-]*)", message, re.I)
        if explicit_id:
            entities.product_id = explicit_id.group(1)
        named_product = None if explicit_id else re.search(r"\b(?:product|item|sku)\s+(?!id\b)([A-Za-z][\w-]*)", message, re.I)
        if not named_product:
            if not explicit_id:
                named_product = re.search(r"\b(?:from|for)\s+(?!the\b|this\b|last\b|next\b)([A-Za-z][\w-]*)", message, re.I)
        if named_product and named_product.group(1).lower() not in _NON_PRODUCT_REFERENCES | set(_MONTH_NAMES) | {item.lower() for item in KNOWN_CATEGORIES}:
            entities.product_reference = named_product.group(1)

    store_match = _STORE_RE.search(message)
    if store_match:
        raw_store_id = store_match.group(0).upper()
        digits = raw_store_id[1:]
        # Normalize short numeric IDs even when users pad them (S0002 -> S002),
        # while preserving longer source IDs such as S00021.
        entities.store_id = f"S{int(digits):03d}" if len(digits) <= 4 else raw_store_id

    for cat in KNOWN_CATEGORIES:
        if cat.lower() in normalized.lower():
            entities.category = cat
            break

    horizon_match = _HORIZON_RE.search(normalized)
    if horizon_match:
        entities.forecast_horizon = int(horizon_match.group(1))
    elif re.search(r"\b(?:next|coming|for)\s+week\b|\bweek\s+ahead\b", normalized, re.IGNORECASE):
        entities.forecast_horizon = 7
    elif re.search(r"\b(?:next|coming|for|over the next)\s+(?:two|2)\s+weeks?\b|\bfortnight\b", normalized, re.IGNORECASE):
        entities.forecast_horizon = 14
    else:
        week_count = re.search(r"\b(?:next|coming|for)\s+(\d{1,2})\s+weeks?\b", normalized, re.IGNORECASE)
        if week_count:
            entities.forecast_horizon = int(week_count.group(1)) * 7

    lower = normalized.lower()
    for granularity, patterns in {
        "daily": ["daily", "per day", "each day"],
        "weekly": ["weekly", "per week", "each week", "by week"],
        "monthly": ["monthly", "per month", "each month", "by month"],
    }.items():
        if any(pattern in lower for pattern in patterns):
            entities.granularity = granularity
            break

    if re.search(r"\b(?:by|per|each|every|which|compare|top|most|least)(?:\s+(?:the|each|every))?\s+(?:products?|items?|skus?)\b|\b(?:products?|items?)\s+(?:by|with|made|generated|earning|most|least)\b", lower):
        entities.group_by = "product"
    elif re.search(r"\b(?:by|per|each|every|which|compare|top|most|least)(?:\s+(?:the|each|every))?\s+categories?\b|\bcategory\s+(?:breakdown|wise|by)\b", lower):
        entities.group_by = "category"
    elif re.search(r"\b(?:by|per|each|every|which|compare|top|most|least)(?:\s+(?:the|each|every))?\s+(?:stores?|locations?)\b|\bstore\s+(?:breakdown|wise|by)\b", lower):
        entities.group_by = "store"
    if re.search(r"\b(?:least|lowest|smallest|worst|bottom)\b", lower):
        entities.sort_order = "ascending"
    elif re.search(r"\b(?:most|highest|largest|best|top)\b", lower):
        entities.sort_order = "descending"

    entities.date_range = _extract_date_range(normalized)

    return entities


def _extract_date_range(message: str) -> dict | None:
    """Extract common explicit and relative ranges for sales queries."""
    today = date.today()
    lower = message.lower()
    dates = _ISO_DATE_RE.findall(message)
    if len(dates) >= 2:
        return {"start_date": dates[0], "end_date": dates[1]}
    if len(dates) == 1:
        if re.search(r"\b(after|since|from)\b", lower):
            return {"start_date": dates[0], "end_date": today.isoformat()}
        if re.search(r"\b(before|until|through)\b", lower):
            return {"start_date": None, "end_date": dates[0]}
        return {"start_date": dates[0], "end_date": dates[0]}

    if "last week" in lower:
        end = today - timedelta(days=today.weekday() + 1)
        return {"start_date": (end - timedelta(days=6)).isoformat(), "end_date": end.isoformat()}
    if "this week" in lower:
        return {"start_date": (today - timedelta(days=today.weekday())).isoformat(), "end_date": today.isoformat()}
    if "last month" in lower:
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        return {"start_date": start.isoformat(), "end_date": end.isoformat()}
    if "this month" in lower:
        return {"start_date": today.replace(day=1).isoformat(), "end_date": today.isoformat()}
    if "yesterday" in lower:
        day = today - timedelta(days=1)
        return {"start_date": day.isoformat(), "end_date": day.isoformat()}
    if re.search(r"\btoday\b", lower):
        return {"start_date": today.isoformat(), "end_date": today.isoformat()}
    if "last year" in lower:
        return {"start_date": today.replace(year=today.year - 1, month=1, day=1).isoformat(),
                "end_date": today.replace(year=today.year - 1, month=12, day=31).isoformat()}
    if "year to date" in lower or "this year" in lower:
        return {"start_date": today.replace(month=1, day=1).isoformat(), "end_date": today.isoformat()}

    date_phrase = rf"\b(?P<month>{_MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>20\d{{2}}))?\b"
    between = re.search(
        rf"\bbetween\s+((?:{_MONTH_PATTERN})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+20\d{{2}})?)"
        rf"\s+(?:and|to)\s+((?:{_MONTH_PATTERN})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+20\d{{2}})?)",
        lower, re.I,
    )
    if between:
        first = re.search(date_phrase, between.group(1), re.I)
        second = re.search(date_phrase, between.group(2), re.I)
        if first and second:
            year1 = int(first.group("year") or today.year)
            year2 = int(second.group("year") or year1)
            try:
                start = date(year1, _MONTH_NAMES[first.group("month").lower().rstrip(".")], int(first.group("day")))
                end = date(year2, _MONTH_NAMES[second.group("month").lower().rstrip(".")], int(second.group("day")))
                return {"start_date": start.isoformat(), "end_date": end.isoformat()}
            except ValueError:
                return None

    month_match = re.search(
        rf"\b(?:in|during|for|since|from)\s+(?P<month>{_MONTH_PATTERN})\.?\b(?:\s+(?P<year>20\d{{2}}))?"
        rf"|^(?P<month_only>{_MONTH_PATTERN})\.?\s*(?P<year_only>20\d{{2}})?$",
        lower, re.I,
    )
    if month_match:
        month_token = month_match.group("month") or month_match.group("month_only")
        year_token = month_match.group("year") or month_match.group("year_only")
        month = _MONTH_NAMES[month_token.lower().rstrip(".")]
        year = int(year_token or (today.year if month <= today.month else today.year - 1))
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        return {"start_date": first.isoformat(), "end_date": last.isoformat()}

    days_match = re.search(r"\b(?:last|past|previous)\s+(\d{1,3})\s+days?\b", lower)
    if days_match:
        count = int(days_match.group(1))
        return {"start_date": (today - timedelta(days=max(0, count - 1))).isoformat(), "end_date": today.isoformat()}
    return None


def classify_intent(message: str) -> Intent:
    message = _normalize_domain_terms(message)
    lower = message.lower()
    if re.search(r"\b(?:stock|inventory)\s+(?:history|movements?|changes|adjustments?)\b", lower):
        return Intent.STOCK_HISTORY
    if re.search(r"\b(?:show|list|when|what|how many)\b.{0,50}\b(?:receive(?:d)?|deliver(?:ed)?|damaged|broken|expired|wasted|adjusted|removed)\b", lower):
        return Intent.STOCK_HISTORY
    # Revenue/profit needs a distinct financial calculation and must not be
    # answered with a nearby units-sold summary.
    if "dollar sales" in lower:
        return Intent.UNKNOWN
    if re.search(r"\b(?:gross\s+)?(?:profit|loss|margin|cogs|cost of goods)\b", lower):
        if re.search(r"\b(store|stores|location|locations)\b", lower) or _STORE_RE.search(message):
            return Intent.STORE_PROFITABILITY
        return Intent.FINANCIAL_ANALYSIS
    if re.search(r"\b(?:do i|do we) have enough stock\b", lower):
        return Intent.STOCKOUT_RISK
    if re.search(r"\b(?:low|low on|low in)\s+(?:stock|inventory)\b", lower) and re.search(
        r"\b(?:selling fast|selling quickly|fast[- ]selling|quick[- ]selling|high velocity|moving quickly)\b", lower
    ):
        return Intent.LOW_STOCK_FAST_SELLING
    has_store_scope = re.search(r"\b(store|location)\b", lower) or _STORE_RE.search(message)
    if has_store_scope and re.search(
        r"\b(profit|profitable|loss|losing|margin|condition|health|performance|doing|money)\b", lower
    ):
        return Intent.STORE_PROFITABILITY
    if re.search(r"\b(units?|items?)\b", lower) and re.search(r"\b(sell|sold|sales)\b", lower):
        return Intent.SALES_TREND
    if re.search(r"\b(low|running low|almost out)\b", lower) and re.search(r"\b(stock|inventory|shelf|shelves)\b", lower):
        return Intent.LOW_STOCK
    for intent, keywords in _INTENT_RULES:
        if any(kw in lower for kw in keywords):
            return intent
    # Keep future-facing stock questions out of the generic current-balance
    # fallback. When wording is genuinely ambiguous, send it to the LLM layer.
    product_and_stock = _PRODUCT_RE.search(message) and re.search(
        r"\b(stock|inventory|on hand|available|left)\b", lower
    )
    future_time = re.search(r"\b(tomorrow|next|coming|week|fortnight|days?|later|future)\b", lower)
    if product_and_stock and future_time:
        if re.search(r"\b(run out|running out|last|enough|cover|deplet|short|risk)\b", lower):
            return Intent.STOCKOUT_RISK
        if re.search(r"\b(sell|sales|demand|move|shift|consume|forecast|predict|expect)\b", lower):
            return Intent.DEMAND_FORECAST
        return Intent.UNKNOWN
    # A generic product + stock mention means a current-balance query, but
    # only after specific forecast, stockout, and low-stock signals had their
    # chance to match (e.g. "will P0001 run out of stock?").
    if product_and_stock:
        return Intent.CURRENT_STOCK
    return Intent.UNKNOWN


def rule_based_parse(message: str) -> tuple[Intent, Entities]:
    return classify_intent(message), extract_entities(message)
