// frontend/src/types/chat.ts
// Kept in sync with backend/app/schemas/chat.py and app/nlp/intent.py

export type Intent =
  | "CURRENT_STOCK"
  | "LOW_STOCK"
  | "TOP_SELLING"
  | "BOTTOM_SELLING"
  | "SALES_TREND"
  | "PRODUCT_INFO"
  | "DEMAND_FORECAST"
  | "STOCKOUT_RISK"
  | "REORDER_RECOMMENDATION"
  | "CATEGORY_ANALYSIS"
  | "STORE_ANALYSIS"
  | "HELP"
  | "UNKNOWN";

export interface Entities {
  product_id: string | null;
  store_id: string | null;
  category: string | null;
  date: string | null;
  date_range: Record<string, string> | null;
  forecast_horizon: number | null;
}

export interface ChatRequest {
  message: string;
}

export interface ChatResponse {
  message: string;
  intent: Intent;
  entities: Entities;
  parse_method: "rules" | "llm";
  data: Record<string, unknown> | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}
