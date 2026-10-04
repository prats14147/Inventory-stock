// frontend/src/services/api.ts
//
// Single dedicated API service layer (spec section 44) -- components
// never call fetch() directly, they call functions exported here.

import type { CurrentInventoryRow, LowStockResponse, ProductInventoryResponse } from "../types/inventory";
import type {
  CategorySalesSummary,
  DailySaleRow,
  SalesTrendResponse,
  StoreSalesSummary,
  TopProductsResponse,
} from "../types/sales";
import type { ForecastResponse } from "../types/forecast";
import type { StockoutRiskResponse } from "../types/stockout";
import type { ReorderResponse } from "../types/reorder";
import type { ProductDetailResponse, ProductListResponse } from "../types/product";
import type { ChatResponse } from "../types/chat";
import type { ChatSessionHistory, ChatSessionInfo } from "../types/chat";
import type { LiveSalesEvent, LiveSummary, SimulatorStatus, StockoutAlert } from "../types/live";
import type { AlertDigest, WatchlistEntry, WatchlistListResponse } from "../types/watchlist";
import type { DashboardSummary } from "../types/dashboard";

// Prefer 127.0.0.1 over "localhost": on macOS the browser often resolves
// localhost to IPv6 (::1) while uvicorn is bound to IPv4 only, which looks
// like "the API is down" even when the backend is running.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the InventoryAI API at ${API_BASE_URL}. Start the backend (python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) and PostgreSQL, then reload this page.`
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // response wasn't JSON -- fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const filtered = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (filtered.length === 0) return "";
  return "?" + new URLSearchParams(filtered.map(([k, v]) => [k, String(v)])).toString();
}

// --- Products ---
export const getProducts = () => request<ProductListResponse>("/api/products");
export const getProduct = (productId: string) => request<ProductDetailResponse>(`/api/products/${productId}`);

// --- Inventory ---
export const getCurrentInventory = (params: { category?: string; region?: string } = {}) =>
  request<CurrentInventoryRow[]>(`/api/inventory${qs(params)}`);
export const getProductInventory = (productId: string) =>
  request<ProductInventoryResponse>(`/api/inventory/${productId}`);
export const getLowStock = (threshold?: number) =>
  request<LowStockResponse>(`/api/inventory/low-stock${qs({ threshold })}`);

// --- Sales ---
export const getSales = (
  params: {
    product_id?: string;
    store_id?: string;
    category?: string;
    start_date?: string;
    end_date?: string;
    limit?: number;
  } = {}
) => request<DailySaleRow[]>(`/api/sales${qs(params)}`);

export const getTopProducts = (limit = 10, start_date?: string, end_date?: string) =>
  request<TopProductsResponse>(`/api/sales/top-products${qs({ limit, start_date, end_date })}`);

export const getBottomProducts = (limit = 10, start_date?: string, end_date?: string) =>
  request<TopProductsResponse>(`/api/sales/bottom-products${qs({ limit, start_date, end_date })}`);

export const getSalesTrend = (
  params: {
    granularity?: "daily" | "weekly" | "monthly";
    product_id?: string;
    store_id?: string;
    category?: string;
    start_date?: string;
    end_date?: string;
  } = {}
) => request<SalesTrendResponse>(`/api/sales/trends${qs(params)}`);

export const getSalesByCategory = () => request<CategorySalesSummary[]>("/api/sales/by-category");
export const getSalesByStore = () => request<StoreSalesSummary[]>("/api/sales/by-store");

// --- Forecast ---
export const getForecast = (productId: string, horizon?: number) =>
  request<ForecastResponse>(`/api/forecast/${productId}${qs({ horizon })}`);

// --- Stockout risk ---
export const getStockoutRiskList = (onlyAtRisk = false) =>
  request<StockoutRiskResponse[]>(`/api/stockout-risk${qs({ only_at_risk: onlyAtRisk })}`);
export const getStockoutRisk = (productId: string, leadTimeDays?: number) =>
  request<StockoutRiskResponse>(`/api/stockout-risk/${productId}${qs({ lead_time_days: leadTimeDays })}`);

// --- Reorder ---
export const getReorderList = (onlyNeeded = false) =>
  request<ReorderResponse[]>(`/api/reorder${qs({ only_needed: onlyNeeded })}`);
