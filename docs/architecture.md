# Architecture

How InventoryAI is put together: the layered request path, the real-time
WebSocket hub, the ML pipeline, and the deterministic operations formulas.
Companion to `README.md` (what it does) and `docs/limitations.md` (what it
honestly cannot do).

## 1. Layered request path (Router → Service → Repository → Database)

Every analytical endpoint follows the same four layers. Components never skip
one: routers never query the database, services never touch HTTP, and the
frontend never calls `fetch()` directly (all HTTP goes through
`frontend/src/services/api.ts`, with TypeScript types in
`frontend/src/types/` mirroring the Pydantic schemas field-for-field).

```
React page (frontend/src/pages/*)
        │  HTTP/JSON via services/api.ts
        ▼
Router (backend/app/routers/*)        parse/validate query + body, map errors
        │  Pydantic schemas (backend/app/schemas/*)
        ▼
Service (backend/app/services/*)      business logic, formulas, cache policy
        │  plain function calls, no HTTP/SQL literals
        ▼
Repository (backend/app/repositories/*)  SQLAlchemy queries only
        │  Session in, rows/DataFrame out
        ▼
PostgreSQL (backend/app/models/* + Alembic migrations)
```

- **Routers** (`stockout.py`, `reorder.py`, `sales.py`, `inventory.py`,
  `products.py`, `forecast.py`, `dashboard.py`, `chat.py`, `live.py`,
  `watchlist.py`, `settings.py`, `model_health.py`, `purchase_orders.py`,
  `auth.py`, `health.py`, `ws.py`) translate HTTP into service calls and
  service exceptions into status codes: `NotFoundError` → 404,
  `InvalidRequestError` → 400, Pydantic failures → 422, anything else → 500
  with a generic message (see `app/main.py` handlers).
- **Services** own every number: `inventory_service` (current/low stock,
  adjustments), `sales_service` (trends, rankings, profitability, recording),
  `forecast_service` (model loading + inference), `stockout_service` and
  `reorder_service` (risk engine), `dashboard_service` (one-shot Tier A
  assembly), `chat_service` (NLP routing), `simulator_service` (demo traffic),
  `settings_service` (effective ops knobs).
- **Repositories** own every query: per-module SQLAlchemy selects, plus two
  process caches for immutable history (`get_full_history_dataframe_cached`,
  risk-result cache with TTL + `clear_risk_cache()` on any write).
- **Auth** sits in middleware (`protect_api` in `app/main.py`): every
  `/api/*` route except health/login requires a bearer token; WebSockets
  check identity before `accept()` and close with `1008` otherwise.

Key invariant: `dashboard_service` computes **nothing new** — it calls the
same services the detail pages use, so the summary can never drift from the
pages it summarizes (enforced by
`test_dashboard_summary_agrees_with_the_detail_endpoints`).

## 2. Real-time WebSocket hub

Two sockets, one pattern: REST stays the source of truth, the socket is a
live view over it with a REST fallback.

```
Simulator tick (REST POST /api/simulator/tick|start)
        │  samples per-(store, product) demand from Postgres
        ▼
simulator_service  →  writes live_sales_events  →  recomputes risk with the
        │              (own table, NEVER daily_*)     same stockout formula,
        │                                            raises StockoutAlert rows
        ▼
live_hub (in-process fan-out, bounded per-subscriber buffer)
        ├── WS /api/live/ws  → Live page ticker + alerts (+ backlog on connect)
        └── REST fallback: /api/live/events, /api/live/alerts, /api/live/summary

WS /api/chat/ws  →  per-turn pipeline progress + token streaming; the final
                    chat_response frame is authoritative (verified data only)
```

- **Isolation guarantee**: live rows never touch `daily_sales` /
  `daily_inventory`, so no model, metric, or backtest is polluted.
