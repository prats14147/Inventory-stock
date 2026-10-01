"""
backend/tests/test_chat_service.py

Tests the full hybrid NLP pipeline. Rule-based tests need no network.
The LLM-fallback tests use a FakeLLMClient (canned responses) so they
verify the *pipeline logic* (JSON parsing, entity merging, graceful
degradation) without requiring real network access to api.groq.com --
which this sandbox's allowlist doesn't include. A real GroqClient should
be smoke-tested separately once a real GROQ_API_KEY is available.
"""

import json

import pytest

from app.nlp import parser
from app.nlp.intent import Intent
from app.nlp.llm_client import LLMUnavailableError
from app.nlp.rules import classify_intent, extract_entities
from app.services.chat_service import handle_chat_message


# --- Rule-based layer (no network, always available) -----------------------

@pytest.mark.parametrize(
    "message,expected_intent",
    [
        ("How much stock do we have for P0001?", Intent.CURRENT_STOCK),
        ("Which products are low on stock?", Intent.LOW_STOCK),
        ("What are our top-selling products?", Intent.TOP_SELLING),
        ("What are the bottom selling products?", Intent.BOTTOM_SELLING),
        ("Forecast P0001.", Intent.DEMAND_FORECAST),
        ("Will P0005 run out of stock?", Intent.STOCKOUT_RISK),
        ("How much should we reorder for P0002?", Intent.REORDER_RECOMMENDATION),
        ("Show me the sales trend for P0001", Intent.SALES_TREND),
        ("Break down sales by category", Intent.CATEGORY_ANALYSIS),
        ("Break down sales by store", Intent.STORE_ANALYSIS),
        ("What can you help with?", Intent.HELP),
        ("asdkjaslkdj random gibberish", Intent.UNKNOWN),
    ],
)
def test_rule_based_intent_classification(message, expected_intent):
    assert classify_intent(message) == expected_intent


def test_rule_based_entity_extraction_product_and_horizon():
    entities = extract_entities("forecast for the next 7 days for P0005")
    assert entities.product_id == "P0005"
    assert entities.forecast_horizon == 7


def test_rule_based_entity_extraction_category():
    entities = extract_entities("how are Electronics doing?")
    assert entities.category == "Electronics"


def test_rule_based_entity_extraction_no_entities():
    entities = extract_entities("what are the top selling products")
    assert entities.product_id is None
    assert entities.category is None


# --- Fake LLM client for testing the fallback path without network ---------

class FakeLLMClient:
    """Returns canned responses -- proves the hybrid pipeline logic works
    without needing real network access to api.groq.com."""

    def __init__(self, json_response: dict | None = None, text_response: str | None = None, raise_error: bool = False):
        self.json_response = json_response
        self.text_response = text_response
        self.raise_error = raise_error
        self.calls = []

    def complete_json(self, system_prompt, user_message):
        self.calls.append(("json", user_message))
        if self.raise_error:
            raise LLMUnavailableError("simulated network failure")
        return json.dumps(self.json_response)

    def complete_text(self, system_prompt, user_message):
        self.calls.append(("text", user_message))
        if self.raise_error:
            raise LLMUnavailableError("simulated network failure")
        return self.text_response


def test_llm_fallback_used_only_when_rules_return_unknown():
    fake = FakeLLMClient(json_response={"intent": "TOP_SELLING", "entities": {}})
    # Rules already classify this confidently -- LLM should NOT be called.
    intent, entities, method = parser.parse("What are our top-selling products?", llm_client=fake)
    assert method == "rules"
    assert fake.calls == []


def test_llm_fallback_invoked_for_ambiguous_message():
    fake = FakeLLMClient(json_response={"intent": "CURRENT_STOCK", "entities": {"product_id": "P0003"}})
    intent, entities, method = parser.parse("what's up with that thing we sell", llm_client=fake)
    assert method == "llm"
    assert intent == Intent.CURRENT_STOCK
    assert entities.product_id == "P0003"
    assert len(fake.calls) == 1


def test_llm_invalid_intent_value_discarded_as_unknown():
    fake = FakeLLMClient(json_response={"intent": "NOT_A_REAL_INTENT", "entities": {}})
    intent, entities, method = parser.parse("some ambiguous message here", llm_client=fake)
    assert intent == Intent.UNKNOWN


def test_llm_unavailable_falls_back_gracefully():
    fake = FakeLLMClient(raise_error=True)
    intent, entities, method = parser.parse("some ambiguous message here", llm_client=fake)
    assert intent == Intent.UNKNOWN
    assert method == "rules"


def test_llm_arbitrary_extra_keys_are_ignored():
    fake = FakeLLMClient(
        json_response={
            "intent": "CURRENT_STOCK",
            "entities": {"product_id": "P0001", "malicious_field": "DROP TABLE products;"},
        }
    )
    intent, entities, method = parser.parse("ambiguous phrasing here", llm_client=fake)
    assert entities.product_id == "P0001"
    assert not hasattr(entities, "malicious_field")


# --- Full chat pipeline (rule-based / template mode, live DB) --------------

def test_chat_current_stock(db):
    r = handle_chat_message(db, "How much stock do we have for P0001?")
    assert r.intent == Intent.CURRENT_STOCK
    assert r.data["product_id"] == "P0001"
    assert "P0001" in r.message


def test_chat_unknown_product_never_fabricates(db):
    r = handle_chat_message(db, "How much stock does P9999 have?")
    assert r.data is None
    assert "couldn't find" in r.message.lower()


def test_chat_missing_entity_asks_clarification(db):
    r = handle_chat_message(db, "forecast please")  # DEMAND_FORECAST intent, no product_id
    assert r.data is None
    assert "?" in r.message


def test_chat_unknown_intent_offers_help(db):
    r = handle_chat_message(db, "asdkjaslkdj random gibberish")
    assert r.intent == Intent.UNKNOWN
    assert r.data is None


def test_chat_response_uses_llm_phrasing_when_available(db):
    fake = FakeLLMClient(text_response="P0001 is well stocked with plenty on hand.")
    r = handle_chat_message(db, "How much stock do we have for P0001?", llm_client=fake)
    assert r.message == "P0001 is well stocked with plenty on hand."
    assert r.data["product_id"] == "P0001"  # underlying verified data still attached


def test_chat_falls_back_to_template_when_llm_fails(db):
    fake = FakeLLMClient(raise_error=True)
    r = handle_chat_message(db, "How much stock do we have for P0001?", llm_client=fake)
    assert "P0001" in r.message
    assert r.data["product_id"] == "P0001"


def test_chat_demand_forecast_column_never_appears_in_response(db):
    """The chatbot must never surface the leaky source `Demand Forecast` column."""
    r = handle_chat_message(db, "Forecast P0001.")
    assert "demand_forecast_reference" not in json.dumps(r.data)
