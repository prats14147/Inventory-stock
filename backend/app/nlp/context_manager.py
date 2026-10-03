"""
backend/app/nlp/context_manager.py

Conversation context management:
- EntityTracker: resolves pronouns ("it", "that product") to actual entities
- TopicStack: manages conversation topics, supports push/pop/"back to X"
- Summarizer: LLM-based conversation summarization for long sessions
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.nlp.entities import Entities
from app.nlp.intent import Intent
from app.nlp.llm_client import LLMUnavailableError

log = logging.getLogger("nlp.context_manager")


# --- Constants --------------------------------------------------------------

# Pronouns and references that indicate entity carryover
PRONOUN_PATTERNS = {
    "product": [
        r"\bit\b",
        r"\bthat product\b",
        r"\bthe product\b",
        r"\bthis product\b",
        r"\bthe first one\b",
        r"\bthe second one\b",
        r"\bthe (?:previous|last) product\b",
    ],
    "store": [
        r"\bthat store\b",
        r"\bthe store\b",
        r"\bthis store\b",
        r"\bthe (?:previous|last) store\b",
        r"\bthere\b",
    ],
    "category": [
        r"\bthat category\b",
        r"\bthe category\b",
        r"\bthis category\b",
    ],
}

# Explicit reference patterns
REFERENCE_PATTERNS = {
    "product": re.compile(r"\b(P0*\d{1,4})\b", re.IGNORECASE),
    "store": re.compile(r"\b(S0*\d{1,3})\b", re.IGNORECASE),
}

# Ordinal references ("the first one", "second one") select a specific
# position in mention history rather than the most recent mention.
ORDINAL_WORDS = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4}
ORDINAL_PATTERN = re.compile(
    r"\b(?:the\s+)?(first|second|third|fourth|fifth)(?:\s+one)?\b", re.IGNORECASE
)

# Topic transition signals
TOPIC_PUSH_SIGNALS = [
    "now check",
    "now look at",
    "what about",
    "how about",
    "also check",
    "also look at",
    "switch to",
    "move to",
]
TOPIC_POP_SIGNALS = [
    "back to",
    "return to",
    "go back to",
    "previous topic",
]


# --- Data Classes -----------------------------------------------------------

@dataclass
class EntityReference:
    """A resolved entity with metadata."""
    entity_type: str  # "product", "store", "category"
    value: str
    confidence: float = 1.0
    source_turn: int = -1
    mention_text: str = ""


@dataclass
class Topic:
    """A conversation topic with associated entities."""
    name: str
    intent: Optional[Intent] = None
    primary_entity: Optional[EntityReference] = None
    related_entities: list[EntityReference] = field(default_factory=list)
    turn_range: tuple[int, int] = (0, 0)  # (start_turn, end_turn)
    active: bool = True


@dataclass
class ConversationContext:
    """Full conversation context for a session."""
    session_id: str
    turns: list[dict] = field(default_factory=list)
    entity_tracker: "EntityTracker" = field(default_factory=lambda: EntityTracker())
    topic_stack: "TopicStack" = field(default_factory=lambda: TopicStack())
    summary: Optional[str] = None
    turn_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


# --- Entity Tracker ---------------------------------------------------------

class EntityTracker:
    """
    Tracks and resolves entities across conversation turns.
    Handles pronoun resolution ("it" -> P0001) and explicit references.
    """

    def __init__(self):
        self.product_history: list[EntityReference] = []
        self.store_history: list[EntityReference] = []
        self.category_history: list[EntityReference] = []
        self._current_turn = 0

    def update(self, entities: Entities, turn_index: int) -> None:
        """Record new entities from current turn."""
        if entities.product_id:
            self.product_history.append(EntityReference(
                entity_type="product",
                value=entities.product_id,
                source_turn=turn_index,
                mention_text=entities.product_id,
            ))
        if entities.store_id:
            self.store_history.append(EntityReference(
                entity_type="store",
                value=entities.store_id,
                source_turn=turn_index,
                mention_text=entities.store_id,
            ))
        if entities.category:
            self.category_history.append(EntityReference(
                entity_type="category",
                value=entities.category,
                source_turn=turn_index,
                mention_text=entities.category,
            ))
        self._current_turn = turn_index

    def resolve(self, message: str, current_entities: Entities) -> Entities:
        """
        Resolve pronouns and implicit references in the message using context.
        Returns enriched Entities with carried-over values.
        """
        resolved = current_entities.model_copy()
        lower = message.lower()

        # Check for explicit references first (highest confidence)
        for entity_type, pattern in REFERENCE_PATTERNS.items():
            match = pattern.search(message)
            if match:
                value = match.group(1).upper()
                # Normalize format
                if entity_type == "product":
                    value = f"P{int(value[1:]):04d}"
                    resolved.product_id = value
                elif entity_type == "store":
                    value = f"S{int(value[1:]):03d}"
                    resolved.store_id = value
                continue  # Explicit reference wins

        # Ordinal references ("the first one", "the second one") index into
        # mention history (deduplicated, in first-mention order).
        if not resolved.product_id:
            ordinal = ORDINAL_PATTERN.search(message)
            if ordinal:
                index = ORDINAL_WORDS[ordinal.group(1).lower()]
                seen: list[str] = []
                for ref in self.product_history:
                    if ref.value not in seen:
                        seen.append(ref.value)
                if index < len(seen):
                    resolved.product_id = seen[index]

        # Check for pronoun/implicit references
        if not resolved.product_id and self._has_pronoun(lower, "product"):
            resolved.product_id = self._get_most_recent_product()

        if not resolved.store_id and self._has_pronoun(lower, "store"):
            resolved.store_id = self._get_most_recent_store()

        if not resolved.category and self._has_pronoun(lower, "category"):
            resolved.category = self._get_most_recent_category()

        return resolved

    def _has_pronoun(self, message: str, entity_type: str) -> bool:
        patterns = PRONOUN_PATTERNS.get(entity_type, [])
        return any(re.search(p, message) for p in patterns)

    def _get_most_recent_product(self) -> Optional[str]:
        if self.product_history:
            return self.product_history[-1].value
        return None

    def _get_most_recent_store(self) -> Optional[str]:
        if self.store_history:
            return self.store_history[-1].value
        return None

    def _get_most_recent_category(self) -> Optional[str]:
        if self.category_history:
            return self.category_history[-1].value
        return None

    def get_active_entities(self) -> dict[str, Optional[str]]:
        """Get currently active entities for context injection."""
        return {
            "product_id": self._get_most_recent_product(),
            "store_id": self._get_most_recent_store(),
            "category": self._get_most_recent_category(),
        }

    def forget_entity(self, entity_type: str, value: str) -> None:
        """Remove an entity from history (e.g., user says 'forget P0001')."""
        history = getattr(self, f"{entity_type}_history", [])
        setattr(self, f"{entity_type}_history", [e for e in history if e.value != value])

    def clear(self) -> None:
        """Clear all entity history."""
        self.product_history.clear()
        self.store_history.clear()
        self.category_history.clear()
        self._current_turn = 0


# --- Topic Stack ------------------------------------------------------------

class TopicStack:
    """
    Manages conversation topics as a stack.
    Supports push (new topic), pop (return to previous), and peek.
    """

    def __init__(self, max_topics: int = 10):
        self.topics: list[Topic] = []
        self.max_topics = max_topics

    def push(self, name: str, intent: Optional[Intent] = None,
             primary_entity: Optional[EntityReference] = None,
             turn_index: int = 0) -> Topic:
        """Start a new topic."""
        topic = Topic(
            name=name,
            intent=intent,
            primary_entity=primary_entity,
            turn_range=(turn_index, turn_index),
        )
        self.topics.append(topic)
        if len(self.topics) > self.max_topics:
            self.topics.pop(0)
        return topic

    def pop(self) -> Optional[Topic]:
        """Return to previous topic."""
        if len(self.topics) <= 1:
            return None
        return self.topics.pop()

    def peek(self) -> Optional[Topic]:
        """Get current topic without removing."""
        return self.topics[-1] if self.topics else None

    def get_previous(self) -> Optional[Topic]:
        """Get the topic before current."""
        return self.topics[-2] if len(self.topics) >= 2 else None

    def find_topic(self, name: str) -> Optional[Topic]:
        """Find a topic by name (case-insensitive, partial match)."""
        lower = name.lower()
        for topic in reversed(self.topics):
            if lower in topic.name.lower():
                return topic
        return None

    def switch_to(self, name: str, turn_index: int) -> Optional[Topic]:
        """Switch to a named topic, making it current."""
        topic = self.find_topic(name)
        if topic:
            # Move to top
            self.topics.remove(topic)
            self.topics.append(topic)
            topic.active = True
            topic.turn_range = (topic.turn_range[0], turn_index)
            return topic
        return None

    def update_current(self, turn_index: int, entities: Entities = None) -> None:
        """Extend current topic's turn range and optionally add entities."""
        if self.topics:
            current = self.topics[-1]
            current.turn_range = (current.turn_range[0], turn_index)
            if entities:
                if entities.product_id and not current.primary_entity:
                    current.primary_entity = EntityReference(
                        entity_type="product", value=entities.product_id, source_turn=turn_index
                    )
                if entities.store_id:
                    current.related_entities.append(EntityReference(
                        entity_type="store", value=entities.store_id, source_turn=turn_index
                    ))
                if entities.category:
                    current.related_entities.append(EntityReference(
                        entity_type="category", value=entities.category, source_turn=turn_index
                    ))

    def detect_transition(self, message: str) -> Optional[str]:
        """Detect if message signals a topic transition. Returns transition type."""
        lower = message.lower()
        for signal in TOPIC_PUSH_SIGNALS:
            if signal in lower:
                return "push"
        for signal in TOPIC_POP_SIGNALS:
            if signal in lower:
                return "pop"
        return None


