// frontend/src/types/inventory.ts
// Kept in sync with backend/app/schemas/inventory.py

export interface CurrentInventoryRow {
  date: string;
  store_id: string;
  product_id: string;
  inventory_level: number;
  units_ordered: number;
  category: string;
  region: string;
}

export interface StoreInventory {
  store_id: string;
  inventory_level: number;
  units_ordered: number;
}

export interface ProductInventoryResponse {
  product_id: string;
  as_of_date: string;
  total_inventory: number;
  stores: StoreInventory[];
}

export interface LowStockItem {
  date: string;
  store_id: string;
  product_id: string;
  category: string;
  region: string;
  inventory_level: number;
  units_ordered: number;
}

export interface LowStockResponse {
  as_of_date: string;
  threshold: number;
  items: LowStockItem[];
  count: number;
}
