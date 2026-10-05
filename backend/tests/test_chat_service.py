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
from app.nlp.rules import classify_intent, extract_entities, is_stock_write_request
from app.services.chat_service import _is_pending_sale_reply, handle_chat_message


# --- Rule-based layer (no network, always available) -----------------------

@pytest.mark.parametrize(
    "message,expected_intent",
    [
        ("How much stock do we have for P0001?", Intent.CURRENT_STOCK),
        ("Which products are low on stock?", Intent.LOW_STOCK),
        ("What are our top-selling products?", Intent.TOP_SELLING),
        ("What are the bottom selling products?", Intent.BOTTOM_SELLING),
        ("How many items are left?", Intent.CURRENT_STOCK),
        ("What's my current inventory?", Intent.CURRENT_STOCK),
        ("Do I have enough stock?", Intent.STOCKOUT_RISK),
        ("How much money did we make this month?", Intent.REVENUE_ANALYSIS),
        ("What did we sell this month?", Intent.SALES_TREND),
        ("What was my gross profit last month?", Intent.FINANCIAL_ANALYSIS),
        ("Which products made the most profit?", Intent.FINANCIAL_ANALYSIS),
        ("Which products are likely to run out soon?", Intent.STOCKOUT_RISK),
        ("Which products are low on stock and selling quickly?", Intent.LOW_STOCK_FAST_SELLING),
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


def test_financial_grouping_and_lowest_sort_are_extracted():
    entities = extract_entities("Which product had the least gross profit?")
    assert entities.group_by == "product"
    assert entities.sort_order == "ascending"
    assert classify_intent("Which product had the least gross profit?") == Intent.FINANCIAL_ANALYSIS


def test_rule_based_entity_extraction_no_entities():
    entities = extract_entities("what are the top selling products")
    assert entities.product_id is None
    assert entities.category is None


@pytest.mark.parametrize(
    "message,expected_intent",
    [
        ("Will P0005 run out of stock?", Intent.STOCKOUT_RISK),
        ("Can you predict demand for P0001 next week?", Intent.DEMAND_FORECAST),
        ("P0001 is running low on stock", Intent.LOW_STOCK),
    ],
)
def test_specific_intent_wins_over_generic_product_stock_mention(message, expected_intent):
    assert classify_intent(message) == expected_intent


def test_forecast_horizon_understands_week_phrasing():
    assert extract_entities("Forecast P0001 for the coming week").forecast_horizon == 7
    assert extract_entities("Predict P0001 demand over the next two weeks").forecast_horizon == 14


def test_rule_layer_recovers_common_forecast_typo():
    assert classify_intent("Forcast P0001 for the next week") == Intent.DEMAND_FORECAST
    assert extract_entities("Forcast P0001 for the next week").forecast_horizon == 7


def test_stock_change_request_is_not_misread_as_a_query():
    assert is_stock_write_request("I sold 5 units of P0001")
    assert is_stock_write_request("Please deduct 5 units from inventory")


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
    # An LLM may classify the request, but cannot invent an unmentioned SKU.
    assert entities.product_id is None
    assert len(fake.calls) == 1


def test_llm_can_select_only_a_registered_tool():
    fake = FakeLLMClient(json_response={
        "tool": "get_current_stock",
        "arguments": {"product_id": "P0003"},
    })
    intent, entities, method = parser.parse("How stocked are we? P0003", llm_client=fake)
    assert method == "llm"
    assert intent == Intent.CURRENT_STOCK
    assert entities.product_id == "P0003"


def test_llm_unregistered_tool_is_rejected():
    fake = FakeLLMClient(json_response={"tool": "run_sql", "arguments": {}})
    intent, _, _ = parser.parse("please inspect inventory", llm_client=fake)
    assert intent == Intent.UNKNOWN


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
    assert entities.product_id is None
    assert not hasattr(entities, "malicious_field")


@pytest.mark.parametrize(
    "raw_response",
    [
        '```json\n{"intent":"LOW_STOCK","entities":[]}\n```',
        '["not", "an", "object"]',
    ],
)
def test_llm_malformed_json_shapes_do_not_break_chat_parser(raw_response):
    class RawLLMClient:
        def complete_json(self, system_prompt, user_message):
            return raw_response

    intent, _, _ = parser.parse("some ambiguous wording", llm_client=RawLLMClient())
    assert intent in {Intent.UNKNOWN, Intent.LOW_STOCK}


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


def test_chat_sale_request_collects_details_without_changing_stock(db):
    from app.models import DailyInventory
    from app.repositories import inventory_repository

    latest = inventory_repository.get_latest_date(db)
    before = db.get(DailyInventory, (latest, "S001", "P0001")) if latest else None
    before_units = before.inventory_level if before else None

    r = handle_chat_message(db, "I sold 5 units of P0001")

    assert r.intent == Intent.RECORD_SALE
    assert r.data["sale_status"] == "collecting_details"
    assert r.data["pending_sale"]["units_sold"] == 5
    assert "store ID" in r.message
    if before is not None:
        db.refresh(before)
        assert before.inventory_level == before_units


def test_chat_sale_understands_about_60_stocks_and_short_store_id(db):
    from app.nlp.session_store import SessionData
    from app.services.chat_service import ChatSessionManager

    class MemorySessionStore:
        def __init__(self): self.sessions = {}
        def create_session(self, user_id=None, session_id=None):
            session = SessionData(session_id=session_id or "sale-phrase-test", user_id=user_id)
            self.sessions[session.session_id] = session
            return session
        def get_session(self, session_id): return self.sessions.get(session_id)
        def save_session(self, session): self.sessions[session.session_id] = session
        def add_turn(self, session_id, turn): self.sessions[session_id].turns.append(turn)

    manager = ChatSessionManager()
    manager.session_store = MemorySessionStore()
    response = manager.handle_message(db, "i sold about 60 stocks of P0001 of S0001")
    assert response.intent == Intent.RECORD_SALE
    assert response.data["pending_sale"]["units_sold"] == 60
    assert response.data["pending_sale"]["product_id"] == "P0001"
    assert response.data["pending_sale"]["store_id"] == "S001"
    assert extract_entities("i sold about 60 stocks of P0001 of S0002").store_id == "S002"


def test_ambiguous_deduction_followup_for_sales_resumes_sale_flow(db):
    from app.nlp.session_store import SessionData
    from app.services.chat_service import ChatSessionManager

    class MemorySessionStore:
        def __init__(self): self.sessions = {}
        def create_session(self, user_id=None, session_id=None):
            session = SessionData(session_id=session_id or "clarify-sale-test", user_id=user_id)
            self.sessions[session.session_id] = session
            return session
        def get_session(self, session_id): return self.sessions.get(session_id)
        def save_session(self, session): self.sessions[session.session_id] = session
        def add_turn(self, session_id, turn): self.sessions[session_id].turns.append(turn)

    manager = ChatSessionManager()
    manager.session_store = MemorySessionStore()
    first = manager.handle_message(db, "deduct the p0001 product of store s001 by 50 stocks")
    assert first.intent == Intent.UNKNOWN
    assert "customer sale" in first.message.lower(), first.message
    assert manager.session_store.sessions[first.session_id].metadata.get("pending_action_clarification")
    followup = manager.handle_message(db, "for sales", session_id=first.session_id)
    assert followup.intent == Intent.RECORD_SALE
    assert followup.data["pending_sale"]["units_sold"] == 50
    assert followup.data["pending_sale"]["product_id"] == "P0001"
    assert followup.data["pending_sale"]["store_id"] == "S001"


@pytest.mark.parametrize("message", [
    "can you add product quantity of P001 of S001 store by 100 units",
    "i recieved 100 units of product P0001 of store S0001",
])
def test_chat_understands_natural_stock_receipt_requests(db, message):
    from app.nlp.session_store import SessionData
    from app.services.chat_service import ChatSessionManager

    class MemorySessionStore:
        def __init__(self): self.sessions = {}
        def create_session(self, user_id=None, session_id=None):
            session = SessionData(session_id=session_id or "receive-phrase-test", user_id=user_id)
            self.sessions[session.session_id] = session
            return session
        def get_session(self, session_id): return self.sessions.get(session_id)
        def save_session(self, session): self.sessions[session.session_id] = session
        def add_turn(self, session_id, turn): self.sessions[session_id].turns.append(turn)

    manager = ChatSessionManager()
    manager.session_store = MemorySessionStore()
    response = manager.handle_message(db, message)
    assert response.intent == Intent.RECEIVE_STOCK
    assert response.data["adjustment_status"] == "awaiting_confirmation"
    assert response.data["pending_adjustment"]["product_id"] == "P0001"
    assert response.data["pending_adjustment"]["store_id"] == "S001"
    assert response.data["pending_adjustment"]["quantity_delta"] == 100
    assert "confirm" in response.message.lower()


def test_receipt_followup_does_not_fall_through_to_project_documentation(db):
    from app.nlp.session_store import SessionData
    from app.services.chat_service import ChatSessionManager

    class MemorySessionStore:
        def __init__(self): self.sessions = {}
        def create_session(self, user_id=None, session_id=None):
            session = SessionData(session_id=session_id or "receive-followup-test", user_id=user_id)
            self.sessions[session.session_id] = session
            return session
        def get_session(self, session_id): return self.sessions.get(session_id)
        def save_session(self, session): self.sessions[session.session_id] = session
        def add_turn(self, session_id, turn): self.sessions[session_id].turns.append(turn)

    manager = ChatSessionManager()
    manager.session_store = MemorySessionStore()
    first = manager.handle_message(db, "add 100 units of P0001 at S001")
    followup = manager.handle_message(db, "100 stocks recieved", session_id=first.session_id)
    assert followup.intent == Intent.RECEIVE_STOCK
    assert followup.data["adjustment_status"] == "awaiting_confirmation"
    assert "Based on:" not in followup.message


def test_pending_sale_does_not_capture_unrelated_stock_question():
    draft = {"product_id": "P0001", "store_id": "S001", "units_sold": 2, "price": 10.0}
    assert not _is_pending_sale_reply("How much stock do we have for P0001?", draft)
    assert _is_pending_sale_reply("confirm sale", draft)


def test_chat_answers_project_questions_from_local_docs(db):
    r = handle_chat_message(db, "How is the forecast model evaluated in this project?")
    assert r.parse_method == "knowledge"
    assert "forecast" in r.message.lower() or "mae" in r.message.lower()
    assert r.data["sources"]


def test_chat_calculates_recorded_net_revenue(db):
    r = handle_chat_message(db, "How much revenue did we record this year?")
    assert r.intent == Intent.REVENUE_ANALYSIS
    assert r.data["discounts_included"] is True
    assert r.data["net_sales_revenue"] >= 0
    assert "revenue" in r.message.lower()


def test_chat_combines_low_stock_with_recent_sales_velocity(db):
    r = handle_chat_message(db, "Which products are low on stock and selling quickly?")
    assert r.intent == Intent.LOW_STOCK_FAST_SELLING
    assert "items" in r.data
    assert "sales_window" in r.data


def test_stock_movement_question_reads_history_instead_of_preparing_a_write(db):
    r = handle_chat_message(db, "Show stock history for P0001")
    assert r.intent == Intent.STOCK_HISTORY
    assert isinstance(r.data["items"], list)


def test_chat_explains_profit_is_unavailable_without_cost_data(db):
    r = handle_chat_message(db, "How much profit did we make?")
    assert r.intent == Intent.FINANCIAL_ANALYSIS
    assert r.data["group_by"] == "total"
    assert "gross_profit_or_loss" in r.data["items"][0]


def test_month_phrases_are_converted_to_date_ranges():
    from datetime import date

    entities = extract_entities("Revenue in September 2025")
    assert entities.date_range == {"start_date": "2025-09-01", "end_date": "2025-09-30"}
    last_month = extract_entities("What about last month?").date_range
    today = date.today()
    last_day = today.replace(day=1).toordinal() - 1
    expected_end = date.fromordinal(last_day)
    expected_start = expected_end.replace(day=1)
    assert last_month == {"start_date": expected_start.isoformat(), "end_date": expected_end.isoformat()}


def test_revenue_follow_up_reuses_metric_and_changes_period(db):
    from datetime import date, timedelta
    from app.nlp.session_store import SessionData
    from app.services.chat_service import ChatSessionManager

    class MemorySessionStore:
        def __init__(self):
            self.sessions = {}
        def create_session(self, user_id=None, session_id=None):
            session = SessionData(session_id=session_id or "revenue-followup", user_id=user_id)
            self.sessions[session.session_id] = session
            return session
        def get_session(self, session_id):
            return self.sessions.get(session_id)
        def save_session(self, session):
            self.sessions[session.session_id] = session
        def add_turn(self, session_id, turn):
            self.sessions[session_id].turns.append(turn)

    manager = ChatSessionManager()
    manager.session_store = MemorySessionStore()
    first = manager.handle_message(db, "How much revenue did we make this month?")
    follow_up = manager.handle_message(db, "What about last month?", session_id=first.session_id)
    today = date.today()
    end = today.replace(day=1) - timedelta(days=1)
    start = end.replace(day=1)
    assert follow_up.intent == Intent.REVENUE_ANALYSIS
    assert follow_up.data["filters"]["start_date"] == start.isoformat()
    assert follow_up.data["filters"]["end_date"] == end.isoformat()


def test_stock_adjustment_chat_preview_does_not_record_a_sale(db, monkeypatch):
    from app.models import DailyInventory
    from app.models.sales import SalesTransaction
    from app.models.stock_movement import StockMovement
    from app.nlp.session_store import SessionData
    from app.services.chat_service import ChatSessionManager
    from app.repositories import inventory_repository

    class MemorySessionStore:
        def __init__(self):
            self.sessions = {}
        def create_session(self, user_id=None, session_id=None):
            session = SessionData(session_id=session_id or "chat-test-session", user_id=user_id)
            self.sessions[session.session_id] = session
            return session
        def get_session(self, session_id):
            return self.sessions.get(session_id)
        def save_session(self, session):
            self.sessions[session.session_id] = session
        def add_turn(self, session_id, turn):
            self.sessions[session_id].turns.append(turn)

    latest = inventory_repository.get_latest_date(db)
    stock = db.get(DailyInventory, (latest, "S001", "P0001")) if latest else None
    if stock is None:
        pytest.skip("fixture database has no P0001 stock at S001")
    before = stock.inventory_level
    sales_before = db.query(SalesTransaction).filter_by(product_id="P0001", store_id="S001").count()
    movements_before = db.query(StockMovement).filter_by(product_id="P0001", store_id="S001").count()
    manager = ChatSessionManager()
    manager.session_store = MemorySessionStore()
    response = manager.handle_message(db, "2 units of P0001 at S001 are damaged")
    assert response.intent == Intent.ADJUST_STOCK
    assert response.data["adjustment_status"] == "awaiting_confirmation"
    assert "not create a sale" in response.message.lower()
    db.refresh(stock)
    assert stock.inventory_level == before

    # Confirmation writes one adjustment movement but no sales/revenue row.
    monkeypatch.setattr(db, "commit", lambda: db.flush())
    confirmed = manager.handle_message(db, "confirm", session_id=response.session_id)
    assert confirmed.data["adjustment_status"] == "recorded"
    db.refresh(stock)
    assert stock.inventory_level == before - 2
    assert db.query(StockMovement).filter_by(product_id="P0001", store_id="S001").count() == movements_before + 1
    assert db.query(SalesTransaction).filter_by(product_id="P0001", store_id="S001").count() == sales_before


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


def test_chat_rejects_llm_phrasing_with_unverified_numbers(db):
    fake = FakeLLMClient(text_response="P0001 has 999 units on hand.")
    r = handle_chat_message(db, "How much stock do we have for P0001?", llm_client=fake)
    assert "999" not in r.message
    assert "P0001" in r.message


def test_named_product_question_asks_for_catalog_id_instead_of_answering_totals(db):
    r = handle_chat_message(db, "What profit did Product Apple make?")
    assert r.data is None
    assert "product id" in r.message.lower()


def test_chat_demand_forecast_column_never_appears_in_response(db):
    """The chatbot must never surface the leaky source `Demand Forecast` column."""
    r = handle_chat_message(db, "Forecast P0001.")
    assert "demand_forecast_reference" not in json.dumps(r.data)
