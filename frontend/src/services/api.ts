// frontend/src/services/api.ts
//
// Single dedicated API service layer.
// Components call functions exported here instead of calling fetch() directly.

import type {
  CurrentInventoryRow,
  LowStockResponse,
  ProductInventoryResponse,
  StockMovement,
} from "../types/inventory";

import type {
  BulkImportResponse,
  CategorySalesSummary,
  CloseSalesDayResponse,
  DailySaleRow,
  SalesSourcesSummaryResponse,
  SalesDayCoverageResponse,
  SalesTrendResponse,
  StoreProfitabilityResponse,
  StoreSalesSummary,
  TopProductsResponse,
} from "../types/sales";

import type { ForecastResponse } from "../types/forecast";

import type {
  RiskLevel,
  StockoutRiskResponse,
} from "../types/stockout";

import type { ReorderResponse } from "../types/reorder";

import type {
  ProductCostRow,
  ProductCostsResponse,
  ProductDetailResponse,
  ProductListResponse,
  ProductSummary,
} from "../types/product";

import type {
  ChatResponse,
  ChatSessionHistory,
  ChatSessionInfo,
} from "../types/chat";

import type {
  LiveSalesEvent,
  LiveSummary,
  SimulatorStatus,
  StockoutAlert,
} from "../types/live";

import type {
  AlertDigest,
  WatchlistEntry,
  WatchlistListResponse,
} from "../types/watchlist";

import type { DashboardSummary } from "../types/dashboard";

// -----------------------------------------------------------------------------
// Base configuration
// -----------------------------------------------------------------------------

// Prefer 127.0.0.1 over localhost on macOS because localhost may resolve to
// IPv6 while uvicorn is bound to IPv4.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "http://127.0.0.1:8000";

const AUTH_TOKEN_KEY = "inventoryai:access_token";

// -----------------------------------------------------------------------------
// Authentication
// -----------------------------------------------------------------------------

export function getAccessToken(): string | null {
  return typeof sessionStorage === "undefined"
    ? null
    : sessionStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAccessToken(
  token: string | null
): void {
  if (typeof sessionStorage !== "undefined") {
    if (token) {
      sessionStorage.setItem(
        AUTH_TOKEN_KEY,
        token
      );
    } else {
      sessionStorage.removeItem(
        AUTH_TOKEN_KEY
      );
    }
  }

  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new Event("inventoryai:auth-changed")
    );
  }
}

export class ApiError extends Error {
  status: number;

  constructor(
    status: number,
    message: string
  ) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

// -----------------------------------------------------------------------------
// Generic request helper
// -----------------------------------------------------------------------------

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  let res: Response;

  const headers = new Headers(
    options?.headers
  );

  headers.set(
    "Content-Type",
    "application/json"
  );

  const token = getAccessToken();

  if (token) {
    headers.set(
      "Authorization",
      `Bearer ${token}`
    );
  }

