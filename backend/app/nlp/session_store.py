"""
backend/app/nlp/session_store.py

Conversation session persistence with Redis (fast) + Postgres (durable) backends.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

from app.database import Base

log = logging.getLogger("nlp.session_store")


def _utcnow_naive() -> datetime:
    # Naive UTC, matching the DateTime columns and the rest of the codebase
    # (live.py, simulator_service.py) -- avoids datetime.utcnow() deprecation
    # warnings without writing tz-aware values into naive columns.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Configuration ----------------------------------------------------------

DEFAULT_TTL_SECONDS = 30 * 60  # 30 minutes
MAX_TURNS_PER_SESSION = 50
SUMMARIZATION_THRESHOLD = 8  # summarize after this many turns


# --- Conversation tables (durable history, Alembic-owned) -------------------
#
# These models live on app.database.Base -- the SAME metadata Alembic's
# env.py imports -- so `alembic revision --autogenerate` sees them and no
# second, shadow metadata can drift out of sync. The tables themselves are
# created/altered only by migrations
# (see d4e5f6a7b8c9_add_conversation_tables.py); the store never calls
# create_all().


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)
    updated_at = Column(DateTime, default=_utcnow_naive, onupdate=_utcnow_naive, nullable=False)
    metadata_json = Column(Text, default="{}")  # JSON string for flexible metadata
    # Cached rolling summary of the conversation (Phase 11). Written when
    # the ContextManager's summarizer fires; nullable because short
    # sessions never produce one.
    summary = Column(Text, nullable=True)


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id = Column(String(36), primary_key=True)  # UUID
    session_id = Column(String(36), ForeignKey("conversation_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    # Integer, not string: lexicographic ("10" < "2") ordering silently
    # scrambles history display and context replay at 10+ turns.
    turn_index = Column(Integer, nullable=False)
    user_message = Column(Text, nullable=False)
    assistant_response = Column(Text, nullable=True)
    intent = Column(String(50), nullable=True)
    entities_json = Column(Text, default="{}")
    parse_method = Column(String(20), nullable=True)
    data_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- Session Store Interface ------------------------------------------------

@dataclass
class SessionData:
    session_id: str
    user_id: Optional[str] = None
    turns: list[dict] = field(default_factory=list)
    summary: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class SessionStore:
    """Abstract base for session storage."""

    def create_session(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> SessionData:
        raise NotImplementedError

    def get_session(self, session_id: str) -> Optional[SessionData]:
        raise NotImplementedError

    def save_session(self, session: SessionData) -> None:
        raise NotImplementedError

    def delete_session(self, session_id: str) -> None:
        raise NotImplementedError

    def add_turn(self, session_id: str, turn: dict) -> None:
        raise NotImplementedError

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 100) -> list[SessionData]:
        raise NotImplementedError


# --- Redis Implementation ---------------------------------------------------

class RedisSessionStore(SessionStore):
    """Redis-backed session store with TTL."""

    def __init__(
        self,
        url: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        key_prefix: str = "inventoryai:session:",
    ):
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix
        self._client = None
        self._url = url or get_settings().redis_url
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        try:
            import redis
            self._client = redis.from_url(
                self._url,
                decode_responses=True,
                socket_timeout=1.0,
                socket_connect_timeout=1.0,
            )
            self._client.ping()
            self._available = True
            log.info("Redis session store connected: %s", self._url)
        except Exception as e:
            log.warning("Redis unavailable, session store will use memory fallback: %s", e)
            self._available = False
            self._memory_store: dict[str, SessionData] = {}

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}{session_id}"

    def _serialize(self, session: SessionData) -> str:
        return json.dumps({
            "session_id": session.session_id,
            "user_id": session.user_id,
            "turns": session.turns,
            "summary": session.summary,
            "metadata": session.metadata,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        })

    def _deserialize(self, data: str) -> SessionData:
        d = json.loads(data)
        return SessionData(**d)

    def create_session(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> SessionData:
        session_id = session_id or str(uuid.uuid4())
        session = SessionData(session_id=session_id, user_id=user_id)
        self.save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[SessionData]:
        if not self._available:
            return self._memory_store.get(session_id)

        data = self._client.get(self._key(session_id))
        if data is None:
            return None
        session = self._deserialize(data)
        # Extend TTL on access
        self._client.expire(self._key(session_id), self.ttl_seconds)
        return session

    def save_session(self, session: SessionData) -> None:
        session.updated_at = time.time()
        data = self._serialize(session)
        if not self._available:
            self._memory_store[session.session_id] = session
            return
        self._client.setex(self._key(session.session_id), self.ttl_seconds, data)

    def delete_session(self, session_id: str) -> None:
        if not self._available:
            self._memory_store.pop(session_id, None)
            return
        self._client.delete(self._key(session_id))

    def add_turn(self, session_id: str, turn: dict) -> None:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        session.turns.append(turn)
        # Trim if too many turns
        if len(session.turns) > MAX_TURNS_PER_SESSION:
            session.turns = session.turns[-MAX_TURNS_PER_SESSION:]
        self.save_session(session)

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 100) -> list[SessionData]:
        if not self._available:
            sessions = list(self._memory_store.values())
            if user_id:
                sessions = [s for s in sessions if s.user_id == user_id]
            return sessions[:limit]

        # Redis doesn't support efficient listing by user_id without secondary index
        # For now, return empty list - use Postgres for listing
        return []


# --- Postgres Implementation (durable history) ------------------------------

class PostgresSessionStore(SessionStore):
    """Postgres-backed session store for durable conversation history."""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL required for PostgresSessionStore")
        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=15,
            pool_recycle=300,
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        # NOTE: no create_all() here. The conversation_* tables are owned by
        # Alembic (see d4e5f6a7b8c9_add_conversation_tables.py); creating them
        # implicitly on store construction is what let the schema drift
        # undocumented (VARCHAR turn_index, missing FK, missing defaults).

    def _session_to_data(self, session: ConversationSession, turns: list[ConversationTurn]) -> SessionData:
        ordered = sorted(turns, key=lambda x: (x.turn_index if isinstance(x.turn_index, int) else int(x.turn_index)))
        return SessionData(
            session_id=session.id,
            user_id=session.user_id,
            turns=[
                {
                    "turn_index": int(t.turn_index),
                    "user_message": t.user_message,
                    "assistant_response": t.assistant_response,
                    "intent": t.intent,
                    "entities": json.loads(t.entities_json or "{}"),
                    "parse_method": t.parse_method,
                    "data": self._safe_json(t.data_json, what="data_json", session_id=session.id),
                    "created_at": t.created_at.isoformat(),
                }
                for t in ordered
            ],
            summary=session.summary,  # rolling summary written by the ContextManager, if any
            metadata=json.loads(session.metadata_json or "{}"),
            created_at=session.created_at.timestamp(),
            updated_at=session.updated_at.timestamp(),
        )

    @staticmethod
    def _safe_json(raw: Optional[str], what: str, session_id: str) -> dict:
        """Parse a JSON text column defensively: corrupt rows degrade to {}.

        data_json feeds the frontend's detail cards, so one bad row must not
        500 the whole history endpoint.
        """
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log.warning("Unparseable %s in session %s, returning {}", what, session_id)
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def create_session(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> SessionData:
        session_id = session_id or str(uuid.uuid4())
        db = self.SessionLocal()
        try:
            session = ConversationSession(id=session_id, user_id=user_id)
            db.add(session)
            db.commit()
            return SessionData(session_id=session_id, user_id=user_id)
        finally:
            db.close()

    def get_session(self, session_id: str) -> Optional[SessionData]:
        db = self.SessionLocal()
        try:
            session = db.query(ConversationSession).filter(ConversationSession.id == session_id).first()
            if not session:
                return None
            turns = db.query(ConversationTurn).filter(ConversationTurn.session_id == session_id).all()
            return self._session_to_data(session, turns)
        finally:
            db.close()

    def save_session(self, session: SessionData) -> None:
        # Postgres is the source of truth for history; individual turns are saved via add_turn.
        # This method upserts session-level metadata AND the cached rolling
        # summary (the summary lives on the session row so history reads get
        # it without a second query).
        db = self.SessionLocal()
        try:
            db_session = db.query(ConversationSession).filter(ConversationSession.id == session.session_id).first()
            if db_session:
                db_session.metadata_json = json.dumps(session.metadata)
                db_session.summary = session.summary
                db.commit()
        finally:
            db.close()

    def delete_session(self, session_id: str) -> None:
        db = self.SessionLocal()
        try:
            db.query(ConversationTurn).filter(ConversationTurn.session_id == session_id).delete()
            db.query(ConversationSession).filter(ConversationSession.id == session_id).delete()
            db.commit()
        finally:
            db.close()

    def add_turn(self, session_id: str, turn: dict) -> None:
        db = self.SessionLocal()
        try:
            # COUNT(*) avoids fetching the whole row just to derive the next
            # index, and keeps the index numeric (see turn_index comment).
            turn_index = db.query(ConversationTurn).filter(
                ConversationTurn.session_id == session_id
            ).count()

            db_turn = ConversationTurn(
                id=str(uuid.uuid4()),
                session_id=session_id,
                turn_index=turn_index,
                user_message=turn.get("user_message", ""),
                assistant_response=turn.get("assistant_response"),
                intent=turn.get("intent"),
                entities_json=json.dumps(turn.get("entities", {})),
                parse_method=turn.get("parse_method"),
                data_json=json.dumps(turn.get("data", {})),
            )
            db.add(db_turn)
            db.commit()
        finally:
            db.close()

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 100) -> list[SessionData]:
        db = self.SessionLocal()
        try:
            query = db.query(ConversationSession)
            if user_id:
                query = query.filter(ConversationSession.user_id == user_id)
            sessions = query.order_by(ConversationSession.updated_at.desc()).limit(limit).all()

            result = []
            for session in sessions:
                turns = db.query(ConversationTurn).filter(ConversationTurn.session_id == session.id).all()
                result.append(self._session_to_data(session, turns))
            return result
        finally:
            db.close()


# --- Hybrid Store (Redis for active sessions, Postgres for history) --------

class HybridSessionStore(SessionStore):
    """
    Uses Redis for active sessions (fast reads/writes, TTL) and Postgres
    for durable history. Falls back to in-memory if neither is available.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        postgres_url: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        settings = get_settings()
        self.redis_store = RedisSessionStore(redis_url or settings.redis_url, ttl_seconds)
        self.postgres_store = None
        if postgres_url or settings.database_url:
            try:
                self.postgres_store = PostgresSessionStore(postgres_url or settings.database_url)
            except Exception as e:
                log.warning("Postgres session store unavailable: %s", e)

    def create_session(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> SessionData:
        # One shared id across BOTH backends: the Postgres row must carry the
        # same id as the Redis entry, otherwise a restart (Redis TTL expiry)
        # resurrects a *different* session from Postgres and the earlier
        # turns are silently orphaned.
        session = self.redis_store.create_session(user_id, session_id=session_id)
        if self.postgres_store:
            self.postgres_store.create_session(user_id, session_id=session.session_id)
        return session

    def get_session(self, session_id: str) -> Optional[SessionData]:
        # Try Redis first (fast)
        session = self.redis_store.get_session(session_id)
        if session:
            return session
        # Fall back to Postgres (durable)
        if self.postgres_store:
            session = self.postgres_store.get_session(session_id)
            if session:
                # Redis may have expired an active-session key while the
                # durable Postgres row still exists. Rehydrate the fast store
                # before returning: add_turn() writes to Redis first and
                # otherwise rejects this valid, recovered session.
                self.redis_store.save_session(session)
            return session
        return None

    def save_session(self, session: SessionData) -> None:
        self.redis_store.save_session(session)
        if self.postgres_store:
            self.postgres_store.save_session(session)

    def delete_session(self, session_id: str) -> None:
        self.redis_store.delete_session(session_id)
        if self.postgres_store:
            self.postgres_store.delete_session(session_id)

    def add_turn(self, session_id: str, turn: dict) -> None:
        self.redis_store.add_turn(session_id, turn)
        if self.postgres_store:
            self.postgres_store.add_turn(session_id, turn)

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 100) -> list[SessionData]:
        if self.postgres_store:
            return self.postgres_store.list_sessions(user_id, limit)
        return self.redis_store.list_sessions(user_id, limit)


# --- Factory ----------------------------------------------------------------

_session_store_instance: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Get or create the global session store instance."""
    global _session_store_instance
    if _session_store_instance is None:
        _session_store_instance = HybridSessionStore()
    return _session_store_instance


def set_session_store(store: SessionStore) -> None:
    """Override the global session store (for testing)."""
    global _session_store_instance
    _session_store_instance = store
