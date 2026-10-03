"""
backend/app/services/chat_service.py

Orchestrates: message -> parse (rules, then LLM if needed) -> validate ->
backend tool call (spec section 33) -> structured result -> natural-
language response.

NO-HALLUCINATION POLICY (spec section 55), enforced structurally:
  - Every intent that needs a product ID is checked against the real
    database via product_repository.product_exists BEFORE any number is
    computed. Unknown products get a fixed "not found" message -- the
    LLM never sees a chance to invent a substitute value.
  - Tool functions return ONLY data computed by Phase 4-6 services
    (real DB queries / real saved ML models). The LLM (when available)
    is only asked to phrase that data in words -- see
    RESPONSE_GENERATION_SYSTEM_PROMPT -- and a deterministic template
    formatter is used whenever the LLM is unavailable, so the system
    never silently depends on the LLM to produce a legitimate answer.

CONVERSATION MEMORY (Phase 11):
  - Session-based multi-turn context with entity carryover
  - Pronoun resolution ("it", "that product") via EntityTracker
  - Topic management via TopicStack
  - Optional LLM summarization for long conversations
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.nlp import (
    parser,
    ContextManager,
    EntityTracker,
    SessionData,
    get_session_store,
    create_context_manager,
)
from app.nlp.entities import Entities
from app.nlp.intent import PRODUCT_REQUIRED_INTENTS, Intent
from app.nlp.llm_client import LLMUnavailableError
from app.nlp.prompts import RESPONSE_GENERATION_SYSTEM_PROMPT
from app.nlp.rules import looks_like_follow_up
from app.repositories import product_repository
from app.schemas.chat import ChatResponse
from app.schemas.conversation import ChatRequest, ChatResponse as ConversationChatResponse
from app.services import forecast_service, inventory_service, reorder_service, sales_service, stockout_service
from app.services.errors import InvalidRequestError, NotFoundError

log = logging.getLogger("chat_service")


# --- Constants --------------------------------------------------------------

HELP_TEXT = (
    "I can help with: current stock for a product, which products are low on stock, "
    "top or bottom selling products, sales trends, demand forecasts, stockout risk, "
    "and reorder recommendations. Try asking something like \"How much stock does "
    "P0001 have?\" or \"Should I reorder P0007?\""
)

CONTEXT_COMMANDS = {
    "reset", "clear context", "start over",
    "show history", "show context",
    "forget",
    "back to",
}


# --- Tool functions (spec section 33) --------------------------------------

def _tool_current_inventory(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like to check the stock for?")
    return inventory_service.get_product_inventory(db, entities.product_id).model_dump(mode="json")


def _tool_low_stock(db: Session, entities: Entities) -> dict:
    return inventory_service.get_low_stock(db).model_dump(mode="json")


def _tool_top_selling(db: Session, entities: Entities) -> dict:
    return sales_service.get_top_products(db, limit=10).model_dump(mode="json")


def _tool_bottom_selling(db: Session, entities: Entities) -> dict:
    return sales_service.get_bottom_products(db, limit=10).model_dump(mode="json")


def _tool_sales_trend(db: Session, entities: Entities) -> dict:
    result = sales_service.get_sales_trend(
        db, granularity="monthly", product_id=entities.product_id, category=entities.category
    )
    return result.model_dump(mode="json")


def _tool_product_info(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like information about?")
    inventory = inventory_service.get_product_inventory(db, entities.product_id)
    trend = sales_service.get_sales_trend(db, granularity="monthly", product_id=entities.product_id)
    return {
        "inventory": inventory.model_dump(mode="json"),
        "monthly_sales_trend": trend.model_dump(mode="json"),
    }


def _tool_forecast_demand(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like a demand forecast for?")
    horizon = entities.forecast_horizon or get_settings().default_forecast_horizon
    result = forecast_service.forecast_product_demand(db, entities.product_id, horizon=horizon)
    result["target_date"] = result["target_date"].isoformat()
    return result


def _tool_stockout_risk(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like to check stockout risk for?")
    return stockout_service.calculate_stockout_risk(db, entities.product_id).model_dump(mode="json")


def _tool_reorder_recommendation(db: Session, entities: Entities) -> dict:
    if not entities.product_id:
        raise MissingEntityError("Which product would you like a reorder recommendation for?")
    return reorder_service.calculate_reorder(db, entities.product_id).model_dump(mode="json")


def _tool_category_analysis(db: Session, entities: Entities) -> dict:
    return {"categories": [c.model_dump(mode="json") for c in sales_service.get_category_analysis(db)]}


def _tool_store_analysis(db: Session, entities: Entities) -> dict:
    return {"stores": [s.model_dump(mode="json") for s in sales_service.get_store_analysis(db)]}


TOOLS = {
    Intent.CURRENT_STOCK: _tool_current_inventory,
    Intent.LOW_STOCK: _tool_low_stock,
    Intent.TOP_SELLING: _tool_top_selling,
    Intent.BOTTOM_SELLING: _tool_bottom_selling,
    Intent.SALES_TREND: _tool_sales_trend,
    Intent.PRODUCT_INFO: _tool_product_info,
    Intent.DEMAND_FORECAST: _tool_forecast_demand,
    Intent.STOCKOUT_RISK: _tool_stockout_risk,
    Intent.REORDER_RECOMMENDATION: _tool_reorder_recommendation,
    Intent.CATEGORY_ANALYSIS: _tool_category_analysis,
    Intent.STORE_ANALYSIS: _tool_store_analysis,
}


# --- Exceptions -------------------------------------------------------------

class MissingEntityError(Exception):
    """Raised when an intent needs an entity (e.g. product_id) that wasn't extracted."""


