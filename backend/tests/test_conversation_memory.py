"""
backend/tests/test_conversation_memory.py

Tests for the multi-turn conversation memory system.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.nlp.context_manager import (
    ContextManager,
    EntityTracker,
    TopicStack,
    Summarizer,
)
from app.nlp.entities import Entities
from app.nlp.intent import Intent
from app.nlp.session_store import (
    HybridSessionStore,
    RedisSessionStore,
    SessionData,
    set_session_store,
)
from app.services.chat_service import ChatSessionManager, set_chat_session_manager


# --- Test Fixtures ----------------------------------------------------------

@pytest.fixture
def memory_session_store():
    """In-memory session store for testing (no Redis/Postgres)."""
    store = HybridSessionStore()
    # Replace Redis with in-memory fallback
    store.redis_store._available = False
    store.redis_store._memory_store = {}
    # Disable Postgres
    store.postgres_store = None
    set_session_store(store)
    yield store
    set_session_store(None)


@pytest.fixture
def chat_manager(memory_session_store):
    """ChatSessionManager with in-memory store."""
    manager = ChatSessionManager(llm_client=None)
    set_chat_session_manager(manager)
    yield manager
    set_chat_session_manager(None)


@pytest.fixture
def context_manager():
    """Fresh ContextManager for each test."""
    return ContextManager(llm_client=None)


# --- EntityTracker Tests ----------------------------------------------------

class TestEntityTracker:
    """Tests for entity tracking and pronoun resolution."""

    def test_track_product_entity(self, context_manager):
        """Product entities are tracked across turns."""
        entities = Entities(product_id="P0001")
        context_manager.entity_tracker.update(entities, 0)

        active = context_manager.entity_tracker.get_active_entities()
        assert active["product_id"] == "P0001"

    def test_track_multiple_products_latest_wins(self, context_manager):
        """Most recent product becomes active."""
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)
        context_manager.entity_tracker.update(Entities(product_id="P0002"), 1)

        active = context_manager.entity_tracker.get_active_entities()
        assert active["product_id"] == "P0002"

    def test_resolve_pronoun_it_to_product(self, context_manager):
        """'it' resolves to most recent product."""
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)

        # User says "forecast it for 14 days"
        message = "forecast it for 14 days"
        entities = Entities()  # No product in current message
        resolved = context_manager.inject_context(message, entities)

        assert resolved.product_id == "P0001"

    def test_resolve_that_product(self, context_manager):
        """'that product' resolves to most recent product."""
        context_manager.entity_tracker.update(Entities(product_id="P0005"), 0)

        message = "what about that product?"
        entities = Entities()
        resolved = context_manager.inject_context(message, entities)

        assert resolved.product_id == "P0005"

    def test_resolve_first_second_product(self, context_manager):
        """'the first one' / 'the second one' resolve correctly."""
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)
        context_manager.entity_tracker.update(Entities(product_id="P0002"), 1)

        # "the first one" -> P0001
        entities = Entities()
        resolved = context_manager.inject_context("tell me about the first one", entities)
        assert resolved.product_id == "P0001"

        # "the second one" -> P0002
        resolved = context_manager.inject_context("what about the second one", entities)
        assert resolved.product_id == "P0002"

    def test_explicit_product_overrides_context(self, context_manager):
        """Explicit product mention in message overrides context."""
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)

        # User explicitly mentions P0002
        message = "forecast P0002 for 7 days"
        entities = Entities(product_id="P0002")
        resolved = context_manager.inject_context(message, entities)

        assert resolved.product_id == "P0002"

    def test_store_entity_tracking(self, context_manager):
        """Store entities are tracked and resolved."""
        context_manager.entity_tracker.update(Entities(store_id="S001"), 0)

        active = context_manager.entity_tracker.get_active_entities()
        assert active["store_id"] == "S001"

        message = "check stock there"
        entities = Entities()
        resolved = context_manager.inject_context(message, entities)
        assert resolved.store_id == "S001"

    def test_category_entity_tracking(self, context_manager):
        """Category entities are tracked."""
        context_manager.entity_tracker.update(Entities(category="Electronics"), 0)

        active = context_manager.entity_tracker.get_active_entities()
        assert active["category"] == "Electronics"

    def test_forget_entity(self, context_manager):
        """'forget P0001' removes entity from history."""
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)
        context_manager.entity_tracker.update(Entities(product_id="P0002"), 1)

        context_manager.entity_tracker.forget_entity("product", "P0001")

        active = context_manager.entity_tracker.get_active_entities()
        assert active["product_id"] == "P0002"

    def test_clear_all_entities(self, context_manager):
        """Clear removes all entity history."""
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)
        context_manager.entity_tracker.update(Entities(store_id="S001"), 0)

        context_manager.entity_tracker.clear()

        active = context_manager.entity_tracker.get_active_entities()
        assert active["product_id"] is None
        assert active["store_id"] is None


# --- TopicStack Tests -------------------------------------------------------

class TestTopicStack:
    """Tests for conversation topic management."""

    def test_push_and_peek_topic(self, context_manager):
        """New topics are pushed and accessible."""
        context_manager.topic_stack.push("P0001 stock check", Intent.CURRENT_STOCK, turn_index=0)

        topic = context_manager.topic_stack.peek()
        assert topic is not None
        assert topic.name == "P0001 stock check"
        assert topic.intent == Intent.CURRENT_STOCK

    def test_pop_returns_to_previous(self, context_manager):
        """Pop returns to previous topic."""
        context_manager.topic_stack.push("Topic A", Intent.CURRENT_STOCK, turn_index=0)
        context_manager.topic_stack.push("Topic B", Intent.DEMAND_FORECAST, turn_index=1)

        popped = context_manager.topic_stack.pop()
        assert popped.name == "Topic B"

        current = context_manager.topic_stack.peek()
        assert current.name == "Topic A"

    def test_switch_to_named_topic(self, context_manager):
        """Can switch to a previous topic by name."""
        context_manager.topic_stack.push("P0001 analysis", Intent.CURRENT_STOCK, turn_index=0)
        context_manager.topic_stack.push("P0002 forecast", Intent.DEMAND_FORECAST, turn_index=1)
        context_manager.topic_stack.push("Category comparison", Intent.CATEGORY_ANALYSIS, turn_index=2)

        # Switch back to P0001
        topic = context_manager.topic_stack.switch_to("P0001", 3)
        assert topic is not None
        assert topic.name == "P0001 analysis"

        current = context_manager.topic_stack.peek()
        assert current.name == "P0001 analysis"

    def test_detect_push_transition(self, context_manager):
        """Detects topic push signals."""
        assert context_manager.topic_stack.detect_transition("now check P0002") == "push"
        assert context_manager.topic_stack.detect_transition("what about store 2?") == "push"
        assert context_manager.topic_stack.detect_transition("also look at category A") == "push"

    def test_detect_pop_transition(self, context_manager):
        """Detects topic pop signals."""
        assert context_manager.topic_stack.detect_transition("back to P0001") == "pop"
        assert context_manager.topic_stack.detect_transition("return to previous topic") == "pop"
        assert context_manager.topic_stack.detect_transition("go back to forecast") == "pop"

    def test_no_transition_for_normal_questions(self, context_manager):
        """Normal follow-ups don't trigger transitions."""
        assert context_manager.topic_stack.detect_transition("what is the forecast?") is None
        assert context_manager.topic_stack.detect_transition("tell me more") is None
        assert context_manager.topic_stack.detect_transition("why?") is None


