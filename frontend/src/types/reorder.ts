// frontend/src/types/reorder.ts

export interface ReorderResponse {
  product_id: string;
  as_of_date: string;
  current_inventory: number;
  forecast_lead_time_demand: number;
  safety_stock: number;
  recommended_reorder_quantity: number;
  assumptions: Record<string, string | number>;
}
