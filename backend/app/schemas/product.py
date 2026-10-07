"""backend/app/schemas/product.py"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ProductSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    name: str
    sku: str
    category: str


class ProductListResponse(BaseModel):
    product_ids: list[str]
    products: list[ProductSummary]
    count: int


class ProductDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    name: str
    sku: str
    category: str
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

class ProductCreateRequest(BaseModel):
    product_id: str | None = None
    name: str = Field(min_length=1, max_length=100)
    sku: str = Field(min_length=1, max_length=50)
    category: str = Field(min_length=1, max_length=50)
    cost_price: float | None = Field(default=None, ge=0)