# --- ContextManager Integration Tests ---------------------------------------

class TestContextManagerIntegration:
    """Tests for full context manager workflow."""

    def test_multi_turn_conversation_flow(self, context_manager):
        """Full conversation: stock -> forecast -> reorder."""
        # Turn 1: Check stock for P0001
        entities1 = Entities(product_id="P0001")
        intent1 = Intent.CURRENT_STOCK
        cm = context_manager.process_turn(
            session_id="test-session",
            user_message="How much stock for P0001?",
            entities=entities1,
            intent=intent1,
            parse_method="rules",
            response="P0001 has 100 units.",
            data={"product_id": "P0001", "total_inventory": 100},
        )

        # Turn 2: "Forecast it" - should carry P0001
        entities2 = Entities()  # No product mentioned
        intent2 = Intent.DEMAND_FORECAST
        cm.process_turn(
            session_id="test-session",
            user_message="Forecast it for 14 days",
            entities=entities2,
            intent=intent2,
            parse_method="rules",
            response="Forecast: 88 units.",
            data={"forecast_total_units": 88},
        )

        # Turn 3: "Reorder it" - should still be P0001
        entities3 = Entities()
        intent3 = Intent.REORDER_RECOMMENDATION
        cm.process_turn(
            session_id="test-session",
            user_message="What should I reorder?",
            entities=entities3,
            intent=intent3,
            parse_method="rules",
            response="Reorder 20 units.",
            data={"recommended_reorder_quantity": 20},
        )

        # Verify entity was carried through all turns
        active = cm.entity_tracker.get_active_entities()
        assert active["product_id"] == "P0001"

    def test_context_command_reset(self, context_manager):
        """'reset' command clears context."""
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)
        context_manager.topic_stack.push("Test", Intent.CURRENT_STOCK, turn_index=0)

        response = context_manager.handle_command("reset")

        assert "cleared" in response.lower()
        assert context_manager.entity_tracker.get_active_entities()["product_id"] is None
        assert len(context_manager.topic_stack.topics) == 0

    def test_context_command_forget(self, context_manager):
        """'forget P0001' removes specific entity."""
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)
        context_manager.entity_tracker.update(Entities(product_id="P0002"), 1)

        response = context_manager.handle_command("forget P0001")

        assert "forgot" in response.lower()
        active = context_manager.entity_tracker.get_active_entities()
        assert active["product_id"] == "P0002"

    def test_context_command_back_to(self, context_manager):
        """'back to' switches topic."""
        context_manager.topic_stack.push("P0001", Intent.CURRENT_STOCK, turn_index=0)
        context_manager.topic_stack.push("P0002", Intent.DEMAND_FORECAST, turn_index=1)

        response = context_manager.handle_command("back to P0001")

        assert "switched" in response.lower()
        current = context_manager.topic_stack.peek()
        assert current.name == "P0001"

    def test_context_command_show_history(self, context_manager):
        """'show history' returns summary."""
        context_manager.turn_count = 5
        context_manager.entity_tracker.update(Entities(product_id="P0001"), 0)

        response = context_manager.handle_command("show history")

        assert "5 turns" in response
        assert "P0001" in response