  try {
    res = await fetch(
      `${API_BASE_URL}${path}`,
      {
        ...options,
        headers,
      }
    );
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the InventoryAI API at ${API_BASE_URL}. Start the backend (python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) and PostgreSQL, then reload this page.`
    );
  }

  if (!res.ok) {
    if (
      res.status === 401 &&
      path !== "/api/auth/login"
    ) {
      setAccessToken(null);
    }

    let detail = res.statusText;

    try {
      const body = await res.json();

      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    } catch {
      // Response was not JSON.
    }

    throw new ApiError(
      res.status,
      detail
    );
  }

  return res.json() as Promise<T>;
}

// -----------------------------------------------------------------------------
// Query-string helper
// -----------------------------------------------------------------------------

function qs(
  params: Record<
    string,
    string | number | boolean | undefined
  >
): string {
  const filtered = Object.entries(
    params
  ).filter(
    ([, value]) =>
      value !== undefined &&
      value !== ""
  );

  if (filtered.length === 0) {
    return "";
  }

  return (
    "?" +
    new URLSearchParams(
      filtered.map(([key, value]) => [
        key,
        String(value),
      ])
    ).toString()
  );
}

// -----------------------------------------------------------------------------
// Authentication API
// -----------------------------------------------------------------------------

export const signIn = async (
  username: string,
  password: string
) => {
  const result = await request<{
    access_token: string;
    token_type: string;
    expires_in: number;
  }>(
    "/api/auth/login",
    {
      method: "POST",
      body: JSON.stringify({
        username,
        password,
      }),
    }
  );

  setAccessToken(
    result.access_token
  );

  return result;
};

export const getCurrentUser = () =>
  request<{
    username: string;
  }>("/api/auth/me");

// -----------------------------------------------------------------------------
// Products
// -----------------------------------------------------------------------------

export const getProducts = () =>
  request<ProductListResponse>(
    "/api/products"
  );

export const createProduct = (payload: {
  product_id?: string;
  name: string;
  sku: string;
  category: string;
  cost_price?: number;
}) =>
  request<ProductSummary>(
    "/api/products",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );

export const getProduct = (
  productId: string
) =>
  request<ProductDetailResponse>(
    `/api/products/${encodeURIComponent(
      productId
    )}`
  );

export const getProductCosts = () =>
  request<ProductCostsResponse>(
    "/api/products/costs"
  );

export const updateProductCost = (
  productId: string,
  cost_price: number
) =>
  request<ProductCostRow>(
    `/api/products/${encodeURIComponent(
      productId
    )}/cost`,
    {
      method: "PUT",
      body: JSON.stringify({
        cost_price,
      }),
    }
  );

// -----------------------------------------------------------------------------
// Inventory
// -----------------------------------------------------------------------------

export const getCurrentInventory = (
  params: {
    category?: string;
    region?: string;
  } = {}
) =>
  request<CurrentInventoryRow[]>(
    `/api/inventory${qs(params)}`
  );

export const saveInventory = (
  payload: {
    product_id: string;
    store_id: string;
    inventory_level: number;
    units_ordered: number;
    cost_price?: number;
    region?: string;
  }
) =>
  request<{
    date: string;
    product_id: string;
    store_id: string;
    inventory_level: number;
    units_ordered: number;
    created: boolean;
  }>(
    "/api/inventory",
    {
      method: "POST",
      body: JSON.stringify(
        payload
      ),
    }
  );

export const getProductInventory = (
  productId: string
) =>
  request<ProductInventoryResponse>(
    `/api/inventory/${encodeURIComponent(
      productId
    )}`
  );

export const getLowStock = (
  threshold?: number
) =>
  request<LowStockResponse>(
    `/api/inventory/low-stock${qs({
      threshold,
    })}`
  );

export const getStockMovements = (
  params: {
    product_id?: string;
    store_id?: string;
    movement_type?: string;
  } = {}
) =>
  request<StockMovement[]>(
    `/api/sales/stock-movements${qs(
      params
    )}`
  );

export const adjustInventory = (
  payload: {
    product_id: string;
    store_id: string;
    movement_type:
      | "DELIVERY"
      | "RETURN"
      | "MANUAL_CORRECTION";
    quantity_delta: number;
    reason: string;
  }
) =>
  request<{
    date: string;
    product_id: string;
    store_id: string;
    movement_type: string;
    quantity_delta: number;
    quantity_before: number;
    quantity_after: number;
    reason: string;
  }>(
    "/api/inventory/adjust",
    {
      method: "POST",
      body: JSON.stringify(
        payload
      ),
    }
  );

// -----------------------------------------------------------------------------
// Sales
// -----------------------------------------------------------------------------

export const getSales = (
  params: {
    product_id?: string;
    store_id?: string;
    category?: string;
    start_date?: string;
    end_date?: string;
    source?: string;
    genuine_only?: boolean;
    limit?: number;
    offset?: number;
  } = {}
) =>
  request<DailySaleRow[]>(
    `/api/sales${qs(params)}`
  );

export const exportSalesCsv = (
  params: {
    product_id?: string;
    store_id?: string;
    category?: string;
    start_date?: string;
    end_date?: string;
    source?: string;
    genuine_only?: boolean;
  } = {}
) => {
  const queryString = qs(params);

  const token =
    getAccessToken();

  const headers = new Headers();

  if (token) {
    headers.set(
      "Authorization",
      `Bearer ${token}`
    );
  }

  return fetch(
    `${API_BASE_URL}/api/sales/export/csv${queryString}`,
    {
      headers,
    }
  ).then(async (res) => {
    if (!res.ok) {
      let message =
        "Failed to export CSV";

      try {
        const body = await res.json();
        message =
          typeof body.detail === "string"
            ? body.detail
            : message;
      } catch {
        // Keep fallback message.
      }

      throw new ApiError(
        res.status,
        message
      );
    }

    return res.blob();
  });
};

export const recordSale = (
  payload: {
    product_id: string;
    store_id: string;
    units_sold: number;
    price: number;
    unit_cost?: number;
    category: string;
    region: string;
    date?: string;
  }
) =>
  request<{
    date: string;
    product_id: string;
    store_id: string;
    units_sold: number;
    daily_units_sold: number;
    remaining_inventory: number;
    unit_cost: number | null;
    gross_profit: number | null;
    source: string;
  }>(
    "/api/sales/record",
    {
      method: "POST",
      body: JSON.stringify(
        payload
      ),
    }
  );

export const bulkImportSales = (
  payload: {
    csv_content?: string;
    rows?: unknown[];
  }
) =>
  request<BulkImportResponse>(
    "/api/sales/bulk-import",
    {
      method: "POST",
      body: JSON.stringify(
        payload
      ),
    }
  );

export const closeSalesDay = (
  payload: {
    business_date: string;
    store_id: string;
  }
) =>
  request<CloseSalesDayResponse>(
    "/api/sales/close-day",
    {
      method: "POST",
      body: JSON.stringify(
        payload
      ),
    }
  );

export const getSalesDayCoverage = () =>
  request<SalesDayCoverageResponse>(
    "/api/sales/day-coverage"
  );

export const getSalesSourcesSummary = () =>
  request<SalesSourcesSummaryResponse>(
    "/api/sales/sources"
  );

export const getStoreProfitability = (
  params: {
    store_id?: string;
    product_id?: string;
    start_date?: string;
    end_date?: string;
  } = {}
) =>
  request<StoreProfitabilityResponse>(
    `/api/sales/profitability/by-store${qs(
      params
    )}`
  );

export const getTopProducts = (
  limit = 10,
  start_date?: string,
  end_date?: string,
  source?: string,
  genuine_only?: boolean
) =>
  request<TopProductsResponse>(
    `/api/sales/top-products${qs({
      limit,
      start_date,
      end_date,
      source,
      genuine_only,
    })}`
  );

export const getBottomProducts = (
  limit = 10,
  start_date?: string,
  end_date?: string,
  source?: string,
  genuine_only?: boolean
) =>
  request<TopProductsResponse>(
    `/api/sales/bottom-products${qs({
      limit,
      start_date,
      end_date,
      source,
      genuine_only,
    })}`
  );

export const getSalesTrend = (
  params: {
    granularity?:
      | "daily"
      | "weekly"
      | "monthly";
    product_id?: string;
    store_id?: string;
    category?: string;
    start_date?: string;
    end_date?: string;
    source?: string;
    genuine_only?: boolean;
  } = {}
) =>
  request<SalesTrendResponse>(
    `/api/sales/trends${qs(params)}`
  );

export const getSalesByCategory = (
  params: {
    source?: string;
    genuine_only?: boolean;
  } = {}
) =>
  request<CategorySalesSummary[]>(
    `/api/sales/by-category${qs(
      params
    )}`
  );

export const getSalesByStore = (
  params: {
    source?: string;
    genuine_only?: boolean;
  } = {}
) =>
  request<StoreSalesSummary[]>(
    `/api/sales/by-store${qs(
      params
    )}`
  );

// -----------------------------------------------------------------------------
// Forecast
// -----------------------------------------------------------------------------

export const getForecast = (
  productId: string,
  horizon?: number
) =>
  request<ForecastResponse>(
    `/api/forecast/${encodeURIComponent(
      productId
    )}${qs({
      horizon,
    })}`
  );

// -----------------------------------------------------------------------------
// Stockout risk
// -----------------------------------------------------------------------------

export interface RiskListParams {
  onlyAtRisk?: boolean;
  store_id?: string;
  search?: string;
  category?: string;
  limit?: number;
  offset?: number;
}

export const getStockoutRiskList = (
  onlyAtRiskOrParams:
    | boolean
    | RiskListParams = false
) => {
  const params: Record<
    string,
    string | number | boolean | undefined
  > =
    typeof onlyAtRiskOrParams ===
    "boolean"
      ? {
          only_at_risk:
            onlyAtRiskOrParams,
        }
      : {
          only_at_risk:
            onlyAtRiskOrParams.onlyAtRisk,
          store_id:
            onlyAtRiskOrParams.store_id,
          search:
            onlyAtRiskOrParams.search,
          category:
            onlyAtRiskOrParams.category,
          limit:
            onlyAtRiskOrParams.limit,
          offset:
            onlyAtRiskOrParams.offset,
        };

  return request<StockoutRiskResponse[]>(
    `/api/stockout-risk${qs(params)}`
  );
};

export const getStockoutRisk = (
  productId: string,
  leadTimeDays?: number,
  storeId?: string
) =>
  request<StockoutRiskResponse>(
    `/api/stockout-risk/${encodeURIComponent(
      productId
    )}${qs({
      lead_time_days:
        leadTimeDays,
      store_id: storeId,
    })}`
  );

// -----------------------------------------------------------------------------
// Reorder
// -----------------------------------------------------------------------------

export interface ReorderListParams {
  onlyNeeded?: boolean;
  store_id?: string;
  search?: string;
  category?: string;
  limit?: number;
  offset?: number;
}

export const getReorderList = (
  onlyNeededOrParams:
    | boolean
    | ReorderListParams = false
) => {
  const params: Record<
    string,
    string | number | boolean | undefined
  > =
    typeof onlyNeededOrParams ===
    "boolean"
      ? {
          only_needed:
            onlyNeededOrParams,
        }
      : {
          only_needed:
            onlyNeededOrParams.onlyNeeded,
          store_id:
            onlyNeededOrParams.store_id,
          search:
            onlyNeededOrParams.search,
          category:
            onlyNeededOrParams.category,
          limit:
            onlyNeededOrParams.limit,
          offset:
            onlyNeededOrParams.offset,
        };

  return request<ReorderResponse[]>(
    `/api/reorder${qs(params)}`
  );
};

export const getReorder = (
  productId: string,
  leadTimeDays?: number,
  storeId?: string
) =>
  request<ReorderResponse>(
    `/api/reorder/${encodeURIComponent(
      productId
    )}${qs({
      lead_time_days:
        leadTimeDays,
      store_id: storeId,
    })}`
  );

// -----------------------------------------------------------------------------
// Chat
// -----------------------------------------------------------------------------

export const postChat = (
  message: string,
  session_id?: string | null
) =>
  request<ChatResponse>(
    "/api/chat",
    {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id:
          session_id ?? null,
      }),
    }
  );

export const listChatSessions = (
  limit = 50
) =>
  request<{
    sessions: ChatSessionInfo[];
    total: number;
  }>(
    `/api/chat/sessions${qs({
      limit,
    })}`
  );

export const getChatSessionHistory = (
  sessionId: string
) =>
  request<ChatSessionHistory>(
    `/api/chat/sessions/${encodeURIComponent(
      sessionId
    )}/history`
  );

export const deleteChatSession = (
  sessionId: string
) =>
  request<{
    message: string;
    session_id: string;
  }>(
    `/api/chat/sessions/${encodeURIComponent(
      sessionId
    )}`,
    {
      method: "DELETE",
    }
  );

export const createChatSession = () =>
  request<{
    session_id: string;
    created_at: string;
  }>(
    "/api/chat/sessions",
    {
      method: "POST",
      body: JSON.stringify({}),
    }
  );

export const submitChatFeedback = (
  payload: {
    session_id: string;
    turn_index: number;
    helpful: boolean;
  }
) =>
  request<{
    session_id: string;
    turn_index: number;
    helpful: boolean;
    recorded: boolean;
  }>(
    "/api/chat/feedback",
    {
      method: "POST",
      body: JSON.stringify(
        payload
      ),
    }
  );

// -----------------------------------------------------------------------------
// Alerts / backend live endpoints
// -----------------------------------------------------------------------------
//
// These endpoints remain because Alerts still uses them.
// The Live page itself is no longer part of the frontend navigation.

export const getLiveSummary = () =>
  request<LiveSummary>(
    "/api/live/summary"
  );

export const getLiveEvents = (
  limit = 25
) =>
  request<{
    count: number;
    events: LiveSalesEvent[];
  }>(
    `/api/live/events${qs({
      limit,
    })}`
  );

export const getLiveAlerts = (
  acknowledged?: boolean,
  limit = 25
) =>
  request<{
    count: number;
    alerts: StockoutAlert[];
  }>(
    `/api/live/alerts${qs({
      acknowledged,
      limit,
    })}`
  );

export const acknowledgeAlert = (
  alertId: number
) =>
  request<StockoutAlert>(
    `/api/live/alerts/${alertId}/acknowledge`,
    {
      method: "POST",
    }
  );

export const getAlertDigest = (
  date?: string
) =>
  request<AlertDigest>(
    `/api/live/digest${qs({
      date,
    })}`
  );

// Keep simulator API exports so any old unused Live component/hook still
// type-checks. They are no longer exposed through the navigation UI.

export const getSimulatorStatus = () =>
  request<SimulatorStatus>(
    "/api/simulator/status"
  );

export const runSimulatorTick = (
  events?: number
) =>
  request<{
    tick_at: string;
    events: LiveSalesEvent[];
    alerts: StockoutAlert[];
    suppressed_alerts: number;
  }>(
    `/api/simulator/tick${qs({
      events,
    })}`,
    {
      method: "POST",
    }
  );

export const startSimulator = (
  tickSeconds?: number,
  eventsPerTick?: number
) =>
  request<
    { started: boolean } &
      SimulatorStatus
  >(
    `/api/simulator/start${qs({
      tick_seconds:
        tickSeconds,
      events_per_tick:
        eventsPerTick,
    })}`,
    {
      method: "POST",
    }
  );

export const stopSimulator = () =>
  request<
    { stopped: boolean } &
      SimulatorStatus
  >(
    "/api/simulator/stop",
    {
      method: "POST",
    }
  );

// -----------------------------------------------------------------------------
// CSV exports
// -----------------------------------------------------------------------------

function downloadBlob(
  filename: string,
  blob: Blob
): void {
  const url =
    URL.createObjectURL(blob);

  const link =
    document.createElement("a");

  link.href = url;
  link.download = filename;

  document.body.appendChild(link);
  link.click();

  document.body.removeChild(link);

  setTimeout(
    () => URL.revokeObjectURL(url),
    0
  );
}

async function fetchBlob(
  path: string
): Promise<Blob> {
  const token =
    getAccessToken();

  const headers =
    new Headers();

  if (token) {
    headers.set(
      "Authorization",
      `Bearer ${token}`
    );
  }

  let res: Response;

  try {
    res = await fetch(
      `${API_BASE_URL}${path}`,
      {
        headers,
      }
    );
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the InventoryAI API at ${API_BASE_URL}.`
    );
  }

  if (!res.ok) {
    throw new ApiError(
      res.status,
      "CSV export failed."
    );
  }

  return res.blob();
}

