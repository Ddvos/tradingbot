"""Initial schema: backtest_runs, trades, model_registry, strategy_configs.

Hand-written to mirror adapters/postgres/tables.py exactly.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("data_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initial_capital", sa.Numeric(24, 8), nullable=False),
        sa.Column("final_equity", sa.Numeric(24, 8), nullable=False),
        sa.Column("sharpe", sa.Float(), nullable=False),
        sa.Column("max_drawdown", sa.Float(), nullable=False),
        sa.Column("n_trades", sa.Integer(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("equity_curve_path", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "trades",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("exit_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pnl", sa.Numeric(24, 8), nullable=False),
        sa.Column("fees", sa.Numeric(24, 8), nullable=False),
        sa.Column("exit_reason", sa.String(32), nullable=False),
    )
    op.create_table(
        "model_registry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("artifact_path", sa.String(512), nullable=False),
        sa.Column("auc", sa.Float(), nullable=False),
        sa.Column("ic", sa.Float(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "strategy_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("strategy_configs")
    op.drop_table("model_registry")
    op.drop_table("trades")
    op.drop_table("backtest_runs")