# --- Session Store Tests ----------------------------------------------------

class TestSessionStore:
    """Tests for session persistence."""

    def test_create_and_get_session(self, memory_session_store):
        """Create session and retrieve it."""
        session = memory_session_store.create_session(user_id="user123")
        assert session.session_id is not None
        assert session.user_id == "user123"

        retrieved = memory_session_store.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        assert retrieved.user_id == "user123"

    def test_add_turn(self, memory_session_store):
        """Add turns to session."""
        session = memory_session_store.create_session()
        turn = {
            "turn_index": 0,
            "user_message": "Hello",
            "assistant_response": "Hi there!",
            "intent": "CURRENT_STOCK",
            "entities": {"product_id": "P0001"},
            "parse_method": "rules",
            "data": {},
        }
        memory_session_store.add_turn(session.session_id, turn)

        retrieved = memory_session_store.get_session(session.session_id)
        assert len(retrieved.turns) == 1
        assert retrieved.turns[0]["user_message"] == "Hello"

    def test_session_ttl_extends_on_access(self, memory_session_store):
        """Session TTL extends on access (Redis behavior simulated)."""
        session = memory_session_store.create_session()
        # Just verify session exists after "access"
        retrieved = memory_session_store.get_session(session.session_id)
        assert retrieved is not None


# --- ChatSessionManager Tests ----------------------------------------------

