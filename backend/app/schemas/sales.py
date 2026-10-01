"""backend/app/schemas/sales.py"""

from datetime import date

from pydantic import BaseModel, ConfigDict


class DailySaleRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
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
    start_date: date | None
    end_date: date | None
    limit: int
    products: list[ProductSalesRank]


class SalesTrendPoint(BaseModel):
    period: date
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
    date: date
    store_id: str
    product_id: str
    category: str
    region: str
    units_sold: int
    price: float
    discount: int
    holiday_promotion: bool


class SalesListResponse(BaseModel):
    items: list[SalesRecord]
    count: int
    limit: int
    offset: int
