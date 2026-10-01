// frontend/src/types/forecast.ts

export interface StoreForecast {
  store_id: string;
  forecast_units: number;
}

export interface ForecastResponse {
  product_id: string;
  requested_horizon_days: number;
  model_horizon_days: number;
  target_date: string;
  forecast_total_units: number;
  per_store: StoreForecast[];
  model_test_mae: number;
}