class TestChatSessionManager:
    """Tests for the full chat session manager."""

    def test_new_session_created_when_none_provided(self, chat_manager, db_session):
        """New session created when no session_id provided."""
        response = chat_manager.handle_message(
            db=db_session,
            message="How much stock for P0001?",
            session_id=None,
        )

        assert response.session_id is not None
        assert response.intent == Intent.CURRENT_STOCK
        assert response.entities.get("product_id") == "P0001"

    def test_continues_existing_session(self, chat_manager, db_session):
        """Continues existing session when session_id provided."""
        # First message
        response1 = chat_manager.handle_message(
            db=db_session,
            message="How much stock for P0001?",
            session_id=None,
        )
        session_id = response1.session_id

        # Second message in same session
        response2 = chat_manager.handle_message(
            db=db_session,
            message="Forecast it for 14 days",
            session_id=session_id,
        )

        assert response2.session_id == session_id
        assert response2.entities.get("product_id") == "P0001"  # Carried over

    def test_entity_carryover_across_turns(self, chat_manager, db_session):
        """Product entity carries across multiple turns."""
        session_id = None

        # Turn 1: Ask about P0001
        response = chat_manager.handle_message(
            db=db_session,
            message="How much stock for P0001?",
            session_id=session_id,
        )
        session_id = response.session_id

        # Turn 2: "Forecast it" - no product mentioned
        response = chat_manager.handle_message(
            db=db_session,
            message="Forecast it for 7 days",
            session_id=session_id,
        )

        assert response.entities.get("product_id") == "P0001"

        # Turn 3: "Stockout risk for it"
        response = chat_manager.handle_message(
            db=db_session,
            message="Stockout risk for it",
            session_id=session_id,
        )

        assert response.entities.get("product_id") == "P0001"

    def test_explicit_product_changes_context(self, chat_manager, db_session):
        """Explicit product mention changes active entity."""
        session_id = None

        # Turn 1: P0001
        response = chat_manager.handle_message(
            db=db_session,
            message="Stock for P0001",
            session_id=session_id,
        )
        session_id = response.session_id

        # Turn 2: Explicitly ask about P0002
        response = chat_manager.handle_message(
            db=db_session,
            message="What about P0002?",
            session_id=session_id,
        )

        assert response.entities.get("product_id") == "P0002"

        # Turn 3: "Forecast it" should now be P0002
        response = chat_manager.handle_message(
            db=db_session,
            message="Forecast it",
            session_id=session_id,
        )

        assert response.entities.get("product_id") == "P0002"

    def test_context_included_in_response(self, chat_manager, db_session):
        """Response includes context info."""
        response = chat_manager.handle_message(
            db=db_session,
            message="Stock for P0001",
            session_id=None,
        )

        assert response.context is not None
        assert "active_entities" in response.context
        assert response.context["active_entities"].get("product_id") == "P0001"

    def test_context_commands_work(self, chat_manager, db_session):
        """Context commands like 'reset' work."""
        session_id = None

        # Set up context
        chat_manager.handle_message(db=db_session, message="Stock for P0001", session_id=session_id)
        session_id = chat_manager.handle_message(
            db=db_session, message="Forecast it", session_id=session_id
        ).session_id

        # Reset
        response = chat_manager.handle_message(
            db=db_session,
            message="reset",
            session_id=session_id,
        )

        assert "cleared" in response.message.lower()

        # Next message should not have P0001
        response = chat_manager.handle_message(
            db=db_session,
            message="Forecast it",
            session_id=session_id,
        )

        # Should ask for clarification since no product in context
        assert response.entities.get("product_id") is None

    def test_multi_entity_tracking(self, chat_manager, db_session):
        """Multiple products tracked in same conversation."""
        session_id = None

        # Ask about P0001 and P0002. Both calls must share ONE session --
        # the first call returns the freshly created session id, which the
        # second call has to reuse (passing None again would discard the
        # first turn and "the first one" would have nothing to point at).
        session_id = chat_manager.handle_message(
            db=db_session, message="Stock for P0001", session_id=session_id
        ).session_id
        session_id = chat_manager.handle_message(
            db=db_session, message="Stock for P0002", session_id=session_id
        ).session_id

        # Both should be in history
        # "the first one" -> P0001
        response = chat_manager.handle_message(
            db=db_session,
            message="Forecast the first one",
            session_id=session_id,
        )
        assert response.entities.get("product_id") == "P0001"

        # "the second one" -> P0002
        response = chat_manager.handle_message(
            db=db_session,
            message="What about the second one?",
            session_id=session_id,
        )
        assert response.entities.get("product_id") == "P0002"

    def test_store_entity_carryover(self, chat_manager, db_session):
        """Store entity carries over."""
        session_id = None

        response = chat_manager.handle_message(
            db=db_session,
            message="Stock for P0001 at S001",
            session_id=session_id,
        )
        session_id = response.session_id

        response = chat_manager.handle_message(
            db=db_session,
            message="How much at that store?",
            session_id=session_id,
        )

        assert response.entities.get("store_id") == "S001"

    def test_session_listing(self, chat_manager, db_session):
        """Can list sessions."""
        chat_manager.handle_message(db=db_session, message="Test 1", session_id=None)
        chat_manager.handle_message(db=db_session, message="Test 2", session_id=None)

        sessions = chat_manager.list_sessions()
        assert len(sessions) >= 2


# --- Schema Validation Tests -----------------------------------------------

