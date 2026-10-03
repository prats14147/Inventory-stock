"""
backend/app/nlp/__init__

NLP package exports.
"""

from app.nlp.entities import Entities
from app.nlp.intent import Intent, PRODUCT_REQUIRED_INTENTS
from app.nlp.parser import parse
from app.nlp.rules import rule_based_parse, classify_intent, extract_entities
from app.nlp.session_store import (
    SessionStore,
    RedisSessionStore,
    PostgresSessionStore,
    HybridSessionStore,
    SessionData,
    get_session_store,
    set_session_store,
)
from app.nlp.context_manager import (
    ContextManager,
    EntityTracker,
    TopicStack,
    Summarizer,
    ConversationContext,
    create_context_manager,
)

__all__ = [
    # Core
    "Entities",
    "Intent",
    "PRODUCT_REQUIRED_INTENTS",
    "parse",
    "rule_based_parse",
    "classify_intent",
    "extract_entities",
    # Session & Context
    "SessionStore",
    "RedisSessionStore",
    "PostgresSessionStore",
    "HybridSessionStore",
    "SessionData",
    "get_session_store",
    "set_session_store",
    "ContextManager",
    "EntityTracker",
    "TopicStack",
    "Summarizer",
    "ConversationContext",
    "create_context_manager",
]