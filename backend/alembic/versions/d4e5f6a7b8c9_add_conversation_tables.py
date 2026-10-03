"""create conversation session tables

Revision ID: d4e5f6a7b8c9
Revises: c1a4f7b2e9d3
Create Date: 2026-10-01 12:00:00.000000

These tables ALREADY exist in the live database because
PostgresSessionStore called Base.metadata.create_all() on startup.
That call is now removed -- this migration is the single source of truth
for the schema going forward. upgrade() is idempotent: on a database
where the tables exist (every existing deployment) it only adds the
missing foreign key, server defaults, and cached-summary column.
On a fresh database it creates both tables from scratch.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c1a4f7b2e9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(inspector) -> set:
    return set(inspector.get_table_names())


def _col_names(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_columns(table)}


def _has_fk_to(inspector, table: str, referred: str) -> bool:
    return any(fk.get("referred_table") == referred for fk in inspector.get_foreign_keys(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = _table_names(insp)

    if "conversation_sessions" not in names:
        op.create_table(
            'conversation_sessions',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('user_id', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('metadata_json', sa.Text(), server_default="{}", nullable=True),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
    else:
        cols = _col_names(insp, "conversation_sessions")
        if "summary" not in cols:
            op.add_column("conversation_sessions", sa.Column("summary", sa.Text(), nullable=True))

    if "conversation_turns" not in names:
        op.create_table(
            'conversation_turns',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('session_id', sa.String(length=36), nullable=False),
            sa.Column('turn_index', sa.Integer(), nullable=False),
            sa.Column('user_message', sa.Text(), nullable=False),
            sa.Column('assistant_response', sa.Text(), nullable=True),
            sa.Column('intent', sa.String(length=50), nullable=True),
            sa.Column('entities_json', sa.Text(), server_default="{}", nullable=True),
            sa.Column('parse_method', sa.String(length=20), nullable=True),
            sa.Column('data_json', sa.Text(), server_default="{}", nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['session_id'], ['conversation_sessions.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    else:
        cols = _col_names(insp, "conversation_turns")
        turn_col = next((c for c in insp.get_columns("conversation_turns") if c["name"] == "turn_index"), None)
        if turn_col is not None and not isinstance(turn_col["type"], sa.Integer):
            # Existing deployments stored turn_index as VARCHAR ("0", "1", ...).
            # Numeric ordering matters at 10+ turns ("10" < "2" lexicographically).
            op.execute("ALTER TABLE conversation_turns ALTER COLUMN turn_index TYPE INTEGER USING turn_index::integer")
        if "data_json" not in cols:
            op.add_column("conversation_turns", sa.Column("data_json", sa.Text(), server_default="{}", nullable=True))
        if not _has_fk_to(insp, "conversation_turns", "conversation_sessions"):
            with op.batch_alter_table("conversation_turns") as b:
                b.create_foreign_key("fk_conversation_turns_session_id", "conversation_sessions", ["session_id"], ["id"], ondelete="CASCADE")

    insp = sa.inspect(op.get_bind())
    turn_ix = {ix["name"] for ix in insp.get_indexes("conversation_turns")}
    sess_ix = {ix["name"] for ix in insp.get_indexes("conversation_sessions")}
    if "ix_conversation_turns_session_id" not in turn_ix:
        op.create_index('ix_conversation_turns_session_id', 'conversation_turns', ['session_id'], unique=False)
    if "ix_conversation_sessions_user_id" not in sess_ix:
        op.create_index('ix_conversation_sessions_user_id', 'conversation_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_conversation_sessions_user_id', table_name='conversation_sessions')
    op.drop_index('ix_conversation_turns_session_id', table_name='conversation_turns')
    op.drop_table('conversation_turns')
    op.drop_table('conversation_sessions')
