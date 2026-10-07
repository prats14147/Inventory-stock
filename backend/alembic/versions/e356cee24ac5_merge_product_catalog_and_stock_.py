"""merge product catalog and stock movement and cost heads

Revision ID: e356cee24ac5
Revises: a6ffa36d9cbf, c7d8a9e4f201
Create Date: 2026-10-07 18:47:37.900667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e356cee24ac5'
down_revision: Union[str, None] = ('a6ffa36d9cbf', 'c7d8a9e4f201')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
