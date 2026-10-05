"""store product cost and transaction-level sale prices for profit reporting

Revision ID: e21d6f4a9c30
Revises: a1b2c3d4e5f6
Create Date: 2026-10-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e21d6f4a9c30"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("cost_price", sa.Float(), nullable=True))
    op.create_table(
        "sales_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(length=20), nullable=False),
        sa.Column("product_id", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("units_sold", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.store_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_transactions_business_date", "sales_transactions", ["business_date"])
    op.create_index("ix_sales_transactions_store_id", "sales_transactions", ["store_id"])
    op.create_index("ix_sales_transactions_product_id", "sales_transactions", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_sales_transactions_product_id", table_name="sales_transactions")
    op.drop_index("ix_sales_transactions_store_id", table_name="sales_transactions")
    op.drop_index("ix_sales_transactions_business_date", table_name="sales_transactions")
    op.drop_table("sales_transactions")
    op.drop_column("products", "cost_price")