# --- Summarizer -------------------------------------------------------------

SUMMARIZATION_PROMPT = """Summarize the following conversation between a user and an inventory intelligence assistant.
Focus on: products discussed, key questions asked, important findings, and any pending actions.
Keep it concise (3-5 sentences). Do not include greetings or meta-commentary.

Conversation:
{conversation}

Summary:"""

# Number of turns after which the summarizer should kick in.
SUMMARIZATION_THRESHOLD = 6


class Summarizer:
    """LLM-based conversation summarization for long sessions."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def should_summarize(self, turn_count: int, threshold: int = SUMMARIZATION_THRESHOLD) -> bool:
        return turn_count >= threshold

    def summarize(self, turns: list[dict]) -> Optional[str]:
        """Generate a summary of the conversation so far."""
        if not self.llm_client:
            return self._fallback_summary(turns)

        # Format conversation for prompt
        conversation_lines = []
        for i, turn in enumerate(turns):
            user_msg = turn.get("user_message", "")
            asst_msg = turn.get("assistant_response", "")
            conversation_lines.append(f"User: {user_msg}")
            if asst_msg:
                conversation_lines.append(f"Assistant: {asst_msg}")

        conversation_text = "\n".join(conversation_lines)

        try:
            summary = self.llm_client.complete_text(
                SUMMARIZATION_PROMPT.format(conversation=conversation_text),
                max_tokens=200,
                temperature=0.3,
            )
            return summary.strip()
        except LLMUnavailableError as e:
            log.warning("LLM unavailable for summarization: %s", e)
            return self._fallback_summary(turns)
        except Exception as e:
            log.error("Summarization failed: %s", e)
            return self._fallback_summary(turns)

    def _fallback_summary(self, turns: list[dict]) -> str:
        """Deterministic fallback summary without LLM."""
        products = set()
        intents = set()
        for turn in turns:
            entities = turn.get("entities", {})
            if entities.get("product_id"):
                products.add(entities["product_id"])
            if turn.get("intent"):
                intents.add(turn["intent"])

        parts = []
        if products:
            parts.append(f"Discussed products: {', '.join(sorted(products))}")
        if intents:
            parts.append(f"Topics: {', '.join(sorted(intents))}")
        parts.append(f"Total turns: {len(turns)}")

        return ". ".join(parts) + "."


# --- Context Manager (Main Entry Point) ------------------------------------

class ContextManager:
    """
    Main context management orchestrator.
    Combines entity tracking, topic management, and summarization.
    """

    def __init__(self, llm_client=None, summarization_threshold: int = SUMMARIZATION_THRESHOLD):
        self.entity_tracker = EntityTracker()
        self.topic_stack = TopicStack()
        self.summarizer = Summarizer(llm_client)
        self.summarization_threshold = summarization_threshold
        self.summary: Optional[str] = None
        self.turn_count = 0

    def process_turn(self, session_id: str, user_message: str,
                     entities: Entities, intent: Intent,
                     parse_method: str, response: str,
                     data: Optional[dict] = None) -> "ContextManager":
        """
        Process a completed turn, updating all context components.
        Returns self so multi-turn flows can chain calls
        (``cm.process_turn(...).process_turn(...)``).
        """
        turn_index = self.turn_count

        # 1. Resolve entities using context (before updating with new entities)
        resolved_entities = self.entity_tracker.resolve(user_message, entities)

        # 2. Update entity tracker with resolved entities
        self.entity_tracker.update(resolved_entities, turn_index)

        # 3. Detect and handle topic transitions
        transition = self.topic_stack.detect_transition(user_message)
        if transition == "push":
            # Extract topic name from message
            topic_name = self._extract_topic_name(user_message)
            self.topic_stack.push(topic_name, intent, turn_index=turn_index)
        elif transition == "pop":
            self.topic_stack.pop()

        # 4. Update current topic
        self.topic_stack.update_current(turn_index, resolved_entities)

        # 5. Record turn
        turn = {
            "turn_index": turn_index,
            "user_message": user_message,
            "assistant_response": response,
            "intent": intent.value if intent else None,
            "entities": resolved_entities.model_dump(),
            "parse_method": parse_method,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        # 6. Check if summarization needed
        self.turn_count += 1
        if self.summarizer.should_summarize(self.turn_count) and not self.summary:
            # Get all turns from session (would need session store access)
            # For now, we'll summarize when explicitly requested
            pass

        # Snapshot of this turn (kept for debugging/introspection).
        ConversationContext(
            session_id=session_id,
            turns=[turn],  # Just current turn; full history in session store
            entity_tracker=self.entity_tracker,
            topic_stack=self.topic_stack,
            summary=self.summary,
            turn_count=self.turn_count,
        )
        return self

    def get_context_for_llm(self) -> dict[str, Any]:
        """Get context formatted for LLM prompt injection."""
        active_entities = self.entity_tracker.get_active_entities()
        current_topic = self.topic_stack.peek()

        return {
            "active_entities": active_entities,
            "current_topic": current_topic.name if current_topic else None,
            "topic_intent": current_topic.intent.value if current_topic and current_topic.intent else None,
            "summary": self.summary,
            "turn_count": self.turn_count,
        }

    def inject_context(self, message: str, entities: Entities) -> Entities:
        """Inject conversation context into current message/entities."""
        return self.entity_tracker.resolve(message, entities)

    def handle_command(self, command: str) -> Optional[str]:
        """Handle explicit context commands. Returns response message if handled."""
        lower = command.lower().strip()

        if lower in ("reset", "clear context", "start over"):
            self.entity_tracker.clear()
            self.topic_stack.topics.clear()
            self.summary = None
            self.turn_count = 0
            return "Conversation context cleared. Starting fresh."

        if lower == "show history":
            # Return recent turns summary
            return f"Conversation: {self.turn_count} turns. Active product: {self.entity_tracker.get_active_entities().get('product_id', 'none')}."

        if lower.startswith("forget "):
            # forget P0001
            parts = lower.split()
            if len(parts) >= 2:
                entity_ref = parts[1].upper()
                if entity_ref.startswith("P"):
                    self.entity_tracker.forget_entity("product", entity_ref)
                    return f"Forgot product {entity_ref}."
                elif entity_ref.startswith("S"):
                    self.entity_tracker.forget_entity("store", entity_ref)
                    return f"Forgot store {entity_ref}."

        if lower.startswith("back to "):
            topic_name = lower[8:].strip()
            topic = self.topic_stack.switch_to(topic_name, self.turn_count)
            if topic:
                return f"Switched back to topic: {topic.name}"
            return f"Could not find topic: {topic_name}"

        return None

    def _extract_topic_name(self, message: str) -> str:
        """Extract a topic name from a transition message."""
        # Remove transition signals
        clean = message.lower()
        for signal in TOPIC_PUSH_SIGNALS:
            clean = clean.replace(signal, "")
        # Take first meaningful phrase
        words = clean.strip().split()
        if words:
            return " ".join(words[:5]).capitalize()
        return "New topic"


# --- Helper function for easy integration ----------------------------------

def create_context_manager(llm_client=None) -> ContextManager:
    """Factory function to create a ContextManager."""
    return ContextManager(llm_client=llm_client)