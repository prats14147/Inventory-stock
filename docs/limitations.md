# Limitations

This file is expanded as each phase surfaces new caveats. Phase 2 (EDA)
findings below; ML/forecasting and stockout/reorder sections are added in
their respective phases.

## Dataset realism (from EDA, Phase 2)

- **Sales appear largely synthetic/randomly generated rather than
  price-driven.** Correlation between `Units Sold` and `Price` is ~0.001,
  and between `Units Sold` and `Discount` is ~0.003 -- essentially zero.
  Average sales are also nearly identical whether a promotion is active or
  not. A forecasting model trained on this data will likely find price,
  discount, and promotion weak predictors -- this is a property of the
  dataset, not a modeling failure.
- **Sales volumes are nearly uniform across products, categories, and
  stores** (all within a few percent of each other), which further
  suggests the generating process was closer to uniform-random than to a
  realistic demand simulation tied to product/category identity.
- **`Units Sold` is capped by `Inventory Level`.** The scatter plot of
  Inventory vs. Sales shows a hard upper-boundary (Units Sold never
  exceeds Inventory Level except in the 369 flagged edge-case rows), and
  the two are correlated at ~0.59. This means observed sales in
  low-inventory periods may understate true demand (demand censoring) --
  relevant to both the forecasting model and the stockout-risk logic
  built in later phases.
- **369 rows (~0.505%) have `Units Sold >= Inventory Level`.** These are
  treated as flagged edge cases (`possible_stock_constrained` column),
  not confirmed stockouts -- the data doesn't distinguish "demand exactly
  met supply" from "demand exceeded supply and was constrained."

## Forecasting feature design and results (Phase 5)

**Leakage-safety assumptions, stated explicitly:**
- Lag/rolling features (`lag_1/7/14`, `rolling_mean/std_7/14`) use only
  `Units Sold` up to and including the forecast origin date T -- never
  from T or later relative to the target.
- Target-date (T+h) calendar features (day of week, month, week of year,
  weekend) are always legitimately knowable in advance.
- The sample does not provide a planned future price/promotion calendar.
  Training, validation, test, and live inference therefore carry forward
  the latest known `Price`, `Discount`, `Holiday/Promotion`, and `Competitor
  Pricing` values. Actual future-row values are not used as model inputs.
- `Inventory Level` uses **only the origin-date (T) value** -- the
  target-date value depends on events between T and T+h that aren't
  knowable at forecast time, so using it would be leakage.
- `Category`, `Region`, `Weather Condition`, and `Seasonality` are not
  stable per-entity or even per-date in this dataset (every date has rows
  spanning all 4 seasons and all weather conditions -- see the Database
  Design section above). Only origin-date (last-known) values are used as
  features; they are not expected to carry meaningful signal for the
  target date; they're included to satisfy the spec's feature list, not
  because they help.
- The existing `Demand Forecast` column from the source data is never
  used as a feature (guarded by an automated test).

**Results (test set, chronologically held out -- Oct 2023 onward):**

| Horizon | Baseline (7-day MA) MAE | XGBoost MAE | Improvement |
|---|---|---|---|
| 7 days  | 93.4 | 88.5 | ~5.2% |
| 14 days | 92.8 | 88.5 | ~4.7% |

The improvement over the naive baseline is real but modest, and sMAPE is
high (~72-74%) at both horizons. Feature importances are nearly uniform
across all ~30 features (0.035-0.044 each, XGBoost's default gain
metric) -- no feature dominates. This is consistent with the EDA finding
that `Units Sold` in this dataset correlates near-zero with price,
discount, and promotion: **the underlying data has limited genuinely
learnable signal**, so a much stronger result would be a red flag for
leakage rather than a sign of a better model. This should be stated
plainly to any reader of the forecasting results, not glossed over.

## Stockout risk / reorder engine assumptions (Phase 6)

- **Product-level, not per-store.** Inventory, forecast demand, and
  safety stock are all aggregated across the 5 stores for a given
  product. This matches how the master spec's own chatbot examples talk
  about a product ("P0001 currently has 50 units... reorder ~95 units")
  -- they don't reference a specific store. Per-store inventory detail
  remains available separately via `InventoryService` (Phase 4) if
  finer-grained decisions are ever needed.
- **No real supplier lead time exists in this dataset.** `lead_time_days`
  always comes from the configurable `DEFAULT_LEAD_TIME_DAYS` setting
  (default 7) unless explicitly overridden, and every stockout-risk /
  reorder response echoes this assumption back explicitly rather than
  applying it silently.
- **Lead-time demand approximation.** The trained forecasting models
  (Phase 5) predict a single day's demand at a specific horizon (7 or 14
  days ahead), not a cumulative sum over an arbitrary window. The model's
  product-wide prediction for the target date is already a daily rate, so
  total lead-time demand is approximated as
  `forecast_total_units * lead_time_days`. This assumes a near-constant
  daily demand rate across the window -- a simplification, not a per-day
  recursive forecast.