export const exportInventoryCsv =
  async (
    params: {
      category?: string;
      region?: string;
    } = {}
  ) => {
    const blob =
      await fetchBlob(
        `/api/inventory/export/csv${qs(
          params
        )}`
      );

    downloadBlob(
      `inventory-export-${new Date()
        .toISOString()
        .slice(
          0,
          10
        )}.csv`,
      blob
    );
  };

export const exportStockoutCsv = async (
  items: StockoutRiskResponse[]
) => {
  const {
    toCsv,
    downloadCsv,
  } = await import(
    "../lib/csv"
  );

  const headers = [
    "Product",
    "Name",
    "SKU",
    "Category",
    "Store",
    "Current inventory",
    "Forecast demand",
    "Safety stock",
    "Required",
    "Risk",
  ];

  downloadCsv(
    `stockout-risk-${new Date()
      .toISOString()
      .slice(
        0,
        10
      )}.csv`,
    toCsv(
      headers,
      items.map((r) => [
        r.product_id,
        r.name,
        r.sku,
        r.category,
        r.store_id ?? "all",
        r.current_inventory.toFixed(
          0
        ),
        r.forecast_lead_time_demand.toFixed(
          1
        ),
        r.safety_stock.toFixed(
          1
        ),
        r.required_inventory.toFixed(
          1
        ),
        r.risk,
      ])
    )
  );
};

