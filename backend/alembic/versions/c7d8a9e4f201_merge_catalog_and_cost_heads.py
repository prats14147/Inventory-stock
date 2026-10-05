"""merge product catalog and cost migration heads

Revision ID: c7d8a9e4f201
Revises: e21d6f4a9c30, 0ab8b7d097ac
"""

from typing import Sequence, Union


revision: str = "c7d8a9e4f201"
down_revision: Union[str, Sequence[str], None] = (
    "e21d6f4a9c30",
    "0ab8b7d097ac",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
