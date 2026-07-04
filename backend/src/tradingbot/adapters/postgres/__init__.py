"""PostgreSQL repositories (SQLAlchemy 2.0).

Impls of the storage ports: backtest runs, trades, model registry, strategy
configs. Positions/orders arrive with their consumer, the live runner
(Slice 5). Schema is managed by Alembic (backend/migrations/).
"""
