"""restore daily sales provenance column when schema drifted

Revision ID: 3d9f6a8b1c42
Revises: 256e18bdc853
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "3d9f6a8b1c42"
down_revision: Union[str, None] = "256e18bdc853"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("daily_sales")}
    if "source" not in columns:
        op.add_column(
            "daily_sales",
            sa.Column(
                "source",
                sa.String(length=50),
                nullable=False,
                server_default="Sample Data",
            ),
        )

    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("daily_sales")}
    if "ix_daily_sales_source" not in indexes:
        op.create_index("ix_daily_sales_source", "daily_sales", ["source"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("daily_sales")}
    if "ix_daily_sales_source" in indexes:
        op.drop_index("ix_daily_sales_source", table_name="daily_sales")

    columns = {column["name"] for column in inspector.get_columns("daily_sales")}
    if "source" in columns:
        op.drop_column("daily_sales", "source")
