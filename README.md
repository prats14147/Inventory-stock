# Inventory Intelligence System (InventoryAI)

> Status: **Phase 10 of 12 complete — Integration.** Sections below are
> filled in as each phase lands.

## Project Overview
Retail inventory intelligence app combining inventory/sales analytics,
demand forecasting, stockout-risk scoring, reorder recommendations, and a
natural-language chatbot interface backed by real database/ML calculations
(never invented numbers).

## Problem Statement
_(added in Phase 12 documentation pass)_

## Objectives
_(added in Phase 12 documentation pass)_

## Features
_(added in Phase 12 documentation pass)_

## Architecture
```
Frontend (React + TS)
      |
   FastAPI REST API
      |
 -----------------------------
 |          |                |
NLP/Chat  Business Logic   ML Service
 |          |                |
 -----------------------------
      |
  PostgreSQL
```
Full diagrams land in `docs/architecture.md` (Phase 12).

## Technology Stack
- Backend: Python 3.11+, FastAPI, SQLAlchemy, Alembic, PostgreSQL
- Data/ML: pandas, NumPy, scikit-learn, XGBoost, joblib
- NLP: Gemini or Groq, hybrid intent/entity layer — LLM never
  invents data, only understands language and phrases verified results
- Frontend: React, TypeScript, Vite, Tailwind CSS, Recharts
- Testing: pytest, FastAPI TestClient

## Dataset
See `data/README.md`.

## EDA / Data Cleaning
- `scripts/clean_data.py` converts dates, clips negative numeric values and
  negative `Demand Forecast` to 0, flags (but does not alter) rows where
  `Units Sold >= Inventory Level`, and logs every correction to
  `data/processed/cleaning_log.txt`. Output: `data/processed/cleaned_inventory.csv`.
- `scripts/run_eda.py` produces 9 charts + a text summary under `ml/eda/`
  (dataset overview, product/category/store breakdowns, time trends,
  inventory-vs-sales / price-vs-sales / discount-vs-sales / promotion
  relationships).
- Key finding: sales show ~0 correlation with price/discount/promotion and
  are capped by inventory level — see `docs/limitations.md`.

## Database Design
PostgreSQL, SQLAlchemy models, Alembic migrations under `backend/alembic/`.

- `products` / `stores`: **identity tables only** (just the ID). The
  source data does not actually have a stable product→category or
  store→region mapping (see `docs/limitations.md`) — normalizing them as
  spec'd would have meant silently discarding most of the data.
- `daily_inventory` (date, store_id, product_id, inventory_level,
  units_ordered) — composite PK on (date, store_id, product_id).
- `daily_sales` (date, store_id, product_id, category, region, units_sold,
  price, discount, holiday_promotion, weather_condition,
  competitor_pricing, seasonality, demand_forecast_reference,
  possible_stock_constrained) — same composite PK; category/region live
  here since that's where they're actually stable per-row.
- Indexes added for per-product time-series lookups
  (`product_id, date`) and low-stock filtering (`inventory_level`), beyond
  the primary keys.
- Load: `scripts/load_database.py` — idempotent, truncates+reloads fact
  tables so re-running never duplicates data.
- Migration chain tested: `alembic downgrade base` → `alembic upgrade head`
  reproduces the schema exactly.

## Analytics (Phase 4)
Layered as `Router -> Service -> Repository -> Database`.

- **"Current" inventory** is defined as the latest date present in the
  data (2024-01-01) — the dataset is historical, so there's no literal
  present-day row. See `docs/limitations.md`.
- `InventoryService`: current stock per product (broken down by store),
  low-stock listing (configurable threshold, default from
  `LOW_STOCK_THRESHOLD`).
- `SalesService`: top/bottom-selling products (optionally date-ranged),
  sales trend at daily/weekly/monthly granularity (filterable by product,
  store, category, date range), category and store sales summaries.
- Unknown products raise `NotFoundError`; invalid date ranges or
  granularities raise `InvalidRequestError` — both map to proper HTTP
  status codes via the routers added in Phase 8.
- **Tested against the live database** in `backend/tests/`, with every
  aggregate cross-checked against an independently computed pandas value
  (not just "the code ran without crashing").

