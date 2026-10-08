"""merge stock movement and cost/catalog heads

Revision ID: d9e1f2a3b4c5
Revises: a6ffa36d9cbf, c7d8a9e4f201
"""

from typing import Sequence, Union


revision: str = "d9e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = (
    "a6ffa36d9cbf",
    "c7d8a9e4f201",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
