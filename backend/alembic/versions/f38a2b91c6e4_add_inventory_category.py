"""add an editable category to inventory snapshots

Revision ID: f38a2b91c6e4
Revises: b2c8e1f4a7d9
Create Date: 2026-10-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f38a2b91c6e4"
down_revision: Union[str, None] = "b2c8e1f4a7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("daily_inventory", sa.Column("category", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_inventory", "category")
