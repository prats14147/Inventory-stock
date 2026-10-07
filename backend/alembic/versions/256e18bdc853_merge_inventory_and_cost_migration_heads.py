"""merge inventory and cost migration heads

Revision ID: 256e18bdc853
Revises: a6ffa36d9cbf, c7d8a9e4f201
Create Date: 2026-10-06 07:46:44.308991

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '256e18bdc853'
down_revision: Union[str, None] = ('a6ffa36d9cbf', 'c7d8a9e4f201')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
