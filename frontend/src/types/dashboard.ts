// frontend/src/types/dashboard.ts
//
// One-shot dashboard payload (Tier A). Replaces five parallel requests on
// mount, three of which each ran the stockout engine over every product.

import type { CategorySalesSummary, ProductSalesRank } from "./sales";
import type { RiskLevel } from "./stockout";

export interface DashboardRiskCounts {
  high: number;
  medium: number;
  low: number;
  at_risk: number;
}

export interface NeedsAttentionItem {
  product_id: string;
  name: string;
  sku: string;
  category: string;
  risk: RiskLevel;
  current_inventory: number;
  required_inventory: number;
  recommended_reorder_quantity: number;
  reason: string;
}

export interface LowStockItem {
  product_id: string;
  name: string;
  sku: string;
  category: string;
  store_id: string;
  inventory_level: number;
  threshold: number;
}

export interface SalesSparklinePoint {
  date: string;
  units_sold: number;
}

export interface StockMovementFeedItem {
  product_id: string;
  name: string;
  store_id: string;
  movement_type: string;
  quantity_delta: number;
  quantity_before: number;
  quantity_after: number;
  reason: string;
  occurred_at: string;
}

export interface DashboardSummary {
  as_of_date: string | null;
  product_count: number;
  store_count: number;
  total_inventory_units: number;
  low_stock_count: number;
  low_stock_threshold: number;
  risk_counts: DashboardRiskCounts;
  needs_attention: NeedsAttentionItem[];
  low_stock_preview: LowStockItem[];
  sales_sparkline: SalesSparklinePoint[];
  stock_movements_feed: StockMovementFeedItem[];
  category_sales: CategorySalesSummary[];
  top_products: ProductSalesRank[];
  /** Server-side cost of building the payload, in ms. */
  compute_ms: number;
  /** True when the risk rows came from the in-process cache. */
  served_from_cache: boolean;
}