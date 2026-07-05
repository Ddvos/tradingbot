"""Slice 5 live-bot state: positions, bot_commands, paper_account.

Hand-written to mirror adapters/postgres/tables.py exactly.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False, unique=True),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("entry_fee", sa.Numeric(24, 8), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stop", sa.Numeric(24, 8), nullable=True),
        sa.Column("take_profit", sa.Numeric(24, 8), nullable=True),
        sa.Column("bars_held", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "bot_commands",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("is_paused", sa.Boolean(), nullable=False),
        sa.Column("promoted_strategy", sa.String(128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "paper_account",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("equity", sa.Numeric(24, 8), nullable=False),
        sa.Column("initial_capital", sa.Numeric(24, 8), nullable=False),
        sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_bar_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paper_account")
    op.drop_table("bot_commands")
    op.drop_table("positions")
