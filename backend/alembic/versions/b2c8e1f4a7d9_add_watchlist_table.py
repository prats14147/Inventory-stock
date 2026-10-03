"""add watchlist table (pinned products)

Revision ID: b2c8e1f4a7d9
Revises: d4e5f6a7b8c9
Create Date: 2026-10-02 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c8e1f4a7d9'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'watchlist',
        sa.Column('product_id', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
        sa.PrimaryKeyConstraint('product_id'),
    )


def downgrade() -> None:
    op.drop_table('watchlist')