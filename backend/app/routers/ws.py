"""
backend/app/routers/ws.py

WebSocket endpoint for streaming chat (Tier 1 real-time layer).

Why a WebSocket at all: the REST endpoint returns one JSON blob once the
whole pipeline (parse -> validate -> query -> phrase) has finished. This
endpoint reports the same pipeline *while it runs*, so the UI can show what
the system is doing ("analyzing_request" -> "querying_database" ->
"phrasing_response") and stream the LLM's phrasing token by token.

FRAME PROTOCOL (all frames are JSON, `type` discriminates)
  client -> server
    {"type": "chat",  "message": "...", "session_id": "..." | null}
    {"type": "ping"}
    {"type": "reset"}                     # clears this session's context
  server -> client
    {"type": "session_created", "session_id": "..."}   # on connect
    {"type": "status",  "stage": "...", "session_id": "..."}
    {"type": "token",   "text": "...",  "session_id": "..."}
    {"type": "chat_response", ...same fields as the REST ChatResponse...}
    {"type": "pong"}
    {"type": "error", "code": "...", "message": "...", "session_id": "..."}

HONESTY NOTE -- token frames are *provisional*. The `chat_response` frame is
the authoritative one: it carries the verified `data` (straight from the
Phase 4-6 services / saved ML models) plus `intent` and `entities`. If the
LLM is unavailable mid-stream, the deterministic template is sent as the
final frame, and the client is expected to replace the streamed text with it
(see the frontend's streaming reducer). This keeps the no-hallucination
guarantee intact: nothing counts as "the answer" unless it arrives in the
final, verified frame.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import anyio
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.nlp.intent import Intent
from app.nlp.llm_client import build_llm_client
from app.schemas.conversation import WSChatMessage, WSError
from app.services import chat_service
from app.security import require_websocket_identity

router = APIRouter(tags=["chat-ws"])
log = logging.getLogger("ws")

_DONE = "__done__"
_PING_INTERVAL_SECONDS = 25.0


def _resolve_llm_client():
    """Use the same configured provider as the REST chat path."""
    return build_llm_client()


@router.websocket("/api/chat/ws")
async def chat_ws(
    websocket: WebSocket,
    session_id: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
) -> None:
    """Bidirectional chat with per-turn progress and token streaming."""
    if require_websocket_identity(websocket) is None:
        await websocket.close(code=1008, reason="Sign-in required")
        return
    await websocket.accept(subprotocol="inventoryai")

    manager = chat_service.get_chat_session_manager(_resolve_llm_client())
    session = manager._get_or_create_session(session_id, user_id)
    session_id = session.session_id
    await websocket.send_json({"type": "session_created", "session_id": session_id})

    try:
        while True:
            raw = await _receive_text(websocket)
            if raw is None:
                break  # client disconnected

            try:
                payload: Any = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("frame must be a JSON object")
            except (json.JSONDecodeError, ValueError):
                await websocket.send_json(
                    WSError(
                        code="invalid_frame",
                        message="Frames must be JSON objects.",
                        session_id=session_id,
                    ).model_dump()
                )
                continue

            frame_type = payload.get("type", "chat")

            if frame_type == "ping":
                await websocket.send_json({"type": "pong", "session_id": session_id})
                continue

            if frame_type == "reset":
                manager._get_or_create_context_manager(session_id).handle_command("reset")
                await websocket.send_json({"type": "context_reset", "session_id": session_id})
                continue

            if frame_type != "chat":
                await websocket.send_json(
                    WSError(
                        code="unsupported_frame",
                        message=f"Unsupported frame type: {frame_type}",
                        session_id=session_id,
                    ).model_dump()
                )
                continue

            try:
                chat_message = WSChatMessage(**payload)
            except Exception as exc:  # noqa: BLE001 -- pydantic ValidationError
                await websocket.send_json(
                    WSError(code="invalid_message", message=str(exc), session_id=session_id).model_dump()
                )
                continue

            # A turn may continue this socket's session, never a different
            # one: the connection owns exactly the session it announced.
            if chat_message.session_id and chat_message.session_id != session_id:
                await websocket.send_json(
                    WSError(
                        code="session_mismatch",
                        message="This connection is bound to session "
                        f"'{session_id}'; open a new connection to switch sessions.",
                        session_id=session_id,
                    ).model_dump()
                )
                continue

            await _stream_turn(websocket, manager, chat_message.message, session_id, user_id)

    except WebSocketDisconnect:
        log.info("WebSocket client disconnected (session=%s)", session_id)
    except Exception:  # noqa: BLE001
        log.exception("WebSocket loop failed (session=%s)", session_id)
        try:
            await websocket.send_json(
                WSError(code="internal_error", message="An unexpected error occurred.", session_id=session_id).model_dump()
            )
        except Exception:  # noqa: BLE001 -- socket already gone
            pass


async def _receive_text(websocket: WebSocket) -> Optional[str]:
    """Receive one text frame, returning None on disconnect."""
    try:
        return await websocket.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        return None


async def _stream_turn(
    websocket: WebSocket,
    manager: "chat_service.ChatSessionManager",
    message: str,
    session_id: str,
    user_id: Optional[str],
) -> None:
    """Run one chat turn in a worker thread and forward its frames live.

    The pipeline is synchronous (SQLAlchemy + XGBoost + a blocking HTTP call
    to Groq), so it must not run on the event loop. It runs in a thread and
    pushes frames onto an asyncio.Queue through `loop.call_soon_threadsafe`;
    this coroutine stays the only writer to the socket, which keeps frame
    ordering deterministic (progress frames always precede the final
    chat_response, and the final one always arrives last).
    """
    queue: "asyncio.Queue[dict]" = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(frame: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, frame)

    def on_stage(stage: str) -> None:
        emit({"type": "status", "stage": stage, "session_id": session_id})

    def on_token(text: str) -> None:
        emit({"type": "token", "text": text, "session_id": session_id})

    def run_pipeline() -> None:
        db: Session = SessionLocal()
        try:
            response = manager.handle_message(
                db=db,
                message=message,
                session_id=session_id,
                user_id=user_id,
                on_stage=on_stage,
                on_token=on_token,
            )
            # mode="json" so enums (Intent) serialize to plain strings.
            emit({"type": "chat_response", **response.model_dump(mode="json")})
        except Exception:  # noqa: BLE001
            log.exception("Chat turn failed (session=%s)", session_id)
            emit(
                WSError(
                    code="internal_error",
                    message="An unexpected error occurred.",
                    session_id=session_id,
                ).model_dump()
            )
        finally:
            db.close()
            emit({"type": _DONE})

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(anyio.to_thread.run_sync, run_pipeline)
        while True:
            frame = await queue.get()
            if frame.get("type") == _DONE:
                break
            await websocket.send_json(frame)


# --- REST companion: is streaming available? --------------------------------

@router.get("/api/chat/streaming-status", include_in_schema=False)
def streaming_status() -> dict:
    """Small, cache-friendly probe used by the frontend to decide whether to
    upgrade the chat widget to the WebSocket transport."""
    settings = get_settings()
    client = build_llm_client()
    provider = type(client).__name__.removesuffix("Client").lower() if client else "disabled"
    return {
        "websocket_path": "/api/chat/ws",
        "llm_streaming": client is not None,
        "llm_provider": provider,
        "llm_model": getattr(client, "model", None),
        "llm_fallback_model": getattr(client, "fallback_model", None),
        "ping_interval_seconds": _PING_INTERVAL_SECONDS,
        "known_intents": [intent.value for intent in Intent],
    }