# --- Deterministic template fallback (used when no LLM / LLM unavailable) --

def _template_response(intent: Intent, entities: Entities, data: dict) -> str:
    if intent == Intent.CURRENT_STOCK:
        return f"{data['product_id']} currently has {data['total_inventory']:.0f} units in stock (as of {data['as_of_date']}, across {len(data['stores'])} stores)."
    if intent == Intent.LOW_STOCK:
        return f"{data['count']} store-product combinations are below the low-stock threshold of {data['threshold']} units (as of {data['as_of_date']})."
    if intent == Intent.TOP_SELLING:
        top = data["products"][:3]
        names = ", ".join(f"{p['product_id']} ({p['total_units_sold']:.0f} units)" for p in top)
        return f"The top-selling products are: {names}."
    if intent == Intent.BOTTOM_SELLING:
        bottom = data["products"][:3]
        names = ", ".join(f"{p['product_id']} ({p['total_units_sold']:.0f} units)" for p in bottom)
        return f"The lowest-selling products are: {names}."
    if intent == Intent.DEMAND_FORECAST:
        return (
            f"Forecast demand for {data['product_id']} over the next {data['model_horizon_days']} days "
            f"(by {data['target_date']}) is approximately {data['forecast_total_units']:.0f} units across all stores."
        )
    if intent == Intent.STOCKOUT_RISK:
        return f"{data['product_id']} has {data['risk']} stockout risk. {data['reason']}"
    if intent == Intent.REORDER_RECOMMENDATION:
        return (
            f"{data['product_id']} currently has {data['current_inventory']:.0f} units. Estimated demand over the "
            f"{data['assumptions']['lead_time_days']}-day lead time is {data['forecast_lead_time_demand']:.1f} units, "
            f"with a safety stock of {data['safety_stock']:.1f}. Recommended reorder quantity: "
            f"{data['recommended_reorder_quantity']:.0f} units."
        )
    if intent == Intent.CATEGORY_ANALYSIS:
        top = data["categories"][:3]
        names = ", ".join(f"{c['category']} ({c['total_units_sold']:.0f} units)" for c in top)
        return f"Top categories by units sold: {names}."
    if intent == Intent.STORE_ANALYSIS:
        top = data["stores"][:3]
        names = ", ".join(f"{s['store_id']} ({s['total_units_sold']:.0f} units)" for s in top)
        return f"Top stores by units sold: {names}."
    if intent == Intent.SALES_TREND:
        n_points = len(data["points"])
        return f"Here's the {data['granularity']} sales trend ({n_points} data points)."
    if intent == Intent.PRODUCT_INFO:
        inv = data["inventory"]
        return f"{inv['product_id']}: {inv['total_inventory']:.0f} units in stock as of {inv['as_of_date']}."
    return "Here's what I found."


