"""merge inventory and profitability heads

Revision ID: 01f668d4130e
Revises: a6ffa36d9cbf, c7d8a9e4f201
Create Date: 2026-10-06 07:49:26.006032

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01f668d4130e'
down_revision: Union[str, None] = ('a6ffa36d9cbf', 'c7d8a9e4f201')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
