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
    predicted_units_on_target_date: float
    prediction_semantics: str
    # Retained for existing frontend/API clients; this is still a point
    # prediction, despite the legacy field name.
    forecast_total_units: float
    per_store: list[StoreForecast]
    model_test_mae: float
    baseline_mae: float = 0.0
    data_source: str = "Synthetic Sample Dataset (2022-2024)"
    is_synthetic_model: bool = True
    baseline_improvement_pct: float = 0.0
    warning: str = (
        "This is a single-day prediction at the target date, not cumulative demand over the selected horizon. "
        "The model was trained on synthetic sample data (2022-2024); its holdout error is large and its improvement "
        "over simple moving-average baselines is modest. Genuine recorded sales are not used to train this model."
    )

