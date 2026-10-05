"""merge product catalog and stock movement heads

Revision ID: a6ffa36d9cbf
Revises: 0ab8b7d097ac, b7c9d2e4f6a8
Create Date: 2026-10-06 01:24:47.413709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6ffa36d9cbf'
down_revision: Union[str, None] = ('0ab8b7d097ac', 'b7c9d2e4f6a8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
