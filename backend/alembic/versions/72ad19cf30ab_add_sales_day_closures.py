"""add per-store daily sales completeness confirmations

Revision ID: 72ad19cf30ab
Revises: 3d9f6a8b1c42, e356cee24ac5
Create Date: 2026-10-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "72ad19cf30ab"
down_revision: Union[str, Sequence[str], None] = ("3d9f6a8b1c42", "e356cee24ac5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Also reconcile the two equivalent merge heads present in some clones,
    # while adding the new table as their single downstream head.
    op.create_table(
        "sales_day_closures",
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.String(length=20), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.store_id"]),
        sa.PrimaryKeyConstraint("business_date", "store_id"),
    )


def downgrade() -> None:
    op.drop_table("sales_day_closures")
