"""
backend/app/schemas/watchlist.py

Watchlist wire format. The pinned flag is separate from the figures: the row
only records the pin, and every number below is recomputed per request from
the same services the Stockout / Reorder pages use, so a pin can never show a
stale value.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.stockout import RiskLevel


class WatchlistEntryResponse(BaseModel):
    product_id: str
    pinned_at: datetime
    note: str | None = None

    # Live figures, recomputed on read. `None` means "could not be computed".
    current_inventory: float | None = None
    risk: RiskLevel | None = None
    reason: str | None = None
    recommended_reorder_quantity: float | None = None
    lead_time_days: int | None = None


class WatchlistListResponse(BaseModel):
    entries: list[WatchlistEntryResponse]
    count: int


class WatchlistPinRequest(BaseModel):
    note: str | None = Field(None, max_length=500, description="Why this product is pinned")


class WatchlistNoteRequest(BaseModel):
    note: str | None = Field(None, max_length=500)