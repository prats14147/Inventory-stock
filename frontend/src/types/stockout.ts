// frontend/src/types/stockout.ts

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface StockoutRiskResponse {
  product_id: string;
  name: string;
  sku: string;
  category: string;
  store_id: string | null;
  as_of_date: string;
  current_inventory: number;
  lead_time_days: number;
  forecast_model_horizon_used: number;
  forecast_lead_time_demand: number;
  safety_stock: number;
  required_inventory: number;
  risk: RiskLevel;
  reason: string;
}