- **Alert rule** (threshold, not probability): with
  `projected = last recorded inventory − live units sold`,
  `projected < forecast_lead_time_demand` → CRITICAL,
  else `projected < required_inventory` → WARNING, with a per-product
  cooldown against re-announcement.
- **Limits** (see `docs/limitations.md`): single-process hub (one uvicorn
  worker), synthetic traffic, slow subscribers drop oldest frames (persisted
  backlog stays complete).

## 3. ML pipeline mechanics

```
scripts/clean_data.py  →  data/processed/cleaned_inventory.csv
scripts/load_database.py  →  PostgreSQL (products, stores, daily_*, Sample Data)
ml/features/build_features.py  →  supervised (origin T, target T+h) frames, h ∈ {7, 14}
ml/training/train_forecast.py  →  XGBoost + 7-day-MA baseline, chronological split
                                   train < 2023-07-01 · val ≤ 2023-10-01 · test after
ml/artifacts/  →  forecast_model_h{7,14}.joblib, forecast_metadata_h{7,14}.json,
                  forecast_summary.json  (surfaced on /model-health)
```

- **Inference** (`forecast_service`): models load once into a module cache;
  `build_live_feature_row` builds the origin-T feature row from the **database**
  (source of truth, Sample Data only) — a separate builder from training time
  because there is no future actual to supervise against.
- **Leakage guards**: lag/rolling features use data ≤ T only; target-date
  price/promotion assume planned calendars; origin inventory only; the source
  `Demand Forecast` column is never a feature (automated test).
- **Results** (test holdout): 7-day MAE 88.5 vs 93.4 baseline (~5.2% better);
  14-day MAE 88.5 vs 92.8 (~4.7%); sMAPE ~72%. Modest and honestly reported.

## 4. Deterministic operations formulas

All knobs below are admin-editable on `/settings` (PostgreSQL
`system_settings` overrides env defaults via `settings_service`).

```
forecast_lead_time_demand = (model_forecast_total / model_horizon) × lead_time_days
safety_stock              = historical_daily_demand_std × safety_stock_service_factor
required_inventory        = forecast_lead_time_demand + safety_stock

HIGH    current_inventory <  forecast_lead_time_demand
MEDIUM  forecast_lead_time_demand ≤ current_inventory < required_inventory
LOW     current_inventory ≥ required_inventory

reorder_quantity = max(0, forecast_lead_time_demand + safety_stock − current_inventory)
```

- `lead_time_days` defaults to `DEFAULT_LEAD_TIME_DAYS` (7) — echoed in every
  response because the dataset has no real supplier lead time.
- Store scope (`?store_id=S001…S005`) evaluates one store's on-hand against
  that store's apportioned share (product demand ÷ stores carrying it),
  disclosed in `reason`/`assumptions` — a stepping stone to per-store models.
- **DELIVERY guard** (`inventory_service.adjust_stock`): a receipt must be
  positive and may not exceed outstanding `units_ordered` (it decrements the
  reservation as it lands); stock can never go negative.
- **Purchase orders** (`purchase_orders`): DRAFT reserves `units_ordered`;
  receive converts to a DELIVERY through the same guarded path; cancel
  releases the reservation.
- **Genuine-sales separation**: `record_sale` deducts stock, appends a
  movement-ledger row and a cost-snapshotted transaction, and tags the day row
  `Real · Manual` (CSV import tags `Real · CSV Import`); both are excluded
  from the training frame and forecast history.

## 5. Scaling notes

- List endpoints are server-side paginated (`limit`/`offset` on
  `/api/stockout-risk`, `/api/reorder`, `/api/sales`) with search/category/
  store filters pushed to the backend.
- The dashboard is one request (Tier A) with in-process risk caching; the
  history DataFrame is built once per process.
- Known next bottlenecks: per-product forecast loop on huge catalogs (batch
  inference), single-process hub (Redis pub/sub), unbounded CSV exports
  (stream in chunks) — see README Future Improvements.
