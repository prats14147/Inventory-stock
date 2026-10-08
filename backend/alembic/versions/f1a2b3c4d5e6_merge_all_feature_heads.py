"""merge aayushma inventory merge and combined feature heads

Revision ID: f1a2b3c4d5e6
Revises: 01f668d4130e, f0a1b2c3d4e5
"""

from typing import Sequence, Union


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = (
    "01f668d4130e",
    "f0a1b2c3d4e5",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
