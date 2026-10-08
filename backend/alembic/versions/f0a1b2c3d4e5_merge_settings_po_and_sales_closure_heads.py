"""merge settings/purchase-orders and sales-closure heads

Revision ID: f0a1b2c3d4e5
Revises: e8f1c2a3b4d5, 72ad19cf30ab
"""

from typing import Sequence, Union


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = (
    "e8f1c2a3b4d5",
    "72ad19cf30ab",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
