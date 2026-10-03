// frontend/src/types/watchlist.ts
//
// The watchlist row only records that a product is pinned. Every figure below
// is recomputed server-side per request, so a pin can never show a stale value.

import type { RiskLevel } from "./stockout";

export interface WatchlistEntry {
  product_id: string;
  pinned_at: string;
  note: string | null;

  /** null when the product vanished from the source tables, or the
   *  forecast model could not score it. */
  current_inventory: number | null;
  risk: RiskLevel | null;
  reason: string | null;
  recommended_reorder_quantity: number | null;
  lead_time_days: number | null;
}

export interface WatchlistListResponse {
  entries: WatchlistEntry[];
  count: number;
}

/** One UTC day of alerts, rolled up per product. */
export interface AlertDigest {
  date: string;
  total_alerts: number;
  critical_alerts: number;
  warning_alerts: number;
  open_alerts: number;
  acknowledged_alerts: number;
  products_affected: number;
  products: Array<{
    product_id: string;
    alert_count: number;
    open_count: number;
    worst_severity: "CRITICAL" | "WARNING";
    first_alert_at: string;
    last_alert_at: string;
    projected_inventory: number;
    required_inventory: number;
    message: string;
  }>;
}