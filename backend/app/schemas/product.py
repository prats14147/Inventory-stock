"""backend/app/schemas/product.py"""

from datetime import date

from pydantic import BaseModel
from pydantic import Field


class ProductListResponse(BaseModel):
    product_ids: list[str]
    count: int


class ProductDetailResponse(BaseModel):
    product_id: str
    as_of_date: date
    current_total_inventory: int
    total_units_sold_all_time: int
    cost_price: float | None = None


class ProductCostRow(BaseModel):
    product_id: str
    cost_price: float | None


class ProductCostsResponse(BaseModel):
    products: list[ProductCostRow]


class ProductCostUpdateRequest(BaseModel):
    cost_price: float = Field(ge=0)
