"""add system_settings and purchase_orders tables

Revision ID: e8f1c2a3b4d5
Revises: d9e1f2a3b4c5
Create Date: 2026-10-07

Idempotent: routers also ensure these tables via create_all, so this
migration skips anything that already exists (existing databases).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f1c2a3b4d5"
down_revision: Union[str, Sequence[str], None] = "d9e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "system_settings" not in _tables():
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("updated_by", sa.String(length=100), nullable=False, server_default="admin"),
            sa.PrimaryKeyConstraint("key"),
        )
    if "purchase_orders" not in _tables():
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("product_id", sa.String(length=20), nullable=False),
            sa.Column("store_id", sa.String(length=20), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("received_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
            sa.ForeignKeyConstraint(["store_id"], ["stores.store_id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    if "purchase_orders" in _tables():
        op.drop_table("purchase_orders")
    if "system_settings" in _tables():
        op.drop_table("system_settings")
