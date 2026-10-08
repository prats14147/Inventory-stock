"""backend/tests/test_api.py"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_products():
    r = client.get("/api/products")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 20
    assert "P0001" in body["product_ids"]


def test_get_product_detail():
    r = client.get("/api/products/P0001")
    assert r.status_code == 200
    body = r.json()
    assert body["product_id"] == "P0001"
    assert body["current_total_inventory"] > 0


def test_get_product_detail_not_found():
    r = client.get("/api/products/P9999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_list_current_inventory():
    r = client.get("/api/inventory")
    assert r.status_code == 200
    assert len(r.json()) == 100  # 5 stores x 20 products


def test_list_current_inventory_filtered_by_category():
    r = client.get("/api/inventory", params={"category": "Electronics"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    assert all(row["category"] == "Electronics" for row in body)


def test_get_inventory():
    r = client.get("/api/inventory/P0001")
    assert r.status_code == 200
    assert len(r.json()["stores"]) == 5


def test_low_stock():
    r = client.get("/api/inventory/low-stock", params={"threshold": 2000})
    assert r.status_code == 200
    assert r.json()["threshold"] == 2000


def test_top_products():
    r = client.get("/api/sales/top-products", params={"limit": 3})
    assert r.status_code == 200
    assert len(r.json()["products"]) == 3


def test_bottom_products():
    r = client.get("/api/sales/bottom-products", params={"limit": 3})
    assert r.status_code == 200
    assert len(r.json()["products"]) == 3


def test_sales_trends_monthly():
    r = client.get("/api/sales/trends", params={"granularity": "monthly", "product_id": "P0001"})
    assert r.status_code == 200
    # >= 25, not == 25: 25 is the seed history, but recording a sale (the
    # app's core feature) legitimately adds a new month. The check is that
    # the full seed history comes back, not that the DB never changes.
    assert len(r.json()["points"]) >= 25


def test_sales_trends_invalid_granularity_returns_422():
    r = client.get("/api/sales/trends", params={"granularity": "yearly"})
    assert r.status_code == 422  # caught by FastAPI's own query validation


def test_sales_by_category_and_store():
    r1 = client.get("/api/sales/by-category")
    r2 = client.get("/api/sales/by-store")
    assert r1.status_code == 200 and len(r1.json()) == 5
    assert r2.status_code == 200 and len(r2.json()) == 5


def test_forecast_get():
    r = client.get("/api/forecast/P0001", params={"horizon": 14})
    assert r.status_code == 200
    body = r.json()
    assert body["model_horizon_days"] == 14
    assert len(body["per_store"]) == 5


def test_forecast_post():
    r = client.post("/api/forecast", json={"product_id": "P0001", "horizon": 7})
    assert r.status_code == 200
    assert r.json()["model_horizon_days"] == 7


def test_forecast_not_found():
    r = client.get("/api/forecast/P9999")
    assert r.status_code == 404


def test_stockout_risk_single():
    r = client.get("/api/stockout-risk/P0007")
    assert r.status_code == 200
    assert r.json()["risk"] == "HIGH"


def test_stockout_risk_list_only_at_risk():
    r = client.get("/api/stockout-risk", params={"only_at_risk": True})
    assert r.status_code == 200
    body = r.json()
    assert all(item["risk"] != "LOW" for item in body)
    assert len(body) > 0  # we know P0007 etc. are at risk


def test_reorder_single():
    r = client.get("/api/reorder/P0007")
    assert r.status_code == 200
    assert r.json()["recommended_reorder_quantity"] > 0


def test_reorder_list_only_needed():
    r = client.get("/api/reorder", params={"only_needed": True})
    assert r.status_code == 200
    assert all(item["recommended_reorder_quantity"] > 0 for item in r.json())


def test_chat_current_stock():
    r = client.post("/api/chat", json={"message": "How much stock does P0001 have?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "CURRENT_STOCK"
    assert "P0001" in body["message"]


def test_chat_unknown_product_never_fabricates():
    r = client.post("/api/chat", json={"message": "How much stock does P9999 have?"})
    assert r.status_code == 200  # chat always returns 200 -- errors are conversational, not HTTP errors
    body = r.json()
    assert body["data"] is None
    assert "couldn't find" in body["message"].lower()


def test_chat_missing_message_field_returns_422():
    r = client.post("/api/chat", json={})
    assert r.status_code == 422


def test_cors_headers_present():
    r = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


def test_cors_present_on_simple_get_not_just_preflight():
    """Catches the Phase 10 bug: allow_credentials=True + wildcard origin
    produced inconsistent headers between preflight and actual requests."""
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")



def test_morning_briefing_shape_and_consistency():
    r = client.get("/api/briefing")
    assert r.status_code == 200
    body = r.json()
    assert "headline" in body and isinstance(body["headline"], str)
    assert body["critical_alerts"] <= body["open_alerts"]
    assert len(body["top_risks"]) <= 3
    product_ids = {item["product_id"] for item in body["top_risks"]}
    for suggestion in body["suggested_orders"]:
        assert suggestion["product_id"] in product_ids
        assert suggestion["suggested_quantity"] >= 1
