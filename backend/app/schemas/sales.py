"""backend/app/schemas/sales.py"""

from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field


class DailySaleRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date_type
    store_id: str
    product_id: str
    category: str
    region: str
    units_sold: int
    price: float
    discount: int
    holiday_promotion: bool
    weather_condition: str
    competitor_pricing: float
    seasonality: str


class ProductSalesRank(BaseModel):
    product_id: str
    total_units_sold: int


class TopProductsResponse(BaseModel):
    start_date: date_type | None
    end_date: date_type | None
    limit: int
    products: list[ProductSalesRank]


class SalesTrendPoint(BaseModel):
    period: date_type
    total_units_sold: int


class SalesTrendResponse(BaseModel):
    granularity: str
    filters: dict
    points: list[SalesTrendPoint]


class CategorySalesSummary(BaseModel):
    category: str
    total_units_sold: int


class StoreSalesSummary(BaseModel):
    store_id: str
    total_units_sold: int


class SalesRecord(BaseModel):
    date: date_type
    store_id: str
    product_id: str
    category: str
    region: str
    units_sold: int
    price: float
    discount: int
    holiday_promotion: bool


class RecordSaleRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=20)
    store_id: str = Field(min_length=1, max_length=20)
    units_sold: int = Field(gt=0)
    price: float = Field(ge=0)
    category: str = Field(min_length=1, max_length=50)
    region: str = Field(min_length=1, max_length=50)
    date: date_type | None = None
    discount: int = Field(default=0, ge=0, le=100)
    holiday_promotion: bool = False
    weather_condition: str = Field(default="Unknown", max_length=30)
    competitor_pricing: float | None = Field(default=None, ge=0)
    seasonality: str = Field(default="Unknown", max_length=20)


class RecordSaleResponse(BaseModel):
    date: date_type
    product_id: str
    store_id: str
    units_sold: int
    daily_units_sold: int
    remaining_inventory: int


class SalesListResponse(BaseModel):
    items: list[SalesRecord]
    count: int
    limit: int
    offset: int
