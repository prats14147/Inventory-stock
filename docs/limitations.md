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
- Target-date `Price`, `Discount`, `Holiday/Promotion`, and `Competitor
  Pricing` are used **under the assumption that pricing/promotion
  calendars are planned ahead of the forecast horizon** -- standard
  retail-forecasting practice, but an assumption, not a fact verified in
  this data.
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
  days ahead), not a cumulative sum over an arbitrary window. Total
  demand over the lead-time window is approximated as
  `forecast_daily_rate * lead_time_days`, where `forecast_daily_rate` is
  the model's predicted total for the nearest trained horizon divided by
  that horizon. This assumes a near-constant daily demand rate across the
  window -- a simplification, not a per-day recursive forecast.
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

- **Hybrid architecture, genuinely hybrid**: a rule-based (regex/keyword)
  intent+entity extractor is the PRIMARY layer — deterministic, free, and
  always available. The LLM (Groq) is only consulted when the rules
  return `UNKNOWN`, and only for phrasing the final response when
  available. Verified: for every one of the spec's example test
  questions (section 49), the rule-based layer alone classifies
  correctly — the system does not depend on the LLM being reachable to
  answer any of them.
- **This sandbox cannot reach `api.groq.com`** (its network allowlist
  doesn't include it), so the real Groq call could not be tested live
  from here. To handle this honestly rather than skip testing entirely:
  the LLM sits behind a small `complete_json`/`complete_text` interface,
  and the whole pipeline (JSON parsing, entity validation, malicious/
  unexpected-key stripping, graceful fallback on failure) is tested with
  a `FakeLLMClient` returning canned responses. **You should smoke-test
  the real `GroqClient` once you have a real `GROQ_API_KEY` set** —
  everything else has been verified against the live database.
- **No-hallucination policy is structural, not just a prompt
  instruction**: every product-requiring intent checks
  `product_repository.product_exists` against the real database *before*
  any tool runs — an unknown product always gets a fixed "not found"
  message, never a fabricated number (tested for P9999). LLM JSON output
  is parsed and filtered against the known `Entities` fields — an
  injected/unexpected key (tested with a simulated `"malicious_field"`)
  is silently dropped, never trusted.
- **Deterministic template fallback**: every intent has a hand-written
  template formatter, used whenever no LLM client is passed or the LLM
  call fails. This means the system produces a legitimate, data-grounded
  answer with zero network dependency — the LLM only ever makes the
  phrasing nicer, never supplies facts.
- 27 new tests passing (rule-based classification across all spec
  example questions, LLM-fallback pipeline via fake client, and the full
  chat pipeline against the live database) — 56/56 across the whole
  project.

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
