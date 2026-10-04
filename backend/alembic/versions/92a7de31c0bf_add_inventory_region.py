"""add an editable region to inventory snapshots

Revision ID: 92a7de31c0bf
Revises: f38a2b91c6e4
Create Date: 2026-10-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "92a7de31c0bf"
down_revision: Union[str, None] = "f38a2b91c6e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("daily_inventory", sa.Column("region", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_inventory", "region")