// -----------------------------------------------------------------------------
// Dashboard
// -----------------------------------------------------------------------------

export const getDashboardSummary = () =>
  request<DashboardSummary>(
    "/api/dashboard/summary"
  );

// -----------------------------------------------------------------------------
// Morning briefing
// -----------------------------------------------------------------------------
//
// Kept for compatibility with any older component. The current Dashboard
// does not use it.

export interface BriefingRisk {
  product_id: string;
  name: string;
  risk: RiskLevel;
  current_inventory: number;
  required_inventory: number;
}

export interface BriefingSuggestion {
  product_id: string;
  name: string;
  risk: RiskLevel;
  suggested_quantity: number;
}

export interface MorningBriefing {
  headline: string;
  open_alerts: number;
  critical_alerts: number;
  top_risks: BriefingRisk[];
  suggested_orders: BriefingSuggestion[];
}

export const getMorningBriefing =
  () =>
    request<MorningBriefing>(
      "/api/briefing"
    );

// -----------------------------------------------------------------------------
// System settings
// -----------------------------------------------------------------------------

export interface SystemSettingMeta {
  value: number;
  source: string;
  default: number;
  description: string;
}

export interface SystemSettingsResponse {
  settings: Record<
    string,
    SystemSettingMeta
  >;
}

export const getSystemSettings =
  () =>
    request<SystemSettingsResponse>(
      "/api/settings"
    );

