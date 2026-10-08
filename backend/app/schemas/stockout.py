"""backend/app/schemas/stockout.py"""

from datetime import date
from enum import Enum

from pydantic import BaseModel


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StockoutRiskResponse(BaseModel):
    product_id: str
    name: str
    sku: str
    category: str
    store_id: str | None = None
    as_of_date: date
    current_inventory: float
    lead_time_days: int
    forecast_model_horizon_used: int
    forecast_lead_time_demand: float
    safety_stock: float
    required_inventory: float
    risk: RiskLevel
    reason: str