def _llm_phrase_response(llm_client, message: str, intent: Intent, data: dict, on_token=None) -> str | None:
    """Phrase verified `data` in words using the LLM.

    When `on_token` is supplied and the client supports it, the text arrives
    incrementally and each chunk is forwarded to the caller (live UI). The
    returned string is still the full text, so both paths behave identically.
    """
    if llm_client is None:
        return None
    try:
        payload = json.dumps({"user_question": message, "intent": intent.value, "verified_data": data})
        if on_token is not None and hasattr(llm_client, "stream_text"):
            chunks: list[str] = []
            for chunk in llm_client.stream_text(RESPONSE_GENERATION_SYSTEM_PROMPT, payload):
                chunks.append(chunk)
                on_token(chunk)
            return "".join(chunks).strip() or None
        return llm_client.complete_text(RESPONSE_GENERATION_SYSTEM_PROMPT, payload).strip()
    except LLMUnavailableError as e:
        log.warning("LLM unavailable for response phrasing, using template: %s", e)
        return None


# --- Context-Aware Chat Handler --------------------------------------------

# Progress stages reported to streaming callers (WebSocket). Deliberately
# coarse and mechanical: each stage maps to a real phase of the pipeline, so
# the live UI shows what the system is actually doing instead of a spinner.
STAGE_PARSING = "analyzing_request"
STAGE_QUERYING = "querying_database"
STAGE_PHRASING = "phrasing_response"


def _notify(callback, payload) -> None:
    """Invoke a progress callback, swallowing its errors.

    Progress reporting is a UI nicety: a broken callback must never turn a
    correct, verified answer into an error response.
    """
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:  # noqa: BLE001
        log.warning("Progress callback failed", exc_info=True)


