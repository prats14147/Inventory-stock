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

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
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

// --- Chat ---
export const postChat = (message: string) =>
  request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify({ message }) });
