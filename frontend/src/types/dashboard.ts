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
  risk: RiskLevel;
  current_inventory: number;
  required_inventory: number;
  recommended_reorder_quantity: number;
  reason: string;
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
  category_sales: CategorySalesSummary[];
  top_products: ProductSalesRank[];
  /** Server-side cost of building the payload, in ms. */
  compute_ms: number;
  /** True when the risk rows came from the in-process cache. */
  served_from_cache: boolean;
}