"""
backend/app/nlp/catalog_resolve.py

Human-friendly product resolution: turn a name, SKU fragment, or plain
words from a chat message into a catalog product ID.

Why this exists: the catalog identifies products by P-code, but people say
"wireless headphones", "blender", or "WM-020". Previously the chatbot gave up
at that point and asked for the P-code. Now it resolves the reference against
the live product catalog first and only asks when the reference is genuinely
ambiguous or unknown.

Matching tiers (first unique hit wins):
  1. Full catalog name appearing in the message (longest match first), so
     "how much stock for wireless headphones" matches "Wireless Headphones"
     even though the rule layer only captured "wireless" as the reference.
  2. Exact SKU (case-insensitive).
  3. Exact product name (case-insensitive).
  4. Token-subset: every significant token of the reference occurs in the
     product name ("headphones" -> "Wireless Headphones").
  5. Fuzzy name match (difflib) for typos ("headpones" -> "Wireless Headphones").

Returns (product_id | None, candidates). A unique hit gives product_id;
several hits give candidates for a "did you mean ...?" clarification;
no hits give (None, []) and the caller keeps the old ask-for-P-code reply.
Nothing here invents identifiers: every returned ID comes from the database.
"""

from __future__ import annotations

import difflib
import re

from sqlalchemy.orm import Session

from app.repositories import product_repository

# Generic words that must not count as product evidence on their own.
_STOP_TOKENS = {
    "product", "item", "items", "stock", "inventory", "store", "sales",
    "sale", "units", "unit", "the", "a", "an", "for", "of", "and",
    "low", "high", "risk", "reorder", "forecast", "much", "many",
}


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _STOP_TOKENS
    ]


def find_product_ids_in_message(db: Session, message: str) -> list[str]:
    """Every distinct catalog product referenced in a message, in order.

    P-codes first (exact), then full catalog names longest-first so
    "kitchen blender vs headphones" yields ["P0007", "P0001"]. Used by the
    multi-product compare flow; single-product questions keep using
    resolve_product. Every ID comes from the database, never invented.
    """
    found: list[str] = []
    for match in re.finditer(r"\bP0*([0-9]{1,4})\b", message, re.IGNORECASE):
        product_id = f"P{int(match.group(1)):04d}"
        if product_repository.product_exists(db, product_id) and product_id not in found:
            found.append(product_id)
    lowered_message = message.lower()
    message_tokens = set(_tokens(message))
    for product in sorted(
        product_repository.list_products(db),
        key=lambda item: len(item.name or ""),
        reverse=True,
    ):
        if not product.name or product.product_id in found:
            continue
        if product.name.lower() in lowered_message:
            found.append(product.product_id)
            continue
        # Single distinctive name words also count ("headphones" alone
        # means Wireless Headphones). Short tokens ("t", "led") are
        # skipped: they collide with ordinary words.
        name_tokens = _tokens(product.name)
        if any(len(token) >= 4 and token in message_tokens for token in name_tokens):
            found.append(product.product_id)
    return found


def resolve_product(
    db: Session,
    message: str,
    reference: str | None,
) -> tuple[str | None, list]:
    """Resolve a human product reference to a catalog product.

    Returns (product_id, candidates): product_id is set only for a unique
    match; candidates holds every tied product for clarification.
    """
    products = product_repository.list_products(db)
    if not products:
        return None, []

    lowered_message = message.lower()

    # Tier 1: full catalog name inside the message, longest first.
    name_hits = [
        product
        for product in products
        if product.name and product.name.lower() in lowered_message
    ]
    if len(name_hits) == 1:
        return name_hits[0].product_id, []
    if len(name_hits) > 1:
        longest = max(len(product.name) for product in name_hits)
        longest_hits = [p for p in name_hits if len(p.name) == longest]
        if len(longest_hits) == 1:
            return longest_hits[0].product_id, []
        return None, sorted(longest_hits, key=lambda p: p.product_id)

    candidates: list = []
    if reference:
        ref = reference.strip()
        ref_lower = ref.lower()

        # Tier 2: exact SKU.
        sku_hits = [
            product
            for product in products
            if product.sku and product.sku.lower() == ref_lower
        ]
        if len(sku_hits) == 1:
            return sku_hits[0].product_id, []
        candidates = list(sku_hits)

        # Tier 3: exact name.
        if not candidates:
            name_exact = [
                product
                for product in products
                if product.name and product.name.lower() == ref_lower
            ]
            if len(name_exact) == 1:
                return name_exact[0].product_id, []
            candidates = list(name_exact)

        # Tier 4: every significant reference token inside the product name.
        if not candidates:
            ref_tokens = _tokens(ref)
            if ref_tokens:
                token_hits = [
                    product
                    for product in products
                    if product.name
                    and all(token in product.name.lower() for token in ref_tokens)
                ]
                if len(token_hits) == 1:
                    return token_hits[0].product_id, []
                candidates = list(token_hits)

        # Tier 5: fuzzy match for typos, against full names and their
        # individual words ("headpones" matches the "headphones" token even
        # though it is far from the full "Wireless Headphones" string).
        if not candidates and ref:
            spell_texts: dict[str, list] = {}
            for product in products:
                if not product.name:
                    continue
                spell_texts.setdefault(product.name, []).append(product)
                for token in _tokens(product.name):
                    spell_texts.setdefault(token, []).append(product)
            # Cutoff 0.8 is deliberately strict: a looser threshold maps
            # unrelated words onto catalog tokens ("apple" -> "table" at 0.6)
            # and the bot would then answer for the wrong product -- worse
            # than asking for clarification.
            close = difflib.get_close_matches(ref_lower, list(spell_texts), n=5, cutoff=0.8)
            fuzzy_hits: list = []
            for text in close:
                for product in spell_texts[text]:
                    if product not in fuzzy_hits:
                        fuzzy_hits.append(product)
            if len(fuzzy_hits) == 1:
                return fuzzy_hits[0].product_id, []
            candidates = list(fuzzy_hits)

    candidates = sorted(candidates, key=lambda p: p.product_id)
    return None, candidates