- **Safety stock formula**: `demand_std * SAFETY_STOCK_SERVICE_FACTOR`,
  where `demand_std` is the standard deviation of the product's total
  historical daily sales (summed across stores) over the full 2-year
  history, and the service factor (default 1.65) is a configurable
  knob, not a globally optimal value -- this is an analytical
  recommendation, not a claim of optimal inventory policy.
- **Risk tiers** (HIGH / MEDIUM / LOW) come directly from comparing
  current inventory against `forecast_lead_time_demand` and
  `forecast_lead_time_demand + safety_stock` -- verified across all 20
  real products to actually produce all three tiers (not a formula that
  always returns the same answer).
- **"As of" date** is the latest date in the data (2024-01-01), same
  convention as Phase 4's "current inventory" -- see the EDA section
  above.

## NLP / chatbot design (Phase 7)

- The chatbot uses deterministic rules first for common questions and
  safety-sensitive stock actions. For wording the rules do not recognize,
  the configured Gemini or Groq model returns a structured choice from the
  allowlisted capabilities in `app/nlp/tool_registry.py`; execution remains
  in the explicit backend service map in `chat_service.py`.
- Questions about how the app works can retrieve relevant passages from
  checked-in README, data, and limitations documentation. It shows the
  supporting sections and does not browse the web or scan arbitrary files.
- Invalid model JSON, unknown tools, and malformed entity objects are
  discarded. Product/store IDs and date filters are taken from deterministic
  extraction or conversation context, not invented planner arguments. The
  final model wording is discarded if it introduces numeric values absent
  from the verified backend result; deterministic templates then answer.
- Read questions cover stock, sales trends, net revenue, gross profit/loss
  by product/store/category, forecasts, stockout risk, reorder, and
  category/store summaries. Relative and named month/date ranges are parsed
  before querying. A composite tool combines low-stock items with sales
  velocity over the latest 30 days in the available sales history.
- Net revenue uses recorded units, listed prices, and discounts. Gross
  profit/loss uses sale-level unit-cost snapshots; imported history without
  costs is excluded. This is not net accounting profit because operating
  expenses are not tracked.
- Customer sales, received stock, and non-sale adjustments are distinct.
  Chat prepares previews and requires confirmation before changing stock;
  damage/receiving movements do not create sales or revenue records.
- Capability coverage is bounded by the registry and stored data. Products
  can be named by catalog name, SKU (exact or fuzzy, see
  `app/nlp/catalog_resolve.py`), or P-code; genuinely ambiguous references
  ("wireless" matches two products) are clarified, never guessed. Ambiguous or
  unsupported questions should be clarified. The model cannot run arbitrary
  SQL or safely perform unconfirmed actions.

## Product cost and store gross profit

- `products.cost_price` is the current default cost for future recorded
  sales. Each manually recorded sale also saves its own unit selling price,
  discount, and unit-cost snapshot in `sales_transactions`; later catalog
  cost edits do not rewrite earlier transaction costs.
- The profitability report groups recorded sale transactions by store and
  compares discounted revenue with the known cost of goods sold. It reports
  cost coverage and leaves profit unknown when there are no known costs.
- Existing imported `daily_sales` records remain useful for sales analysis,
  but their prices are aggregate source values and they have no cost
  snapshots. The app does not guess their profit retroactively.

## Frontend (Phase 9)

- **Two more stray files caught at the start of this phase** (a schema
  and four router files referencing a function — `inventory_service.
  get_product_info` — that doesn't exist anywhere in the actual,
  tested codebase). Deleted rather than built upon, same as the
  `build_features.py` stray file caught in Phase 6.
- React + TypeScript + Vite + Tailwind, with TypeScript types in
  `frontend/src/types/` kept in sync field-for-field with the backend's
  Pydantic schemas (spec section 45), and all HTTP calls routed through
  a single API service layer (`frontend/src/services/api.ts`, spec
  section 44) — no component calls `fetch()` directly.
- **What was actually verified, and what wasn't**: `npm install`,
  `tsc -b` (strict mode), and `vite build` all ran for real in this
  sandbox and succeeded — including confirming Tailwind emitted real
  utility CSS (not an empty stylesheet) and that the dev server serves
  the app over HTTP. What could **not** be verified here is a live
  browser click-through (no browser automation available in this
  environment) — layout, interactivity, and the chatbot's actual
  rendering should be checked once you run `npm run dev` yourself.
- One honest fix made along the way: the initial `package.json` included
  a `lint` script pointing at an eslint config that was never actually
  installed — removed rather than left as a broken command.
- Known, disclosed trade-off: the production bundle is ~570KB
  (170KB gzipped) — Vite's own build output flags this as larger than
  its default 500KB warning threshold, mainly due to Recharts. Not
  fixed, since code-splitting isn't necessary for a project this size,
  but noted here rather than silently ignored.

## Integration (Phase 10)

