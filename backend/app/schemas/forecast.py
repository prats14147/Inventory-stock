"""backend/app/schemas/forecast.py"""

from datetime import date

from pydantic import BaseModel, ConfigDict


class ForecastRequest(BaseModel):
    product_id: str
    horizon: int | None = None


class StoreForecast(BaseModel):
    store_id: str
    forecast_units: float


class ForecastResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    product_id: str
    requested_horizon_days: int
    model_horizon_days: int
    target_date: date
    forecast_total_units: float
    per_store: list[StoreForecast]
    model_test_mae: float
    data_source: str = "Synthetic Sample Dataset (2022-2024)"
    is_synthetic_model: bool = True
    baseline_improvement_pct: float = 5.2
    warning: str = (
        "Predictions are generated from an XGBoost model trained on the synthetic sample dataset (2022-2024). "
        "The model only outperforms its baseline by approximately 5% according to project notes. "
        "Genuine sales are kept separate from synthetic data to prevent misleading forecasts."
    )