export const updateSystemSettings = (
  payload: {
    default_lead_time_days?: number;
    safety_stock_service_factor?: number;
    low_stock_threshold?: number;
  }
) =>
  request<SystemSettingsResponse>(
    "/api/settings",
    {
      method: "PUT",
      body: JSON.stringify(
        payload
      ),
    }
  );

// -----------------------------------------------------------------------------
// Model health / evaluation
// -----------------------------------------------------------------------------
//
// This stays in the backend for ML validation even though Model Health is
// removed from the navbar.

export interface ModelHorizonHealth {
  horizon_days: number;
  model: string;
  baseline: string;
  mae: number;
  rmse: number;
  smape: number;
  test_rows: number;
  baseline_mae: number;
  baseline_rmse: number;
  baseline_smape: number;
  improvement_pct_vs_baseline:
    | number
    | null;
  train_rows: number;
  val_rows: number;
  train_date_cutoff: string;
  val_date_cutoff: string;
  best_iteration: number;
  feature_count: number;
  feature_columns: string[];
}

export interface ModelHealthResponse {
  artifacts_dir: string;
  artifacts_found: boolean;
  horizons: ModelHorizonHealth[];
  note: string;
}

export const getModelHealth = () =>
  request<ModelHealthResponse>(
    "/api/model-health"
  );

