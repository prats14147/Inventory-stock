"""backend/app/schemas/inventory.py"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CurrentInventoryRow(BaseModel):
    date: date
    store_id: str
    product_id: str
    inventory_level: int
    units_ordered: int
    category: str
    region: str


class InventoryUpsertRequest(BaseModel):
    """Create a product/store stock record or update its current quantity."""

    product_id: str = Field(min_length=1, max_length=20)
    store_id: str = Field(min_length=1, max_length=20)
    inventory_level: int = Field(ge=0)
    units_ordered: int = Field(default=0, ge=0)
    cost_price: float | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    region: str | None = Field(default=None, min_length=1, max_length=50)


class InventoryUpsertResponse(BaseModel):
    date: date
    product_id: str
    store_id: str
    inventory_level: int
    units_ordered: int
    created: bool


class StoreInventory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: str
    inventory_level: int
    units_ordered: int


class ProductInventoryResponse(BaseModel):
    """Current inventory for one product, broken down by store."""

    product_id: str
    as_of_date: date
    total_inventory: int
    stores: list[StoreInventory]


class LowStockItem(BaseModel):
    date: date
    store_id: str
    product_id: str
    category: str
    region: str
    inventory_level: int
    units_ordered: int


class LowStockResponse(BaseModel):
    as_of_date: date
    threshold: int
    items: list[LowStockItem]
    count: int


class CurrentInventoryItem(BaseModel):
    date: date
    store_id: str
    product_id: str
    category: str
    region: str
    inventory_level: int
    units_ordered: int


class CurrentInventoryListResponse(BaseModel):
    as_of_date: date | None
    items: list[CurrentInventoryItem]
    count: int


class StockAdjustmentRequest(BaseModel):
    """Request to record a delivery, return, or manual stock correction."""

    product_id: str = Field(min_length=1, max_length=20)
    store_id: str = Field(min_length=1, max_length=20)
    movement_type: str = Field(min_length=1, max_length=30)
    quantity_delta: int
    reason: str = Field(min_length=1, max_length=500)


class StockAdjustmentResponse(BaseModel):
    """Result of a stock adjustment, including the before/after quantities."""

    date: date
    product_id: str
    store_id: str
    movement_type: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reason: str
