"""backend/app/schemas/reorder.py"""

from datetime import date

from pydantic import BaseModel


class ReorderResponse(BaseModel):
    product_id: str
    as_of_date: date
    current_inventory: float
    forecast_lead_time_demand: float
    safety_stock: float
    recommended_reorder_quantity: float
    assumptions: dict