- **A real bug was caught here, not just simulated**: the backend's CORS
  config combined `allow_credentials=True` with a wildcard
  `allow_origins=["*"]` — a contradictory configuration the CORS spec
  forbids (browsers refuse to combine credentialed requests with a
  wildcard origin). Starlette's `CORSMiddleware` handled this
  inconsistently: preflight (`OPTIONS`) requests echoed back the specific
  origin, but simple `GET` requests returned a literal `*` alongside
  `allow-credentials: true` — a combination real browsers reject for
  credentialed fetches. This app doesn't use cookie-based auth at all,
  so the fix was to set `allow_credentials=False`, which resolves the
  contradiction and makes the two response types consistent. Caught by
  `frontend/scripts/integration-smoke-test.mjs` testing a plain `GET`
  with an `Origin` header, not just the preflight the Phase 8 test
  happened to check.
- **What "integration" means for this project, concretely**: a Node
  script (`frontend/scripts/integration-smoke-test.mjs`, run via
  `npm run test:integration`) makes real HTTP requests to a live running
  backend using the exact same request shapes as
  `frontend/src/services/api.ts`, and validates the response shapes
  against what the TypeScript types promise. This is a genuinely
  different check from the backend's own pytest suite (which verifies
  backend correctness in isolation) — it verifies the *contract* between
  the two halves actually matches. Run with Postgres + the backend both
  live: 39/39 checks passing.
- **Also verified**: the production frontend bundle correctly bakes in
  the `VITE_API_BASE_URL` fallback at build time (confirmed the literal
  string appears in the built JS), so a production build without a
  `.env.local` override still points at the right default.
- **Still not verifiable in this sandbox**: a real browser loading the
  built frontend and clicking through to the backend end-to-end (no
  browser automation available here — see the Phase 9 note). The
  contract-level check above is the strongest verification possible
  without one.

## Category and Region are not stable dimensions (from Database load, Phase 3)

- The master spec assumes `Category` is a fixed attribute of `Product ID`
  and `Region` is a fixed attribute of `Store ID` (normalized into
  `products`/`stores` dimension tables). **This does not hold in the real
  data**: every one of the 20 products appears under all 5 categories
  across different rows (roughly 700-750 rows each), and every one of the
  5 stores appears under all 4 regions. There is no stable
  product-to-category or store-to-region mapping to normalize.
- Rather than picking an arbitrary "primary" category/region per product/
  store (which would silently discard most of the data, violating the
  no-silent-discard rule from Phase 2), `products` and `stores` were kept
  as pure identity tables, and `category`/`region` were stored as
  row-level attributes on `daily_sales` instead. `daily_inventory` can
  still be joined to `daily_sales` on the shared `(date, store_id,
  product_id)` key whenever category/region context is needed for
  inventory-side analysis (verified working in Phase 3).
- Practical implication: "the category of product P0001" is not a
  well-defined question in this dataset -- only "the category P0001 was
  sold under on a given date" is.

## Real-time layer (Tier 1) -- scope and honest limits

- **The live traffic is synthetic, and says so.** `live_sales_events` rows are
  generated by `app/services/simulator_service.py` (`source="simulator"`), not
  observed from any real store. They are sampled from the real per-(store,
  product) demand profile in Postgres so the numbers move plausibly, but they
  are a demo device.
- **Live events are excluded from every backtest and metric.** They are written
  to their own table and never to `daily_sales`/`daily_inventory`; no Phase 4-9
  service, feature builder, or trained model reads them. Forecast/model metrics
  in `ml/artifacts/` were computed before this layer existed and do not include
  any of it.
- **Alert severity is a threshold rule, not a calibrated probability.** It is
  `projected_inventory < forecast_lead_time_demand` → CRITICAL, else
  `projected_inventory < required_inventory` → WARNING, where
  `projected_inventory = last recorded inventory − live units sold since that
  record`, and `required_inventory` is the documented
  lead-time-demand + safety-stock formula. It inherits every caveat of the
  stockout engine (forecast error, the configured lead time, and the assumption
  that the last recorded inventory is still the shelf count).
- **The live hub is single-process.** `app/services/live_hub.py` fans frames out
  to subscribers in the current process, which matches this app's deployment
  shape (one uvicorn worker). Running multiple workers would give each worker
  its own subscriber set; a production version would publish through Redis
  pub/sub (or Postgres `LISTEN/NOTIFY`) instead. The hub is intentionally tiny
  so that swap stays local to one file.
- **A slow subscriber loses its oldest frames** (bounded buffer) rather than
  stalling the simulator. Every frame is persisted to Postgres first, so the
  REST endpoints and the reconnect backlog remain complete.
- **No browser-based verification of the streaming UI.** The WebSocket
  endpoints are verified end-to-end with real clients (pytest TestClient and a
  `websockets` client against a live uvicorn process), and the frontend
  type-checks and builds -- but, as with the Phase 9 note above, there is no
  browser automation in this sandbox to click through the streamed UI.

