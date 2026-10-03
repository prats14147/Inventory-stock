"""
backend/app/repositories/watchlist_repository.py

Queries for the pinned-products watchlist. Kept out of the router, matching the
other repositories in this package.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WatchlistItem


def list_items(db: Session) -> list[WatchlistItem]:
    """Newest pin first."""
    stmt = select(WatchlistItem).order_by(WatchlistItem.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def get_item(db: Session, product_id: str) -> WatchlistItem | None:
    return db.get(WatchlistItem, product_id)


def is_pinned(db: Session, product_id: str) -> bool:
    return db.get(WatchlistItem, product_id) is not None


def pinned_ids(db: Session) -> set[str]:
    # Selecting a single column means scalars() yields the raw values, not
    # model instances -- so no `.product_id` on each element.
    return set(db.execute(select(WatchlistItem.product_id)).scalars().all())


def add_item(db: Session, product_id: str, now: datetime, note: str | None = None) -> WatchlistItem:
    """Pin a product. Idempotent: pinning twice keeps the original pin time."""
    existing = db.get(WatchlistItem, product_id)
    if existing is not None:
        return existing
    item = WatchlistItem(product_id=product_id, created_at=now, note=note)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def remove_item(db: Session, product_id: str) -> bool:
    """Unpin a product. Returns False when it was not pinned."""
    item = db.get(WatchlistItem, product_id)
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True


def set_note(db: Session, product_id: str, note: str | None) -> WatchlistItem | None:
    item = db.get(WatchlistItem, product_id)
    if item is None:
        return None
    item.note = note
    db.commit()
    db.refresh(item)
    return item