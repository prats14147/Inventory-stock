"""add sales source column to daily_sales

Revision ID: a1b2c3d4e5f6
Revises: 92a7de31c0bf
Create Date: 2026-10-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "92a7de31c0bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_sales",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="Sample Data"),
    )
    op.create_index(op.f("ix_daily_sales_source"), "daily_sales", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_daily_sales_source"), table_name="daily_sales")
    op.drop_column("daily_sales", "source")
