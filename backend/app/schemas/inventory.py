"""backend/app/schemas/inventory.py"""

from datetime import date

from pydantic import BaseModel, ConfigDict


class CurrentInventoryRow(BaseModel):
    date: date
    store_id: str
    product_id: str
    inventory_level: int
    units_ordered: int
    category: str
    region: str


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
