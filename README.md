# tradingbot

Crypto trading bot for BTC perpetual futures (PF_XBTUSD) on Kraken Futures —
a learning project for financial ML, developed hypothesis-driven and
validated rigorously. See `CLAUDE.md` for how we work and `ROADMAP.md` for
where we are.

## Quickstart (dashboard)

```bash
# 1. Postgres (Docker) — from the repo root
docker compose up -d

# 2. Backend — schema, data, one saved backtest, API
cd backend
cp .env.example .env               # fill in later; defaults work locally
uv sync --group dev
uv run alembic upgrade head
uv run python scripts/backfill.py  # fetch PF_XBTUSD 1h history (public API)
uv run python scripts/backtest.py --strategy buy_and_hold --save
uv run uvicorn tradingbot.api.app:app --reload   # http://localhost:8000

# 3. Frontend — in a second terminal
cd frontend
bun install
bun run dev                        # http://localhost:5173
```

## Checks

```bash
cd backend
uv run ruff check && uv run ruff format --check
uv run basedpyright
uv run pytest
```
