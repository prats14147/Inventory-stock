"""backend/app/nlp/entities.py"""

from pydantic import BaseModel


class Entities(BaseModel):
    product_id: str | None = None
    store_id: str | None = None
    category: str | None = None
    date: str | None = None
    date_range: dict | None = None
    forecast_horizon: int | None = None
