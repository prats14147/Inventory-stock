// frontend/src/types/reorder.ts

export interface ReorderResponse {
  product_id: string;
  name: string;
  sku: string;
  category: string;
  store_id: string | null;
  as_of_date: string;
  current_inventory: number;
  forecast_lead_time_demand: number;
  safety_stock: number;
  recommended_reorder_quantity: number;
  assumptions: Record<string, string | number>;
}
