"""Chatbot eval set (Upgrade #5): fixed questions, expected answers.

Rules-only (no network, no LLM): every case below must classify and answer
deterministically. If a future change breaks one, the suite names the exact
question that regressed instead of a vague failure somewhere downstream.
"""

import pytest

from app.nlp.intent import Intent
from app.services.chat_service import handle_chat_message

# (question, expected intent, check): check receives the response and asserts.
CASES = [
    ("How much stock do we have for P0001?", Intent.CURRENT_STOCK,
     lambda r: r.data is not None and r.data["product_id"] == "P0001"),
    ("Which products are low on stock?", Intent.LOW_STOCK,
     lambda r: r.data is not None),
    ("What are our top-selling products?", Intent.TOP_SELLING,
     lambda r: r.data is not None),
    ("Show sales trend for P0002 last month", Intent.SALES_TREND,
     lambda r: r.data is not None),
    ("Forecast P0003 for the next 14 days", Intent.DEMAND_FORECAST,
     lambda r: r.data is not None and r.data["product_id"] == "P0003"),
    ("Will P0007 run out of stock?", Intent.STOCKOUT_RISK,
     lambda r: r.data is not None and r.data["risk"] == "HIGH"),
    ("How much should we reorder for P0007?", Intent.REORDER_RECOMMENDATION,
     lambda r: r.data is not None and r.data["recommended_reorder_quantity"] > 0),
    ("What is our sales revenue?", Intent.REVENUE_ANALYSIS,
     lambda r: r.data is not None),
    ("Which category sells the most?", Intent.CATEGORY_ANALYSIS,
     lambda r: r.data is not None),
    ("How are stores performing?", Intent.STORE_PROFITABILITY,
     lambda r: r.data is not None and r.data["group_by"] == "store"),
    ("Tell me about P0004", Intent.PRODUCT_INFO,
     lambda r: r.data is not None),
    ("Show stock history for P0001", Intent.STOCK_HISTORY,
     lambda r: r.data is not None),
    # Upgrade #1: names resolve without P-codes.
    ("How much stock for kitchen blender?", Intent.CURRENT_STOCK,
     lambda r: r.data is not None and r.data["product_id"] == "P0007"),
    # Upgrade #3: two products compare in one turn.
    ("Compare P0001 and P0002 risk", Intent.PRODUCT_COMPARE,
     lambda r: r.data is not None and r.data["verdict_product_id"] in {"P0001", "P0002"}),
    ("Compare blender and headphones", Intent.PRODUCT_COMPARE,
     lambda r: r.data is not None and {item["product_id"] for item in r.data["products"]} == {"P0007", "P0001"}),
    ("what needs to be rstocked", Intent.LOW_STOCK,
     lambda r: r.data is not None),
    # Unknown stays unknown, stays short, and never fabricates.
    ("How much stock does P9999 have?", None,
     lambda r: r.data is None),
    ("asdkjasd random gibberish", Intent.UNKNOWN,
     lambda r: r.data is None and len(r.message) < 200),
]


@pytest.mark.parametrize(
    "question,expected_intent,check",
    CASES,
    ids=[case[0][:40] for case in CASES],
)
def test_chat_eval_case(db, question, expected_intent, check):
    response = handle_chat_message(db, question)
    if expected_intent is not None:
        assert response.intent == expected_intent, f"{question!r} classified as {response.intent}"
    assert check(response), f"{question!r} failed its answer check: {response.message[:200]}"


def test_chat_feedback_round_trip(db):
    """Thumbs up/down persists on the turn (Upgrade #5 analytics loop)."""
    from fastapi.testclient import TestClient

    import app.main as main
    from app.database import get_db
    from app.database import SessionLocal
    from app.services.chat_service import set_chat_session_manager

    main.require_request_identity = lambda req: "admin"
    main.app.dependency_overrides[get_db] = lambda: SessionLocal()
    client = TestClient(main.app, raise_server_exceptions=False)
    try:
        created = client.post("/api/chat/sessions", json={}).json()
        session_id = created["session_id"]
        client.post("/api/chat", json={"message": "How much stock for P0001?", "session_id": session_id})
        vote = client.post(
            "/api/chat/feedback",
            json={"session_id": session_id, "turn_index": 0, "helpful": True},
        )
        assert vote.status_code == 200, vote.text
        assert vote.json()["recorded"] is True
        missing = client.post(
            "/api/chat/feedback",
            json={"session_id": session_id, "turn_index": 99, "helpful": False},
        )
        assert missing.status_code == 404
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        # The TestClient path installs a REAL-LLM manager globally; drop it
        # so later tests get the deterministic rules-only manager again.
        # Without this, test order changes results (and the suite hits the
        # network).
        set_chat_session_manager(None)
