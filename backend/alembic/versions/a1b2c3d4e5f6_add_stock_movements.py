"""add stock movement history

Revision ID: b7c9d2e4f6a8
Revises: a1b2c3d4e5f6
Create Date: 2026-10-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c9d2e4f6a8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Older app versions created this table from ORM metadata before Alembic
    # became its source of truth. Adopt that existing table instead of
    # failing with DuplicateTable, and add any missing indexes.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("stock_movements"):
        op.create_table(
            "stock_movements",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("business_date", sa.Date(), nullable=False),
            sa.Column("store_id", sa.String(length=20), nullable=False),
            sa.Column("product_id", sa.String(length=20), nullable=False),
            sa.Column("movement_type", sa.String(length=30), nullable=False),
            sa.Column("quantity_delta", sa.Integer(), nullable=False),
            sa.Column("quantity_before", sa.Integer(), nullable=False),
            sa.Column("quantity_after", sa.Integer(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
            sa.ForeignKeyConstraint(["store_id"], ["stores.store_id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    expected_indexes = {
        "ix_stock_movements_product_time": ["product_id", "occurred_at"],
        "ix_stock_movements_store_product": ["store_id", "product_id"],
        "ix_stock_movements_type": ["movement_type"],
    }
    existing_indexes = {index["name"] for index in inspector.get_indexes("stock_movements")}
    for name, columns in expected_indexes.items():
        if name not in existing_indexes:
            op.create_index(name, "stock_movements", columns)


def downgrade() -> None:
    op.drop_index(
        "ix_stock_movements_type",
        table_name="stock_movements",
    )
    op.drop_index(
        "ix_stock_movements_store_product",
        table_name="stock_movements",
    )
    op.drop_index(
        "ix_stock_movements_product_time",
        table_name="stock_movements",
    )
    op.drop_table("stock_movements")
