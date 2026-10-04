from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class StockMovementResponse(BaseModel):
    id: int
    occurred_at: datetime
    business_date: date
    store_id: str
    product_id: str
    movement_type: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reason: str
    source: str

    model_config = ConfigDict(from_attributes=True)