// -----------------------------------------------------------------------------
// Purchase orders
// -----------------------------------------------------------------------------

export interface PurchaseOrder {
  id: number;
  product_id: string;
  store_id: string;
  quantity: number;
  status: string;
  note: string | null;
  created_at: string | null;
  received_at: string | null;
}

export const listPurchaseOrders = (
  status?: string
) =>
  request<{
    count: number;
    orders: PurchaseOrder[];
  }>(
    `/api/purchase-orders${qs({
      status,
    })}`
  );

export const createPurchaseOrder = (
  payload: {
    product_id: string;
    store_id: string;
    quantity: number;
    note?: string;
  }
) =>
  request<PurchaseOrder>(
    "/api/purchase-orders",
    {
      method: "POST",
      body: JSON.stringify(
        payload
      ),
    }
  );

export const receivePurchaseOrder = (
  id: number
) =>
  request<{
    order: PurchaseOrder;
    delivery: unknown;
  }>(
    `/api/purchase-orders/${id}/receive`,
    {
      method: "POST",
    }
  );

export const cancelPurchaseOrder = (
  id: number
) =>
  request<PurchaseOrder>(
    `/api/purchase-orders/${id}/cancel`,
    {
      method: "POST",
    }
  );

// -----------------------------------------------------------------------------
// Watchlist
// -----------------------------------------------------------------------------

