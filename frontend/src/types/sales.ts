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
