// frontend/src/types/sales.ts
// Kept in sync with backend/app/schemas/sales.py

export interface DailySaleRow {
  date: string;
  store_id: string;
  product_id: string;
  category: string;
  region: string;
  units_sold: number;
  price: number;
  discount: number;
  holiday_promotion: boolean;
  weather_condition: string;
  competitor_pricing: number;
  seasonality: string;
}

export interface ProductSalesRank {
  product_id: string;
  total_units_sold: number;
}

export interface TopProductsResponse {
  start_date: string | null;
  end_date: string | null;
  limit: number;
  products: ProductSalesRank[];
}

export interface SalesTrendPoint {
  period: string;
  total_units_sold: number;
}

export interface SalesTrendResponse {
  granularity: "daily" | "weekly" | "monthly";
  filters: Record<string, string | null>;
  points: SalesTrendPoint[];
}

export interface CategorySalesSummary {
  category: string;
  total_units_sold: number;
}

export interface StoreSalesSummary {
  store_id: string;
  total_units_sold: number;
}

export interface StoreProfitability {
  store_id: string;
  transaction_count: number;
  units_sold: number;
  units_with_cost: number;
  units_without_cost: number;
  cost_coverage_percent: number;
  net_sales_revenue: number;
  costed_net_revenue: number;
  known_cost_of_goods_sold: number;
  gross_profit_or_loss: number | null;
  gross_margin_percent: number | null;
  condition: "unknown" | "profit" | "loss" | "break_even";
}

export interface StoreProfitabilityResponse {
  items: StoreProfitability[];
  filters: Record<string, string | null>;
  cost_note: string;
}