export const getWatchlist = () =>
  request<WatchlistListResponse>(
    "/api/watchlist"
  );

export const getWatchlistIds = () =>
  request<{
    count: number;
    product_ids: string[];
  }>(
    "/api/watchlist/ids"
  );

export const pinProduct = (
  productId: string,
  note?: string
) =>
  request<WatchlistEntry>(
    `/api/watchlist/${encodeURIComponent(
      productId
    )}`,
    {
      method: "POST",
      body: JSON.stringify({
        note: note ?? null,
      }),
    }
  );

export const setWatchlistNote = (
  productId: string,
  note: string | null
) =>
  request<WatchlistEntry>(
    `/api/watchlist/${encodeURIComponent(
      productId
    )}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        note,
      }),
    }
  );

export const unpinProduct = (
  productId: string
) =>
  request<{
    unpinned: string;
  }>(
    `/api/watchlist/${encodeURIComponent(
      productId
    )}`,
    {
      method: "DELETE",
    }
  );

// -----------------------------------------------------------------------------
// WebSocket endpoints
// -----------------------------------------------------------------------------

// Kept for the old unused live-stream hook.
// It does not create a visible Live page.

export const liveStreamUrl = () =>
  `${API_BASE_URL.replace(
    /^http/,
    "ws"
  )}/api/live/ws`;

export const chatStreamUrl = (
  sessionId?: string | null
) => {
  const params =
    new URLSearchParams();

  if (sessionId) {
    params.set(
      "session_id",
      sessionId
    );
  }

  const query =
    params.toString();

  return `${API_BASE_URL.replace(
    /^http/,
    "ws"
  )}/api/chat/ws${
    query
      ? `?${query}`
      : ""
  }`;
};

export const websocketProtocols =
  () => {
    const token =
      getAccessToken();

    return token
      ? [
          "inventoryai",
          `bearer.${token}`,
        ]
      : ["inventoryai"];
  };