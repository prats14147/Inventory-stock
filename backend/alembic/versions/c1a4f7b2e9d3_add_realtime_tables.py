"""add realtime tables (live sales events + stockout alerts)

Revision ID: c1a4f7b2e9d3
Revises: ef7f2d944d29
Create Date: 2026-10-01 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a4f7b2e9d3'
branch_labels: Union[str, Sequence[str], None] = None
down_revision: Union[str, None] = 'ef7f2d944d29'
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'live_sales_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_time', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.String(length=20), nullable=False),
        sa.Column('product_id', sa.String(length=20), nullable=False),
        sa.Column('units_sold', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_live_sales_events_product_time', 'live_sales_events', ['product_id', 'event_time']
    )
    op.create_index('ix_live_sales_events_time', 'live_sales_events', ['event_time'])

    op.create_table(
        'stockout_alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('product_id', sa.String(length=20), nullable=False),
        sa.Column('severity', sa.String(length=10), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('current_inventory', sa.Float(), nullable=False),
        sa.Column('live_units_sold', sa.Float(), nullable=False),
        sa.Column('projected_inventory', sa.Float(), nullable=False),
        sa.Column('forecast_lead_time_demand', sa.Float(), nullable=False),
        sa.Column('required_inventory', sa.Float(), nullable=False),
        sa.Column('lead_time_days', sa.Integer(), nullable=False),
        sa.Column('acknowledged', sa.Boolean(), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('trigger', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_stockout_alerts_product_created', 'stockout_alerts', ['product_id', 'created_at']
    )
    op.create_index('ix_stockout_alerts_acknowledged', 'stockout_alerts', ['acknowledged'])


def downgrade() -> None:
    op.drop_index('ix_stockout_alerts_acknowledged', table_name='stockout_alerts')
    op.drop_index('ix_stockout_alerts_product_created', table_name='stockout_alerts')
    op.drop_table('stockout_alerts')

    op.drop_index('ix_live_sales_events_time', table_name='live_sales_events')
    op.drop_index('ix_live_sales_events_product_time', table_name='live_sales_events')
    op.drop_table('live_sales_events')