class ChatSessionManager:
    """Manages chat sessions with conversation memory."""

    def __init__(self, llm_client=None):
        self.session_store = get_session_store()
        self.llm_client = llm_client
        self.context_manager = create_context_manager(llm_client)
        # Per-session context managers (in-memory, short-lived)
        self._context_managers: dict[str, ContextManager] = {}

    def _get_or_create_context_manager(self, session_id: str) -> ContextManager:
        """Get or create a ContextManager for a session."""
        if session_id not in self._context_managers:
            self._context_managers[session_id] = create_context_manager(self.llm_client)
            # Restore context from session store if available
            session = self.session_store.get_session(session_id)
            if session and session.turns:
                self._restore_context(session_id, session)
        return self._context_managers[session_id]

    def _restore_context(self, session_id: str, session: SessionData) -> None:
        """Restore entity tracker and topic stack from session history."""
        cm = self._context_managers[session_id]
        for turn in session.turns:
            entities = Entities(**turn.get("entities", {}))
            intent_str = turn.get("intent")
            intent = Intent(intent_str) if intent_str else None
            cm.entity_tracker.update(entities, turn.get("turn_index", 0))
            cm.topic_stack.update_current(turn.get("turn_index", 0), entities)
        cm.turn_count = len(session.turns)
        cm.summary = session.summary

    def _carryover_intent(self, session: SessionData, message: str) -> Optional[Intent]:
        """Reuse the previous product-scoped intent for a context-only follow-up.

        The rules layer matches keywords, so a pronoun/ordinal follow-up such
        as "Forecast it" or "How much at that store?" is either matched by its
        own keyword or comes back as UNKNOWN. This method covers the remaining
        case: when the message only makes sense with conversation context and
        the last classified turn was product-scoped, carry that intent forward
        rather than replying with a generic "I'm not sure what you're asking".
        """
        if not looks_like_follow_up(message):
            return None

        for turn in reversed(session.turns):
            raw_intent = turn.get("intent")
            if not raw_intent:
                continue
            try:
                previous = Intent(raw_intent)
            except ValueError:
                continue
            if previous == Intent.UNKNOWN:
                continue  # keep walking back to the last real intent
            # Last *classified* turn wasn't product-scoped (e.g. a ranking
            # question) -- carrying it forward would answer the wrong
            # question, so stop here.
            return previous if previous in PRODUCT_REQUIRED_INTENTS else None
        return None

    def _get_or_create_session(self, session_id: Optional[str], user_id: Optional[str] = None) -> SessionData:
        """Get existing session or create new one.

        If a session_id is requested but no session exists with it (fresh
        browser, expired Redis TTL, wiped localStorage) the id is ADOPTED
        for the new session rather than replaced with a random one. This is
        what makes refresh/resume stable: the frontend's stored id stays
        valid, and the conversation simply continues from an empty history.
        """
        if session_id:
            session = self.session_store.get_session(session_id)
            if session:
                return session
            log.warning("Session %s not found, creating new with requested id", session_id)
            return self.session_store.create_session(user_id, session_id=session_id)

        # Create new session
        return self.session_store.create_session(user_id)

    def handle_message(
        self,
        db: Session,
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        on_stage: Optional[Callable[[str], None]] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> ConversationChatResponse:
        """
        Main entry point for handling a chat message with conversation memory.

        `on_stage` / `on_token` are optional progress hooks used by the
        WebSocket streaming endpoint (app/routers/ws.py). They are pure
        observability: leaving them out (REST path, tests) changes nothing
        about the returned response.
        """
        # 1. Get or create session
        session = self._get_or_create_session(session_id, user_id)
        session_id = session.session_id

        # 2. Get context manager for this session
        cm = self._get_or_create_context_manager(session_id)

        # 3. Check for context commands
        cmd_response = cm.handle_command(message)
        if cmd_response is not None:
            # Save command turn
            self._save_turn(session_id, message, cmd_response, None, "command", {})
            return ConversationChatResponse(
                message=cmd_response,
                intent=None,
                entities={},
                parse_method="command",
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        # 4. Parse message with context injection
        # First, inject context into entities
        _notify(on_stage, STAGE_PARSING)
        intent, entities, method = parser.parse(message, llm_client=self.llm_client)

        # Inject conversation context (resolves pronouns, carries entities)
        entities = cm.inject_context(message, entities)

        # 4b. Context-only follow-ups ("How much at that store?") carry the
        # previous product-scoped intent forward instead of becoming UNKNOWN.
        if intent == Intent.UNKNOWN:
            carried_intent = self._carryover_intent(session, message)
            if carried_intent is not None:
                intent, method = carried_intent, "context"

        # 5. Handle HELP and UNKNOWN
        if intent == Intent.HELP:
            response_text = HELP_TEXT
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        if intent == Intent.UNKNOWN:
            response_text = "I'm not sure what you're asking. " + HELP_TEXT
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        # 6. Validate product entity against real database
        if intent in PRODUCT_REQUIRED_INTENTS and entities.product_id:
            if not product_repository.product_exists(db, entities.product_id):
                response_text = f"I couldn't find product '{entities.product_id}' in the current inventory data."
                self._save_turn(session_id, message, response_text, intent, method, {})
                return ConversationChatResponse(
                    message=response_text,
                    intent=intent,
                    entities=entities.model_dump(),
                    parse_method=method,
                    data=None,
                    session_id=session_id,
                    context=cm.get_context_for_llm(),
                )

        # 7. Execute tool
        tool = TOOLS.get(intent)
        if tool is None:
            response_text = HELP_TEXT
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        try:
            _notify(on_stage, STAGE_QUERYING)
            data = tool(db, entities)
        except MissingEntityError as e:
            response_text = str(e)
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )
        except NotFoundError as e:
            response_text = str(e)
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )
        except InvalidRequestError as e:
            response_text = str(e)
            self._save_turn(session_id, message, response_text, intent, method, {})
            return ConversationChatResponse(
                message=response_text,
                intent=intent,
                entities=entities.model_dump(),
                parse_method=method,
                data=None,
                session_id=session_id,
                context=cm.get_context_for_llm(),
            )

        # 8. Generate response (LLM phrasing or template)
        _notify(on_stage, STAGE_PHRASING)
        response_text = _llm_phrase_response(self.llm_client, message, intent, data, on_token=on_token)
        if response_text is None:
            response_text = _template_response(intent, entities, data)

        # 9. Update conversation context
        cm.process_turn(
            session_id=session_id,
            user_message=message,
            entities=entities,
            intent=intent,
            parse_method=method,
            response=response_text,
            data=data,
        )

        # 10. Save turn to session store
        self._save_turn(session_id, message, response_text, intent, method, data, entities)

        # 11. Return response with context
        return ConversationChatResponse(
            message=response_text,
            intent=intent,
            entities=entities.model_dump(),
            parse_method=method,
            data=data,
            session_id=session_id,
            context=cm.get_context_for_llm(),
        )

    def _save_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        intent: Optional[Intent],
        parse_method: str,
        data: dict,
        entities: Optional[Entities] = None,
    ) -> None:
        """Save a turn to the session store."""
        session = self.session_store.get_session(session_id)
        turn = {
            "turn_index": len(session.turns) if session else 0,
            "user_message": user_message,
            "assistant_response": assistant_response,
            "intent": intent.value if intent else None,
            "entities": entities.model_dump() if entities else {},
            "parse_method": parse_method,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.session_store.add_turn(session_id, turn)

    def get_session_info(self, session_id: str) -> Optional[dict]:
        """Get session info for API."""
        session = self.session_store.get_session(session_id)
        if not session:
            return None
        cm = self._context_managers.get(session_id)
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "turn_count": len(session.turns),
            "summary": session.summary,
            "preview": _preview_turns(session.turns),
            "active_entities": cm.entity_tracker.get_active_entities() if cm else {},
            "current_topic": cm.topic_stack.peek().name if cm and cm.topic_stack.peek() else None,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        """List sessions for a user."""
        sessions = self.session_store.list_sessions(user_id, limit)
        result = []
        for session in sessions:
            cm = self._context_managers.get(session.session_id)
            result.append({
                "session_id": session.session_id,
                "user_id": session.user_id,
                "turn_count": len(session.turns),
                "summary": session.summary,
                "preview": _preview_turns(session.turns),
                "active_entities": cm.entity_tracker.get_active_entities() if cm else {},
                "current_topic": cm.topic_stack.peek().name if cm and cm.topic_stack.peek() else None,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            })
        return result

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        self.session_store.delete_session(session_id)
        self._context_managers.pop(session_id, None)
        return True

    def get_session_history(self, session_id: str) -> Optional[dict]:
        """Get full session history."""
        session = self.session_store.get_session(session_id)
        if not session:
            return None
        cm = self._context_managers.get(session_id)
        return {
            "session_id": session.session_id,
            "turns": session.turns,
            "summary": session.summary,
            "context": cm.get_context_for_llm() if cm else {},
        }


PREVIEW_MAX_LENGTH = 80


def _preview_turns(turns: list[dict]) -> Optional[str]:
    """First user message, truncated -- a cheap sidebar label."""
    for turn in turns:
        text = (turn.get("user_message") or "").strip()
        if text:
            return text if len(text) <= PREVIEW_MAX_LENGTH else text[:PREVIEW_MAX_LENGTH] + "…"
    return None


# --- Global instance (for backward compatibility) ---------------------------

_chat_session_manager: Optional[ChatSessionManager] = None


def get_chat_session_manager(llm_client=None) -> ChatSessionManager:
    """Get or create the global chat session manager.

    A supplied `llm_client` wins even when a manager already exists without
    one (e.g. an earlier stateless call in the same process created the
    default manager). Otherwise `handle_chat_message(llm_client=...)` would
    silently ignore the caller's client -- both a test-ordering hazard and a
    real API footgun.
    """
    global _chat_session_manager
    if _chat_session_manager is None or (llm_client is not None and _chat_session_manager.llm_client is None):
        _chat_session_manager = ChatSessionManager(llm_client)
    return _chat_session_manager


def set_chat_session_manager(manager: ChatSessionManager) -> None:
    """Override the global chat session manager (for testing)."""
    global _chat_session_manager
    _chat_session_manager = manager


# --- Backward-compatible entry point ----------------------------------------

def handle_chat_message(
    db: Session,
    message: str,
    llm_client=None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> ChatResponse:
    """
    Backward-compatible entry point.
    Returns the original ChatResponse schema (without session_id/context).
    """
    manager = get_chat_session_manager(llm_client)
    response = manager.handle_message(db, message, session_id, user_id)

    # Convert to legacy ChatResponse
    return ChatResponse(
        message=response.message,
        intent=response.intent,
        entities=Entities(**response.entities) if response.entities else Entities(),
        parse_method=response.parse_method,
        data=response.data,
    )