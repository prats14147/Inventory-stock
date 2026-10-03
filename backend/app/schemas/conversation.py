"""
backend/app/schemas/conversation.py

Pydantic schemas for conversation/session API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- Request/Response Schemas -----------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # If None, create new session
    user_id: Optional[str] = None  # Optional user identifier


class ChatResponse(BaseModel):
    message: str
    intent: Optional[str] = None
    entities: dict[str, Any] = {}
    parse_method: str = "rules"
    data: Optional[dict[str, Any]] = None
    session_id: str
    context: Optional[dict[str, Any]] = None  # Active entities, topic, etc.


class SessionCreateRequest(BaseModel):
    user_id: Optional[str] = None


class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: datetime


class SessionInfo(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    turn_count: int
    summary: Optional[str] = None
    # First user message, truncated server-side -- lets the sidebar show a
    # readable label without fetching every session's full history.
    preview: Optional[str] = None
    active_entities: dict[str, Optional[str]] = {}
    current_topic: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]
    total: int


class TurnInfo(BaseModel):
    turn_index: int
    user_message: str
    assistant_response: Optional[str] = None
    intent: Optional[str] = None
    entities: dict[str, Any] = {}
    parse_method: Optional[str] = None
    data: dict[str, Any] = {}
    timestamp: datetime


class SessionHistoryResponse(BaseModel):
    session_id: str
    turns: list[TurnInfo]
    summary: Optional[str] = None


class ContextCommandRequest(BaseModel):
    session_id: str
    command: str  # "reset", "show history", "forget P0001", "back to <topic>"


class ContextCommandResponse(BaseModel):
    session_id: str
    response: str
    context: Optional[dict[str, Any]] = None


# --- Internal/DB Schemas ----------------------------------------------------

class ConversationTurnBase(BaseModel):
    turn_index: int
    user_message: str
    assistant_response: Optional[str] = None
    intent: Optional[str] = None
    entities: dict[str, Any] = {}
    parse_method: Optional[str] = None
    data: dict[str, Any] = {}
    timestamp: datetime


class ConversationSessionBase(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    turns: list[ConversationTurnBase] = []
    summary: Optional[str] = None
    metadata: dict[str, Any] = {}


# --- WebSocket Schemas (for real-time chat) ---------------------------------

class WSChatMessage(BaseModel):
    type: str = "chat"
    message: str
    session_id: Optional[str] = None


class WSChatResponse(BaseModel):
    type: str = "chat_response"
    message: str
    intent: Optional[str] = None
    entities: dict[str, Any] = {}
    parse_method: str = "rules"
    data: Optional[dict[str, Any]] = None
    session_id: str
    context: Optional[dict[str, Any]] = None


class WSError(BaseModel):
    type: str = "error"
    code: str
    message: str
    session_id: Optional[str] = None


class WSSessionCreated(BaseModel):
    type: str = "session_created"
    session_id: str


# --- Export/Import Schemas --------------------------------------------------

class ExportSessionRequest(BaseModel):
    session_id: str
    format: str = "json"  # "json" or "txt"


class ExportSessionResponse(BaseModel):
    session_id: str
    format: str
    content: str
    exported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImportSessionRequest(BaseModel):
    content: str
    format: str = "json"
    user_id: Optional[str] = None


class ImportSessionResponse(BaseModel):
    session_id: str
    imported_turns: int