class TestConversationSchemas:
    """Tests for conversation API schemas."""

    def test_chat_request_schema(self):
        from app.schemas.conversation import ChatRequest
        req = ChatRequest(message="Hello", session_id="abc", user_id="user1")
        assert req.message == "Hello"
        assert req.session_id == "abc"
        assert req.user_id == "user1"

    def test_chat_response_schema(self):
        from app.schemas.conversation import ChatResponse
        resp = ChatResponse(
            message="Hello!",
            intent="CURRENT_STOCK",
            entities={"product_id": "P0001"},
            parse_method="rules",
            data={"total_inventory": 100},
            session_id="session1",
            context={"active_entities": {"product_id": "P0001"}},
        )
        assert resp.session_id == "session1"
        assert resp.context["active_entities"]["product_id"] == "P0001"

    def test_session_info_schema(self):
        from app.schemas.conversation import SessionInfo
        from datetime import datetime
        info = SessionInfo(
            session_id="s1",
            user_id="u1",
            turn_count=5,
            summary="Test summary",
            active_entities={"product_id": "P0001"},
            current_topic="P0001 analysis",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert info.turn_count == 5


# --- Helper for DB session in tests ----------------------------------------

# Small, deterministic slice of the production schema. The chat tools under
# test (current stock, demand forecast, stockout risk) read from the DB, so a
# bare (empty) SQLite database makes every tool raise NotFoundError and the
# entity-carryover assertions can never pass. These seeds mirror the real
# dataset's dimensions (5 categories, 4 regions, 4 weather conditions,
# 4 seasons) so the live feature builder and the trained XGBoost models --
# which use native categorical support -- encode identically to production.
SEED_PRODUCTS = ["P0001", "P0002", "P0003", "P0004", "P0005"]
SEED_STORES = ["S001", "S002", "S003"]
SEED_CATEGORIES = ["Groceries", "Electronics", "Clothing", "Furniture", "Toys"]
SEED_REGIONS = ["North", "South", "East", "West"]
SEED_WEATHER = ["Sunny", "Rainy", "Cloudy", "Snowy"]
SEED_SEASONS = ["Spring", "Summer", "Autumn", "Winter"]
SEED_HISTORY_DAYS = 21  # > max(LAG_DAYS + ROLLING_WINDOWS) = 14
SEED_START_DATE = date(2022, 1, 1)


def seed_test_database(db) -> None:
    """Insert a small but complete (Date, Store, Product) history."""
    from app.models import DailyInventory, DailySales, Product, Store

    for product_id in SEED_PRODUCTS:
        db.add(Product(product_id=product_id, name=f"Product {product_id}", sku=f"SKU-{product_id}", category="Testing"))
    for store_id in SEED_STORES:
        db.add(Store(store_id=store_id))

    for day_offset in range(SEED_HISTORY_DAYS):
        current_date = SEED_START_DATE + timedelta(days=day_offset)
        for p_idx, product_id in enumerate(SEED_PRODUCTS):
            for s_idx, store_id in enumerate(SEED_STORES):
                units_sold = 40 + 5 * (p_idx + 1) + 3 * (s_idx + 1) + (day_offset % 7)
                inventory_level = 600 + 25 * s_idx + 10 * p_idx - 2 * day_offset

                db.add(
                    DailySales(
                        date=current_date,
                        store_id=store_id,
                        product_id=product_id,
                        category=SEED_CATEGORIES[(p_idx + day_offset) % len(SEED_CATEGORIES)],
                        region=SEED_REGIONS[(s_idx + day_offset) % len(SEED_REGIONS)],
                        units_sold=units_sold,
                        price=round(20.0 + 5 * (p_idx + 1), 2),
                        discount=5 if day_offset % 5 == 0 else 0,
                        holiday_promotion=day_offset % 7 in (5, 6),
                        weather_condition=SEED_WEATHER[(day_offset + s_idx) % len(SEED_WEATHER)],
                        competitor_pricing=round(19.5 + 5 * (p_idx + 1), 2),
                        seasonality=SEED_SEASONS[(day_offset // 7 + p_idx) % len(SEED_SEASONS)],
                        demand_forecast_reference=float(units_sold) * 1.05,
                        possible_stock_constrained=False,
                    )
                )
                db.add(
                    DailyInventory(
                        date=current_date,
                        store_id=store_id,
                        product_id=product_id,
                        inventory_level=inventory_level,
                        units_ordered=50,
                    )
                )
    db.commit()


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session seeded with reference data."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()
    seed_test_database(db)
    try:
        yield db
    finally:
        db.close()
