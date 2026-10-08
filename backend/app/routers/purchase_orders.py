"""backend/app/routers/purchase_orders.py

Draft purchase-order flow for the Reorder page:

  POST /api/purchase-orders            -- create a DRAFT from a reorder row.
                                         Reserves stock by bumping
                                         `units_ordered` on the day's
                                         inventory row.
  GET  /api/purchase-orders            -- list (newest first, optional status)
  POST /api/purchase-orders/{id}/receive  -- fulfill: converts into a DELIVERY
                                         stock adjustment via the same
                                         inventory_service.adjust_stock path
                                         (so the over-delivery guard applies).
  POST /api/purchase-orders/{id}/cancel   -- void: releases the reservation.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import Base, DailyInventory, PurchaseOrder
from app.repositories import inventory_repository, product_repository
from app.schemas.inventory import StockAdjustmentRequest
from app.services import inventory_service
from app.services.stockout_service import clear_risk_cache

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])

Base.metadata.create_all(bind=engine, tables=[PurchaseOrder.__table__])


class PurchaseOrderCreate(BaseModel):
    product_id: str
    store_id: str
    quantity: int = Field(gt=0, le=100000)
    note: str = ""


@router.get("")
def list_purchase_orders(
    status: str | None = Query(None, description="Filter by DRAFT, RECEIVED, or CANCELLED"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status.upper())
    orders = list(db.execute(stmt).scalars().all())
    return {"count": len(orders), "orders": [o.to_dict() for o in orders]}


@router.post("", status_code=201)
def create_purchase_order(payload: PurchaseOrderCreate, db: Session = Depends(get_db)) -> dict:
    if not product_repository.product_exists(db, payload.product_id):
        raise HTTPException(status_code=404, detail=f"Product '{payload.product_id}' was not found.")
    as_of = inventory_repository.get_latest_date(db)
    if as_of is None:
        raise HTTPException(status_code=404, detail="No inventory exists yet.")
    row = db.execute(
        select(DailyInventory).where(
            DailyInventory.date == as_of,
            DailyInventory.product_id == payload.product_id,
            DailyInventory.store_id == payload.store_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No inventory record for product {payload.product_id} at store {payload.store_id}.",
        )
    row.units_ordered += payload.quantity
    order = PurchaseOrder(
        product_id=payload.product_id,
        store_id=payload.store_id,
        quantity=payload.quantity,
        status="DRAFT",
        note=payload.note or f"Reorder for {payload.product_id} at {payload.store_id}",
        created_at=datetime.now(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    clear_risk_cache()
    return order.to_dict()


@router.post("/{order_id}/receive")
def receive_purchase_order(order_id: int, db: Session = Depends(get_db)) -> dict:
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Purchase order {order_id} not found.")
    if order.status != "DRAFT":
        raise HTTPException(status_code=400, detail=f"Order {order_id} is {order.status}, only DRAFT orders can be received.")
    adjustment = inventory_service.adjust_stock(
        db,
        StockAdjustmentRequest(
            product_id=order.product_id,
            store_id=order.store_id,
            movement_type="DELIVERY",
            quantity_delta=order.quantity,
            reason=f"PO #{order.id} received: {order.note}",
        ),
        source="purchase_order",
    )
    order.status = "RECEIVED"
    order.received_at = datetime.now()
    db.commit()
    db.refresh(order)
    return {"order": order.to_dict(), "delivery": adjustment.model_dump(mode="json")}


@router.post("/{order_id}/cancel")
def cancel_purchase_order(order_id: int, db: Session = Depends(get_db)) -> dict:
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Purchase order {order_id} not found.")
    if order.status != "DRAFT":
        raise HTTPException(status_code=400, detail=f"Order {order_id} is {order.status}, only DRAFT orders can be cancelled.")
    as_of = inventory_repository.get_latest_date(db)
    row = db.execute(
        select(DailyInventory).where(
            DailyInventory.date == as_of,
            DailyInventory.product_id == order.product_id,
            DailyInventory.store_id == order.store_id,
        )
    ).scalar_one_or_none()
    if row is not None:
        row.units_ordered = max(0, row.units_ordered - order.quantity)
    order.status = "CANCELLED"
    db.commit()
    db.refresh(order)
    clear_risk_cache()
    return order.to_dict()