## ML / Forecasting (Phase 5)
- `ml/features/build_features.py` builds a supervised (origin T, target
  T+h) frame per (Store ID, Product ID) time series, for horizon h in
  {7, 14} days. See `docs/limitations.md` for the full leakage-safety
  design (what's knowable at forecast time vs. not).
- Chronological split by target date: train < 2023-07-01, val
  2023-07-01 to 2023-10-01, test >= 2023-10-01 (~75/12.5/12.5%).
- Baseline: 7-day moving average. Model: XGBoost (native categorical
  support, no manual encoding needed), early-stopped on the validation
  set.
- **Results (test set):** 7-day horizon MAE 88.5 vs. baseline 93.4
  (~5.2% better); 14-day horizon MAE 88.5 vs. baseline 92.8 (~4.7%
  better). Modest, honestly reported — see `docs/limitations.md` for why
  a much larger improvement would actually be a red flag on this dataset.
- `Demand Forecast` (the source column) is never used as a feature —
  enforced by an automated test, not just a code comment.
- Artifacts saved to `ml/artifacts/`: `forecast_model_h{7,14}.joblib`,
  `forecast_metadata_h{7,14}.json` (features, split sizes, metrics),
  `forecast_summary.json`. Verified in `tests/test_forecast_artifacts.py`
  that reloading the saved model reproduces the saved metrics exactly.

## Stockout Risk / Reorder (Phase 6)
- `ForecastService` loads the saved models once (module cache, never
  retrained per request) and forecasts **product-level** demand (summed
  across stores) at 7 or 14 days beyond the latest date in the data,
  using a new live-inference feature builder
  (`ml/features/build_features.py::build_live_feature_row`) — distinct
  from the training-time builder since there's no real future actual to
  supervise against.
- `StockoutService`: deterministic risk engine —
  `required_inventory = forecast_lead_time_demand + safety_stock`, with
  HIGH/MEDIUM/LOW tiers. Verified against all 20 real products: risk
  tiers actually vary (not a formula that always says the same thing).
- `ReorderService`: `reorder_quantity = max(0, forecast_lead_time_demand
  + safety_stock - current_inventory)`.
- No real supplier lead time exists in this dataset — every response
  explicitly echoes the `DEFAULT_LEAD_TIME_DAYS` assumption rather than
  applying it silently. See `docs/limitations.md` for the full
  lead-time-demand-approximation and safety-stock reasoning.

## NLP (Phase 7)
- `backend/app/nlp/`: deterministic rules and date/entity extraction,
  `tool_registry.py` (allowlisted capabilities and argument descriptions),
  `parser.py` (rules first, structured Gemini/Groq planner fallback), and
  provider prompts/client. The planner can select only registered backend
  tools; it cannot generate SQL or execute arbitrary code.
- `chat_service.py`: routes supported questions to verified database and
  forecasting tools. It can answer stock, sales trends, recorded net sales
  revenue, forecasts, stockout risk, reorder, category/store analysis, and
  project-document questions retrieved from the README and limitations notes.
  A confirmed-sale flow records sales and deducts stock only after a preview
  is accepted. The model interprets language and phrases grounded results; it
  cannot directly write arbitrary SQL or perform unconfirmed inventory changes.
- Intent parsing rejects unregistered tools and malformed model output.
  Revenue and gross-profit questions support date filters and grouping by
  product, store, or category. Chat can combine low-stock results with recent
  sales velocity, and lists reorder/stockout results when no product is
  specified. Relative dates such as “last month” are parsed by the backend.
- Product costs can be saved in Inventory; each recorded sale stores its
  selling price, discount, and cost snapshot. Imported historical sales have
  no cost snapshots, so their profit remains unknown. Chat confirms sales,
  deliveries, and non-sale adjustments before changing stock; delivery and
  damage adjustments never increase sales revenue.
- All of the spec's example test questions (section 49) verified
  end-to-end against the live database, including unknown-product and
  missing-entity clarification handling.

## Backend API (Phase 8)
- Routers: `health`, `products`, `inventory`, `sales`, `forecast`,
  `stockout`, `reorder`, `chat` — all under `/api`. Interactive docs at
  `/docs` (FastAPI's auto-generated Swagger UI).
- Error handling: `NotFoundError` -> 404, `InvalidRequestError` -> 400,
  Pydantic/query validation -> 422 (FastAPI's own), anything unexpected
  -> 500 with a generic message (logged server-side, never leaks
  internals to the client).
- CORS enabled (open for development — tighten `allow_origins` before any
  real deployment).
- **Actually tested with real HTTP requests** (not just "the code
  compiles"): started the server in this sandbox and hit every endpoint
  with `curl`, then wrote 22 FastAPI `TestClient` tests covering the same
  ground (including a 404 for an unknown product, 422 for a bad
  granularity/missing field, and the CORS preflight).
- `backend/Dockerfile` added and wired into `docker-compose.yml` — not
  build-tested (no Docker available in this build environment); see the
  Installation section below for the exact commands to verify locally.

## Frontend (Phase 9)
- React + TypeScript + Vite + Tailwind CSS, with 7 pages: Dashboard,
  Inventory, Sales, Forecast, Stockout Risk, Reorder, Chatbot.
- `frontend/src/types/` mirrors the backend's Pydantic schemas
  field-for-field; `frontend/src/services/api.ts` is the single place
  every HTTP call goes through (spec sections 44-45).
- **Actually built and verified in this sandbox**: `npm install`,
  `tsc -b` (TypeScript strict mode), and `vite build` all succeeded, and
  Tailwind was confirmed to emit real utility CSS. A live browser
  click-through was **not** possible here (no browser automation
  available) — see `docs/limitations.md` for what to check yourself with
  `npm run dev`.
- Bundle size (~570KB / 170KB gzipped) is above Vite's default warning
  threshold, mainly from Recharts — disclosed, not silently ignored; not
  worth code-splitting for a project this size.

## Integration (Phase 10)
- `frontend/scripts/integration-smoke-test.mjs` (run via
  `npm run test:integration`, requires the backend running) makes real
  HTTP requests using the same shapes as `frontend/src/services/api.ts`
  against a live backend, and validates response shapes against the
  TypeScript types' contract — 39/39 checks passing.
- **Caught a real bug**: `allow_credentials=True` combined with a
  wildcard CORS origin is contradictory per the CORS spec, and Starlette
  handled it inconsistently between preflight and simple requests. Fixed
  by setting `allow_credentials=False` (this app has no cookie-based
  auth to protect). See `docs/limitations.md` for the full story.
- Confirmed the production frontend build correctly bakes in the
  `VITE_API_BASE_URL` fallback at build time.
- A real browser click-through end-to-end still isn't verifiable in this
  sandbox (no browser automation available) — the contract-level check
  above is the strongest verification possible without one.

## Installation

### Start the full app on Windows

After the first-time setup below is complete, open PowerShell in the project
folder and run:

```powershell
.\start_inventoryai.ps1
```

The script checks PostgreSQL (and asks Docker Compose to start it if Docker is
available), applies any pending schema migrations, then starts the API and
website. It waits for the API health endpoint before reporting success. Open
`http://127.0.0.1:5173`; run `.\stop_inventoryai.ps1` to stop the API and
website started by the script. PostgreSQL stays running so the database
persists. Logs are saved under `.runtime/`.

The script does **not** clean, reload, or train the sample data. On a brand-new
database, complete the one-time clean/load/train steps below first. This avoids
overwriting products, stock changes, or sales you have entered.

### Prerequisites
- Python 3.11+ (developed/tested against 3.12)
- Node.js 18+ (for the frontend, Phase 9)
- PostgreSQL 15+ (or Docker)
- A Gemini API key from https://aistudio.google.com/app/apikey (recommended),
  or a Groq API key from https://console.groq.com/keys (optional — the system
  still answers supported questions with deterministic rules and templates if
  no model key is configured; see `docs/limitations.md`)

### Quick start (local Python + local/Docker Postgres)
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # set GEMINI_API_KEY and LLM_PROVIDER=gemini if available

# Start Postgres (either):
docker compose up -d postgres     # just the DB, via Docker
# ...or run a local PostgreSQL 15+ instance and update DATABASE_URL in .env

# One-time data pipeline + database setup:
python scripts/clean_data.py
python scripts/run_eda.py         # optional, writes charts to ml/eda/
cd backend && alembic upgrade head && cd ..
python scripts/load_database.py

# Train the forecasting models (writes to ml/artifacts/):
python ml/training/train_forecast.py

# Run the API:
cd backend && uvicorn app.main:app --reload
# -> http://localhost:8000/docs for interactive API docs
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local   # adjust VITE_API_BASE_URL if needed
npm run dev
# -> http://localhost:5173
```
The backend must be running (see above) for the frontend's data to load.

### Docker Compose (backend + Postgres)
```bash
docker compose up --build
```
**Note:** the backend image contains only `backend/` and `ml/` — it does
not include `scripts/` or the raw dataset. Run the data pipeline steps
above (clean → migrate → load → train) from your host machine against
the exposed Postgres port (`localhost:5432`) before or after `docker
compose up`; the backend container reads from the same database via the
Docker network. The `backend/Dockerfile` has not been build-tested in
this environment (no Docker available where this project was built) —
please verify with `docker compose up --build` and report back if
anything needs adjusting.

## Environment Variables
See `.env.example` for the full list with comments.

### Sign-in and deployment safety

The API now requires a bearer token for `/api/*` data routes (except the
health check and sign-in endpoint). The website shows a sign-in page, and
tokens expire after the configured lifetime. The starter setup has one
deployment-configured operator account; it does not provide user registration
or per-user roles yet. Keep the username/password and token secret in the
server's untracked `.env` (fill in the three blank `AUTH_*` fields before
signing in), and set `CORS_ALLOWED_ORIGINS` to the exact trusted
website origin(s), comma-separated. The API rejects `*`.

Before exposing the app online, use HTTPS, strong unique credentials, and a
random `AUTH_TOKEN_SECRET` of at least 32 characters. Do not commit `.env` or
share a common login with people who should have different permissions. For
multiple staff accounts and separate read-only/editor/admin roles, add a user
table and account-management workflow as the next step.

## Running the Application
```bash
cd backend && uvicorn app.main:app --reload
```
Then visit `http://localhost:8000/docs` for interactive API docs, or
`http://localhost:8000/api/health` for a basic health check.

## Real-Time Layer (Tier 1)

A live, streaming path sits alongside the REST API. Nothing in the analytical
path depends on it — it is an additive demo layer, off by default.

- **Streaming chat** — `WS /api/chat/ws`. Reports the pipeline as it runs
  (`analyzing_request` → `querying_database` → `phrasing_response`) and streams
  the LLM's phrasing token by token. Token frames are *provisional*; the final
  `chat_response` frame is authoritative and carries the same verified `data`
  the REST endpoint returns, so the no-hallucination guarantee is unchanged.
  The frontend falls back to `POST /api/chat` automatically if websockets are
  unavailable (`frontend/src/hooks/useChatStream.ts`).
- **Data simulator** — `POST /api/simulator/tick` runs one deterministic tick;
  `POST /api/simulator/start|stop` drive a background ticker. Events are
  sampled from the real per-(store, product) demand profile in Postgres.
- **Proactive alerts** — after each tick, stockout risk is recomputed with the
  same documented formula as `/api/stockout-risk`, projected forward with the
  live drawdown, and an alert is raised when risk crosses a threshold
  (`CRITICAL` / `WARNING`), with a cooldown so one condition is not re-announced
  every tick. Every number in an alert message comes from a query or that
  formula.
- **Live dashboard** — `WS /api/live/ws` pushes sales events and alerts to the
  React dashboard, which also shows open/critical alert counts and
  acknowledge buttons (`frontend/src/hooks/useLiveStream.ts`).

Isolation guarantee: live events are written to their own table
(`live_sales_events`) and never to `daily_sales` / `daily_inventory`, so the
history every model was trained and validated on stays byte-for-byte intact.
See `docs/limitations.md` for the honest scope of this layer (single-process
hub, synthetic live traffic, not part of any backtest).

### Live demo
```bash
# Terminal 1 — API
cd backend && python -m uvicorn app.main:app --reload

# Terminal 2 — drive the simulator (or use the dashboard buttons)
curl -X POST "http://localhost:8000/api/simulator/tick?events=3"
curl -X POST "http://localhost:8000/api/simulator/start?tick_seconds=3"
curl "http://localhost:8000/api/live/summary"
curl "http://localhost:8000/api/live/alerts?acknowledged=false"
```
Set `SIMULATOR_ENABLED=true` to have the ticker start with the API instead.

## Testing
```bash
pytest backend/tests/ tests/
```
138 tests passing: analytics services, ML artifacts, stockout/reorder, the
NLP/chat pipeline (rules + LLM fallback), conversation memory, full API
integration via FastAPI's TestClient, **WebSocket streaming chat**, and the
**real-time layer** (simulator, alert engine, live hub, live REST/WebSocket
endpoints).

## Limitations
See `docs/limitations.md` — covers synthetic-data caveats, the
Category/Region-not-a-stable-dimension finding, demand censoring near
stockouts, forecasting leakage-safety assumptions, the lead-time/
safety-stock assumptions, and the NLP network-testing limitation.

## Future Improvements
_(added in Phase 12)_
