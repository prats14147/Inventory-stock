"""backend/app/routers/chat.py"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.nlp.llm_client import build_llm_client
from app.schemas.conversation import (
    ChatRequest,
    ChatResponse as ConversationChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionInfo,
    SessionListResponse,
    SessionHistoryResponse,
    TurnInfo,
    ContextCommandRequest,
    ContextCommandResponse,
)
from app.services import chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


def get_llm_client():
    """Build the selected optional provider, or use deterministic fallback."""
    return build_llm_client()


def get_chat_manager(llm_client=Depends(get_llm_client)):
    """Get the chat session manager with the appropriate LLM client."""
    return chat_service.get_chat_session_manager(llm_client)


def _to_aware(value: datetime) -> datetime:
    """Normalize naive DB datetimes to UTC-aware for the API.

    Chat history timestamps are naive UTC in the database (pre-existing
    convention). Attaching the UTC zone in the response keeps the JSON
    unambiguous (\"...Z\") for clients in any local timezone.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _turn_timestamp(turn: dict) -> datetime:
    """Read timestamps from both Redis and Postgres session formats.

    Redis turns use ``timestamp`` while durable Postgres turns are serialized
    with ``created_at``. Older sessions may have either representation.
    """
    value = turn.get("timestamp") or turn.get("created_at")
    if isinstance(value, datetime):
        return _to_aware(value)
    if value:
        return _to_aware(datetime.fromisoformat(str(value)))
    # Preserve a valid API response for legacy turns without timestamp data.
    return datetime.fromtimestamp(0, tz=timezone.utc)


def get_optional_user_id(x_user_id: Optional[str] = Header(None, alias="X-User-ID")) -> Optional[str]:
    """Extract optional user ID from header."""
    return x_user_id


# --- Session Management Endpoints ---


def _session_info_to_schema(info: dict) -> SessionInfo:
    """Convert the manager's session-info dict into the API schema."""
    return SessionInfo(
        session_id=info["session_id"],
        user_id=info["user_id"],
        turn_count=info["turn_count"],
        summary=info["summary"],
        preview=info.get("preview"),
        active_entities=info["active_entities"],
        current_topic=info["current_topic"],
        created_at=_to_aware(datetime.fromtimestamp(info["created_at"], tz=timezone.utc)),
        updated_at=_to_aware(datetime.fromtimestamp(info["updated_at"], tz=timezone.utc)),
    )

@router.post("/sessions", response_model=SessionCreateResponse)
def create_session(
    body: SessionCreateRequest,
    user_id: Optional[str] = Depends(get_optional_user_id),
    manager=Depends(get_chat_manager),
):
    """Create a new chat session."""
    session = manager._get_or_create_session(None, body.user_id or user_id)
    return SessionCreateResponse(
        session_id=session.session_id,
        created_at=_to_aware(datetime.fromtimestamp(session.created_at, tz=timezone.utc)),
    )


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    user_id: Optional[str] = Depends(get_optional_user_id),
    limit: int = Query(50, ge=1, le=200),
    manager=Depends(get_chat_manager),
):
    """List chat sessions for the current user."""
    sessions = manager.list_sessions(user_id, limit)
    return SessionListResponse(
        sessions=[_session_info_to_schema(s) for s in sessions],
        total=len(sessions),
    )


@router.get("/sessions/{session_id}", response_model=SessionInfo)
def get_session(
    session_id: str,
    manager=Depends(get_chat_manager),
):
    """Get session info."""
    info = manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_info_to_schema(info)


@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
def get_session_history(
    session_id: str,
    manager=Depends(get_chat_manager),
):
    """Get full conversation history for a session."""
    history = manager.get_session_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionHistoryResponse(
        session_id=history["session_id"],
        turns=[
            TurnInfo(
                turn_index=t["turn_index"],
                user_message=t["user_message"],
                assistant_response=t.get("assistant_response"),
                intent=t.get("intent"),
                entities=t.get("entities", {}),
                parse_method=t.get("parse_method"),
                data=t.get("data", {}),
                timestamp=_turn_timestamp(t),
            )
            for t in history["turns"]
        ],
        summary=history["summary"],
    )


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    manager=Depends(get_chat_manager),
):
    """Delete a chat session."""
    manager.delete_session(session_id)
    return {"message": "Session deleted", "session_id": session_id}


# --- Chat Endpoints ---------------------------------------------------------

@router.post("", response_model=ConversationChatResponse)
def chat(
    body: ChatRequest,
    user_id: Optional[str] = Depends(get_optional_user_id),
    db: Session = Depends(get_db),
    manager=Depends(get_chat_manager),
):
    """
    Send a message and get a response with conversation memory.
    
    - If session_id is provided, continues that conversation
    - If session_id is omitted, creates a new session
    - Context (entities, topics) is carried across turns automatically
    """
    return manager.handle_message(
        db=db,
        message=body.message,
        session_id=body.session_id,
        user_id=body.user_id or user_id,
    )


@router.post("/feedback")
def chat_feedback(
    body: FeedbackRequest,
    db: Session = Depends(get_db),
):
    """Record thumbs up/down on one assistant answer (Upgrade #5).

    Analytics only: it never changes past answers, it builds the eval
    signal for future chatbot improvements.
    """
    from app.nlp.session_store import ConversationTurn

    turn = (
        db.query(ConversationTurn)
        .filter(
            ConversationTurn.session_id == body.session_id,
            ConversationTurn.turn_index == body.turn_index,
        )
        .one_or_none()
    )
    if turn is None:
        raise HTTPException(status_code=404, detail="Chat turn not found.")
    turn.feedback = "helpful" if body.helpful else "not_helpful"
    db.commit()
    return FeedbackResponse(
        session_id=body.session_id,
        turn_index=body.turn_index,
        helpful=body.helpful,
        recorded=True,
    )


@router.post("/context-command", response_model=ContextCommandResponse)
def context_command(
    body: ContextCommandRequest,
    manager=Depends(get_chat_manager),
):
    """
    Execute a context management command:
    - "reset" / "clear context" / "start over" - clear all context
    - "show history" - show conversation summary
    - "forget P0001" - forget a specific product
    - "back to <topic>" - switch to a previous topic
    """
    cm = manager._get_or_create_context_manager(body.session_id)
    response = cm.handle_command(body.command)
    if response is None:
        raise HTTPException(status_code=400, detail=f"Unknown command: {body.command}")
    
    return ContextCommandResponse(
        session_id=body.session_id,
        response=response,
        context=cm.get_context_for_llm(),
    )


# --- Legacy endpoint (backward compatibility) -------------------------------

from app.schemas.chat import ChatRequest as LegacyChatRequest, ChatResponse as LegacyChatResponse

@router.post("/legacy", response_model=LegacyChatResponse, include_in_schema=False)
def chat_legacy(
    body: LegacyChatRequest,
    db: Session = Depends(get_db),
    llm_client=Depends(get_llm_client),
):
    """Legacy chat endpoint (stateless, no session memory)."""
    return chat_service.handle_chat_message(db, body.message, llm_client=llm_client)
