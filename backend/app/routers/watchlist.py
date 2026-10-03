"""
backend/app/routers/watchlist.py

Pinned-products watchlist:

  * GET    /api/watchlist                -- pinned products + live figures
  * GET    /api/watchlist/ids            -- just the ids (cheap "is pinned" check)
  * POST   /api/watchlist/{product_id}   -- pin
  * PATCH  /api/watchlist/{product_id}   -- edit the note
  * DELETE /api/watchlist/{product_id}   -- unpin

Every figure on a pinned entry is recomputed per request by the same
stockout/reorder services the dedicated pages use -- the pin stores no numbers.
If a product was pinned and later disappears from the source tables, the entry
still lists (so the user can see and unpin it) but its figures come back null
instead of raising.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import product_repository, watchlist_repository
from app.schemas.watchlist import (
    WatchlistEntryResponse,
    WatchlistListResponse,
    WatchlistNoteRequest,
    WatchlistPinRequest,
)
from app.services import reorder_service, stockout_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])
log = logging.getLogger("watchlist")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _build_entry(db: Session, item) -> WatchlistEntryResponse:
    """Attach live risk/reorder figures to one pinned row.

    Failures are swallowed on purpose: a watchlist is a navigation aid, and one
    product the forecast model can't score should not blank the whole page.
    """
    entry = WatchlistEntryResponse(
        product_id=item.product_id,
        pinned_at=item.created_at,
        note=item.note,
    )
    try:
        risk = stockout_service.calculate_stockout_risk(db, item.product_id)
        entry.current_inventory = risk.current_inventory
        entry.risk = risk.risk
        entry.reason = risk.reason
        entry.lead_time_days = risk.lead_time_days
    except NotFoundError:
        log.warning("Watchlist entry %s no longer exists in the source tables", item.product_id)
        return entry
    except Exception:  # noqa: BLE001
        log.exception("Could not compute stockout risk for pinned product %s", item.product_id)
    try:
        reorder = reorder_service.calculate_reorder(db, item.product_id)
        entry.recommended_reorder_quantity = reorder.recommended_reorder_quantity
    except NotFoundError:
        pass
    except Exception:  # noqa: BLE001
        log.exception("Could not compute reorder quantity for pinned product %s", item.product_id)
    return entry


@router.get("", response_model=WatchlistListResponse)
def list_watchlist(db: Session = Depends(get_db)) -> WatchlistListResponse:
    entries = [_build_entry(db, item) for item in watchlist_repository.list_items(db)]
    return WatchlistListResponse(entries=entries, count=len(entries))


@router.get("/ids")
def list_watchlist_ids(db: Session = Depends(get_db)) -> dict:
    """Cheap endpoint the pin buttons call to render their filled/empty state."""
    ids = sorted(watchlist_repository.pinned_ids(db))
    return {"count": len(ids), "product_ids": ids}


@router.post("/{product_id}", response_model=WatchlistEntryResponse, status_code=201)
def pin_product(
    product_id: str,
    payload: WatchlistPinRequest | None = None,
    db: Session = Depends(get_db),
) -> WatchlistEntryResponse:
    # Fail loudly on an unknown product -- a silent pin would hide a typo.
    if product_id not in set(product_repository.list_product_ids(db)):
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    item = watchlist_repository.add_item(
        db, product_id, _utcnow(), note=payload.note if payload else None
    )
    return _build_entry(db, item)


@router.patch("/{product_id}", response_model=WatchlistEntryResponse)
def update_note(
    product_id: str,
    payload: WatchlistNoteRequest,
    db: Session = Depends(get_db),
) -> WatchlistEntryResponse:
    item = watchlist_repository.set_note(db, product_id, payload.note)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{product_id} is not on the watchlist")
    return _build_entry(db, item)


@router.delete("/{product_id}")
def unpin_product(product_id: str, db: Session = Depends(get_db)) -> dict:
    if not watchlist_repository.remove_item(db, product_id):
        raise HTTPException(status_code=404, detail=f"{product_id} is not on the watchlist")
    return {"unpinned": product_id}