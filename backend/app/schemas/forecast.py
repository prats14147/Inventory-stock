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
