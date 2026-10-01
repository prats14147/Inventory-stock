"""backend/app/schemas/product.py"""

from datetime import date

from pydantic import BaseModel


class ProductListResponse(BaseModel):
    product_ids: list[str]
    count: int


class ProductDetailResponse(BaseModel):
    product_id: str
    as_of_date: date
    current_total_inventory: int
    total_units_sold_all_time: int
