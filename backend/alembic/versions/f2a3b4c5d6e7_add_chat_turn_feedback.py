"""add feedback column to conversation_turns (Upgrade #5)

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("conversation_turns")}


def upgrade() -> None:
    if "feedback" not in _columns():
        op.add_column(
            "conversation_turns",
            sa.Column("feedback", sa.String(length=10), nullable=True),
        )


def downgrade() -> None:
    if "feedback" in _columns():
        op.drop_column("conversation_turns", "feedback")
