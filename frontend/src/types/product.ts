// frontend/src/types/product.ts

export interface ProductListResponse {
  product_ids: string[];
  count: number;
}

export interface ProductDetailResponse {
  product_id: string;
  as_of_date: string;
  current_total_inventory: number;
  total_units_sold_all_time: number;
  cost_price: number | null;
}

export interface ProductCostRow {
  product_id: string;
  cost_price: number | null;
}

export interface ProductCostsResponse {
  products: ProductCostRow[];
}