export const getReorder = (productId: string, leadTimeDays?: number) =>
  request<ReorderResponse>(`/api/reorder/${productId}${qs({ lead_time_days: leadTimeDays })}`);

// --- Chat (Phase 11 conversation memory + Tier 1 streaming) ---
export const postChat = (message: string, session_id?: string | null) =>
  request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify({ message, session_id: session_id ?? null }) });

export const listChatSessions = (limit = 50) =>
  request<{ sessions: ChatSessionInfo[]; total: number }>(`/api/chat/sessions${qs({ limit })}`);

export const getChatSessionHistory = (sessionId: string) =>
  request<ChatSessionHistory>(`/api/chat/sessions/${sessionId}/history`);

export const deleteChatSession = (sessionId: string) =>
  request<{ message: string; session_id: string }>(`/api/chat/sessions/${sessionId}`, { method: "DELETE" });

export const createChatSession = () =>
  request<{ session_id: string; created_at: string }>("/api/chat/sessions", { method: "POST", body: JSON.stringify({}) });

// --- Live / real-time (Tier 1) ---
export const getLiveSummary = () => request<LiveSummary>("/api/live/summary");
export const getLiveEvents = (limit = 25) =>
  request<{ count: number; events: LiveSalesEvent[] }>(`/api/live/events${qs({ limit })}`);
export const getLiveAlerts = (acknowledged?: boolean, limit = 25) =>
  request<{ count: number; alerts: StockoutAlert[] }>(`/api/live/alerts${qs({ acknowledged, limit })}`);
export const acknowledgeAlert = (alertId: number) =>
  request<StockoutAlert>(`/api/live/alerts/${alertId}/acknowledge`, { method: "POST" });

/** Everything that fired on one UTC day, rolled up per product. */
export const getAlertDigest = (date?: string) =>
  request<AlertDigest>(`/api/live/digest${qs({ date })}`);

export const getSimulatorStatus = () => request<SimulatorStatus>("/api/simulator/status");
export const runSimulatorTick = (events?: number) =>
  request<{ tick_at: string; events: LiveSalesEvent[]; alerts: StockoutAlert[]; suppressed_alerts: number }>(
    `/api/simulator/tick${qs({ events })}`,
    { method: "POST" }
  );
export const startSimulator = (tickSeconds?: number, eventsPerTick?: number) =>
  request<{ started: boolean } & SimulatorStatus>(
    `/api/simulator/start${qs({ tick_seconds: tickSeconds, events_per_tick: eventsPerTick })}`,
    { method: "POST" }
  );
export const stopSimulator = () =>
  request<{ stopped: boolean } & SimulatorStatus>("/api/simulator/stop", { method: "POST" });

// --- Dashboard (Tier A) ---
/** The whole dashboard in one request. Replaces five parallel calls. */
export const getDashboardSummary = () => request<DashboardSummary>("/api/dashboard/summary");

// --- Watchlist (pinned products) ---
export const getWatchlist = () => request<WatchlistListResponse>("/api/watchlist");

/** Cheap "is this pinned?" check -- returns just the ids, no live figures. */
export const getWatchlistIds = () =>
  request<{ count: number; product_ids: string[] }>("/api/watchlist/ids");

export const pinProduct = (productId: string, note?: string) =>
  request<WatchlistEntry>(`/api/watchlist/${encodeURIComponent(productId)}`, {
    method: "POST",
    body: JSON.stringify({ note: note ?? null }),
  });

export const setWatchlistNote = (productId: string, note: string | null) =>
  request<WatchlistEntry>(`/api/watchlist/${encodeURIComponent(productId)}`, {
    method: "PATCH",
    body: JSON.stringify({ note }),
  });

export const unpinProduct = (productId: string) =>
  request<{ unpinned: string }>(`/api/watchlist/${encodeURIComponent(productId)}`, { method: "DELETE" });

/**
 * WebSocket endpoints derived from the same base URL, so a deployment that
 * points VITE_API_BASE_URL at a real host still gets websockets from it
 * (http->ws, https->wss).
 */
export const liveStreamUrl = () => `${API_BASE_URL.replace(/^http/, "ws")}/api/live/ws`;
export const chatStreamUrl = (sessionId?: string | null) => {
  const base = `${API_BASE_URL.replace(/^http/, "ws")}/api/chat/ws`;
  return sessionId ? `${base}?session_id=${encodeURIComponent(sessionId)}` : base;
};
