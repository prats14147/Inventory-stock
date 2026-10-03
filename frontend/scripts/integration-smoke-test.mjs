// frontend/scripts/integration-smoke-test.mjs
//
// Phase 10 integration check: verifies the frontend's assumptions about
// the API (endpoints, response shapes, CORS) actually match the live
// backend -- not a replacement for the backend's own pytest suite, which
// tests backend correctness in isolation. This tests the CONTRACT between
// the two halves, using the same request shapes frontend/src/services/api.ts
// uses, with a real HTTP client (Node's built-in fetch), against a real
// running server.
//
// Usage: node frontend/scripts/integration-smoke-test.mjs
// Requires: backend running on BASE_URL (default http://localhost:8000)

const BASE_URL = process.env.API_BASE_URL || "http://localhost:8000";
const FRONTEND_ORIGIN = "http://localhost:5173";

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (condition) {
    passed++;
    console.log(`  \u2713 ${message}`);
  } else {
    failed++;
    console.error(`  \u2717 FAILED: ${message}`);
  }
}

async function get(path, { origin = false } = {}) {
  const headers = origin ? { Origin: FRONTEND_ORIGIN } : {};
  const res = await fetch(`${BASE_URL}${path}`, { headers });
  const body = await res.json();
  return { res, body };
}

async function post(path, payload) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: FRONTEND_ORIGIN },
    body: JSON.stringify(payload),
  });
  const body = await res.json();
  return { res, body };
}

async function main() {
  console.log(`Integration smoke test against ${BASE_URL}\n`);

  console.log("Health & CORS:");
  {
    const { res, body } = await get("/api/health", { origin: true });
    assert(res.status === 200, "GET /api/health -> 200");
    assert(body.status === "ok", "health body has status:ok");
    assert(
      res.headers.get("access-control-allow-origin") === "*",
      "CORS allows the frontend origin (wildcard, no credentials used)"
    );
  }

  console.log("\nProducts (shape matches ProductListResponse / ProductDetailResponse):");
  {
    const { res, body } = await get("/api/products");
    assert(res.status === 200, "GET /api/products -> 200");
    assert(Array.isArray(body.product_ids) && body.product_ids.length === 20, "20 product_ids returned");
    assert(typeof body.count === "number", "count is a number");

    const pid = body.product_ids[0];
    const { body: detail } = await get(`/api/products/${pid}`);
    for (const field of ["product_id", "as_of_date", "current_total_inventory", "total_units_sold_all_time"]) {
      assert(field in detail, `product detail has field '${field}'`);
    }
  }

  console.log("\nInventory (CurrentInventoryRow / ProductInventoryResponse / LowStockResponse):");
  {
    const { body } = await get("/api/inventory");
    assert(Array.isArray(body) && body.length === 100, "100 current-inventory rows (5 stores x 20 products)");
    for (const field of ["date", "store_id", "product_id", "inventory_level", "units_ordered", "category", "region"]) {
      assert(field in body[0], `inventory row has field '${field}'`);
    }

    const { body: single } = await get("/api/inventory/P0001");
    assert(single.product_id === "P0001", "single product inventory returns correct product_id");
    assert(Array.isArray(single.stores) && single.stores.length === 5, "5 store breakdowns returned");

    const { body: low } = await get("/api/inventory/low-stock?threshold=2000");
    assert(typeof low.count === "number" && low.count === low.items.length, "low-stock count matches items length");
  }

  console.log("\nSales (TopProductsResponse / SalesTrendResponse / summaries):");
  {
    const { body: top } = await get("/api/sales/top-products?limit=5");
    assert(top.products.length === 5, "top-products respects limit=5");
    assert("product_id" in top.products[0] && "total_units_sold" in top.products[0], "product rank shape correct");

    const { body: trend } = await get("/api/sales/trends?granularity=monthly&product_id=P0001");
    assert(trend.points.length === 25, "monthly trend has 25 points for the 2-year dataset");

    const { body: byCategory } = await get("/api/sales/by-category");
    assert(byCategory.length === 5, "5 categories in by-category summary");
  }

  console.log("\nForecast (ForecastResponse):");
  {
    const { body } = await get("/api/forecast/P0001?horizon=14");
    for (const field of ["product_id", "model_horizon_days", "target_date", "forecast_total_units", "per_store"]) {
      assert(field in body, `forecast response has field '${field}'`);
    }
    assert(body.per_store.length === 5, "forecast per_store has 5 entries");
  }

  console.log("\nStockout risk & Reorder (StockoutRiskResponse / ReorderResponse):");
  {
    const { body } = await get("/api/stockout-risk/P0007");
    assert(["LOW", "MEDIUM", "HIGH"].includes(body.risk), "risk is a valid enum value");
    assert(body.risk === "HIGH", "P0007 is known HIGH risk (cross-check with backend test suite)");

    const { body: reorder } = await get("/api/reorder/P0007");
    assert(reorder.recommended_reorder_quantity > 0, "P0007 has a nonzero reorder recommendation");
    assert("lead_time_days" in reorder.assumptions, "reorder assumptions are disclosed");
  }

  console.log("\nChat (ChatResponse, no-hallucination contract):");
  {
    const { body } = await post("/api/chat", { message: "How much stock does P0001 have?" });
    assert(body.intent === "CURRENT_STOCK", "chat correctly classifies intent");
    assert(body.data !== null && body.data.product_id === "P0001", "chat returns real backend data");
    assert(typeof body.session_id === "string" && body.session_id.length > 0, "chat echoes a session_id");

    const { body: unknown } = await post("/api/chat", { message: "How much stock does P9999 have?" });
    assert(unknown.data === null, "unknown product returns null data (never fabricated)");
    assert(unknown.message.toLowerCase().includes("couldn't find"), "unknown product gets a clear not-found message");
  }

  console.log("\nChat sessions (Phase 11 memory contract):");
  {
    // Session resume: a second turn in the same session keeps context.
    const first = await post("/api/chat", { message: "How much stock does P0001 have?" });
    const sid = first.body.session_id;
    const second = await post("/api/chat", { message: "Forecast it for 7 days", session_id: sid });
    assert(second.body.session_id === sid, "same session_id continues the conversation");
    assert(
      second.body.entities && second.body.entities.product_id === "P0001",
      "product entity carries over to the follow-up turn"
    );

    const { body: history } = await get(`/api/chat/sessions/${sid}/history`);
    assert(history.turns.length === 2, "history returns both turns");
    assert(history.turns[0].user_message.includes("P0001"), "first turn stored verbatim");

    const { body: listed } = await get("/api/chat/sessions?limit=5");
    assert(Array.isArray(listed.sessions), "session list returns sessions array");
    const found = listed.sessions.find((s) => s.session_id === sid);
    assert(found && typeof found.preview === "string", "listed session carries a preview label");
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  if (failed > 0) process.exit(1);
}

main().catch((err) => {
  console.error("Integration smoke test crashed:", err);
  process.exit(1);
});
