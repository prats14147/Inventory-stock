export interface ProductSummary {
  product_id: string;
  name: string;
  sku: string;
  category: string;
}

export interface ProductListResponse {
  product_ids: string[];
  products: ProductSummary[];
  count: number;
}

export interface ProductDetailResponse {
  product_id: string;
  name: string;
  sku: string;
  category: string;
  as_of_date: string;
  current_total_inventory: number;
  total_units_sold_all_time: number;
}
