"""
backend/tests/test_ws_chat.py

Tests for the WebSocket streaming chat endpoint (app/routers/ws.py).

These exercise the endpoint through Starlette's TestClient websocket support
(real frame protocol, real thread hand-off) against the live Postgres data
loaded by scripts/load_database.py -- the same database the REST tests use.
An in-memory session store keeps them independent of a local Redis.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.nlp.session_store import HybridSessionStore, set_session_store
from app.services import chat_service

WS_URL = "/api/chat/ws"


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def memory_store():
    """Force the in-memory session store for the duration of a test.

    The handler uses the same process-global session store as the REST
    router; the chat manager also caches the store it was built with, so it
    is rebuilt here and torn down afterwards.
    """
    store = HybridSessionStore()
    store.redis_store._available = False
    store.redis_store._memory_store = {}
    store.postgres_store = None
    set_session_store(store)
    chat_service.set_chat_session_manager(None)
    yield store
    set_session_store(None)
    chat_service.set_chat_session_manager(None)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


class FakeStreamingLLMClient:
    """Minimal client that supports both the blocking and streaming phrasing
    paths, so the token-frame contract can be tested without a network call."""

    def __init__(self, chunks: list[str] | None = None, json_response: dict | None = None):
        self.chunks = chunks if chunks is not None else ["P0001 ", "currently ", "has stock."]
        self.json_response = json_response or {}
        self.stream_calls = 0

    def complete_json(self, system_prompt: str, user_message: str) -> str:
        return json.dumps(self.json_response)

    def complete_text(self, system_prompt: str, user_message: str) -> str:
        return "".join(self.chunks)

    def stream_text(self, system_prompt: str, user_message: str):
        self.stream_calls += 1
        for chunk in self.chunks:
            yield chunk


def _read_until_final(ws, limit: int = 200) -> list[dict]:
    """Collect frames until the authoritative frame (response or error)."""
    frames: list[dict] = []
    while len(frames) < limit:
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") in ("chat_response", "error"):
            return frames
    raise AssertionError(f"no final frame within {limit} frames: {frames}")


# --- Connection / protocol --------------------------------------------------

def test_ws_announces_session_on_connect(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        frame = ws.receive_json()
        assert frame["type"] == "session_created"
        assert frame["session_id"]
        assert memory_store.get_session(frame["session_id"]) is not None


def test_ws_resumes_existing_session(client, memory_store):
    session = memory_store.create_session()
    with client.websocket_connect(f"{WS_URL}?session_id={session.session_id}") as ws:
        frame = ws.receive_json()
        assert frame["session_id"] == session.session_id


def test_ws_ping_pong(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        ws.receive_json()  # session_created
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_ws_rejects_malformed_frame(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        ws.receive_json()  # session_created
        ws.send_text("this is not json")
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert frame["code"] == "invalid_frame"


def test_ws_rejects_unsupported_frame_type(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        ws.receive_json()  # session_created
        ws.send_json({"type": "teleport", "message": "hi"})
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert frame["code"] == "unsupported_frame"


def test_ws_rejects_foreign_session_id(client, memory_store):
    """A socket is bound to the session it announced -- no session hopping."""
    with client.websocket_connect(WS_URL) as ws:
        announced = ws.receive_json()["session_id"]
        ws.send_json({"type": "chat", "message": "Stock for P0001", "session_id": "not-my-session"})
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert frame["code"] == "session_mismatch"
        assert announced in frame["message"]


def test_ws_reset_clears_context(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        session_id = ws.receive_json()["session_id"]
        ws.send_json({"type": "chat", "message": "Stock for P0001"})
        _read_until_final(ws)

        ws.send_json({"type": "reset"})
        assert ws.receive_json()["type"] == "context_reset"

        # The follow-up must no longer resolve to P0001 -> clarification ask
        ws.send_json({"type": "chat", "message": "Forecast it"})
        final = _read_until_final(ws)[-1]
        assert final["type"] == "chat_response"
        assert final["entities"]["product_id"] is None
        # Context is genuinely gone, not just unlinked in the response.
        info = chat_service.get_chat_session_manager().get_session_info(session_id)
        assert info["active_entities"].get("product_id") is None


# --- Streaming behaviour ----------------------------------------------------

def test_ws_streams_progress_then_verified_response(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        ws.receive_json()  # session_created
        ws.send_json({"type": "chat", "message": "How much stock do we have for P0001?"})
        frames = _read_until_final(ws)

        statuses = [f["stage"] for f in frames if f["type"] == "status"]
        assert statuses[0] == "analyzing_request"
        assert "querying_database" in statuses

        final = frames[-1]
        assert final["type"] == "chat_response"
        assert final["intent"] == "CURRENT_STOCK"
        assert final["data"]["product_id"] == "P0001"
        assert "P0001" in final["message"]


def test_ws_final_frame_carries_context_and_entities(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        ws.receive_json()  # session_created
        ws.send_json({"type": "chat", "message": "Stock for P0001"})
        final = _read_until_final(ws)[-1]

        assert final["entities"]["product_id"] == "P0001"
        assert final["context"]["active_entities"]["product_id"] == "P0001"


def test_ws_entity_carryover_in_same_connection(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        ws.receive_json()  # session_created

        ws.send_json({"type": "chat", "message": "Stock for P0001"})
        _read_until_final(ws)

        ws.send_json({"type": "chat", "message": "Forecast it for 7 days"})
        final = _read_until_final(ws)[-1]

        assert final["intent"] == "DEMAND_FORECAST"
        assert final["entities"]["product_id"] == "P0001"
        assert final["data"] is not None


def test_ws_unknown_product_never_fabricates(client, memory_store):
    with client.websocket_connect(WS_URL) as ws:
        ws.receive_json()  # session_created
        ws.send_json({"type": "chat", "message": "How much stock does P9999 have?"})
        final = _read_until_final(ws)[-1]

        assert final["data"] is None
        assert "couldn't find" in final["message"].lower()




def test_ws_streams_llm_tokens_then_authoritative_text(client, memory_store):
    """Token frames are provisional; the final frame repeats the full text and
    is the one the UI renders (see the module docstring in routers/ws.py)."""
    fake = FakeStreamingLLMClient(chunks=["P0001 ", "is ", "well stocked."])
    chat_service.set_chat_session_manager(chat_service.ChatSessionManager(llm_client=fake))

    with client.websocket_connect(WS_URL) as ws:
        ws.receive_json()  # session_created
        ws.send_json({"type": "chat", "message": "How much stock do we have for P0001?"})
        frames = _read_until_final(ws)

    tokens = [f["text"] for f in frames if f["type"] == "token"]
    final = frames[-1]

    assert fake.stream_calls == 1
    assert "".join(tokens) == "P0001 is well stocked."
    assert final["message"] == "P0001 is well stocked."
    assert final["data"]["product_id"] == "P0001"  # verified data still attached


# --- REST companion ---------------------------------------------------------

def test_streaming_status_probe(client):
    r = client.get("/api/chat/streaming-status")
    assert r.status_code == 200
    body = r.json()
    assert body["websocket_path"] == WS_URL
    assert "CURRENT_STOCK" in body["known_intents"]

