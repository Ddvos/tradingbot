# TradingBot — Claude Code Instructions

## Project overview

This is a crypto trading bot for BTC perpetual futures on Kraken. The system
consists of a **backend** (Python) that processes data, trains ML models, runs
backtests, and executes live trading, and a **frontend** (SvelteKit) that acts
as a dashboard.

**Goal:** a learning project for financial ML where we develop, validate, and
possibly run strategies live with small capital — honestly and rigorously. No
"auto-search until profitable" — deliberate, hypothesis-driven development with
strict validation.

**Primary asset:** PF_XBTUSD on Kraken Futures, primarily on the 1H timeframe.

## Mental models we follow

1. **Hypothesis-driven, not search-driven.** Every strategy starts with an
   economic or behavioral hypothesis, not with "try 1000 combinations and pick
   the best".

2. **Strict data separation.** Train/validation/test (chronological, never
   random). The holdout test is used once per strategy, then never touched again
   for that same strategy.

3. **Walk-forward over single-split.** Time series justify rolling walk-forward
   validation with purging and embargo.

4. **Simple models, well-considered features.** Prefer 15–25 carefully chosen
   features over 200 random indicators.

5. **Conservative cost assumptions.** Always include fees, slippage, and funding
   rates in backtests — pessimistic rather than optimistic.

6. **One live strategy at a time.** Multiple trained strategies in the library,
   one explicitly promoted to live trading.

## Architecture

**Pattern:** Hexagonal (Ports & Adapters) for the engine, VSA-style for the
API, FSD for the frontend. Pipes & Filters as the mental model for the runtime
flow (data → features → predictions → signals → risk → execution).

> **Hexagonal = _thin_ (decided 9 Jun 2026).** We create a port only where two
> real impls already exist: `MarketDataProvider` + `OrderExecutor` — these
> guarantee backtest↔live parity. Storage ports not until Slice 4; no
> DTO/mapper layers between core and adapters. No MVC (the bot is a
> scheduler-loop with no Controller/View). See `ROADMAP.md` → ADR-001.

**Process boundaries (important!):** The backend consists of **two independent
processes** that share a database, not one request-chain. The API does not call
the bot via HTTP. Communication goes through PostgreSQL:

```
Frontend ──HTTP──► API (FastAPI) ──SQL──┐
                                         ├──► PostgreSQL
Live Bot (APScheduler loop) ──────SQL───┘
        │
        └─► imports the same core/ library as the API
```

The bot runs continuously (1H tick), the API serves the dashboard. Commands
(pause, switch strategy) flow through DB flags that the bot reads on every tick.

**Backend layers:**

- `core/` — pure business logic, no I/O, framework-agnostic
- `core/ports/` — abstract interfaces (Protocol classes)
- `adapters/` — concrete implementations of the ports (Kraken, Parquet, Postgres, …)
- `application/` — use-case orchestration, wires ports to adapters
- `api/` — FastAPI server (VSA), HTTP → application calls
- `live/` — autonomous runner for live/paper trading
- `config/` — Pydantic configs, settings

**Key abstractions (ports):**

- `MarketDataProvider` — implemented by `KrakenProvider` (live)
  and `ParquetProvider` (backtest)
- `OrderExecutor` — implemented by `KrakenExecutor` (live) and
  `SimulatedExecutor` (backtest)
- `TradeRepository`, `ModelRegistry` — Postgres / filesystem adapters

Backtest and live run the same strategy code, only different adapters.

**Import rules (crucial — otherwise the structure loses its meaning):**

- `core/` may import **only** the standard library and data libs (polars, numpy,
  pydantic) — no `requests`, no `sqlalchemy`, no `fastapi`
- `adapters/` may import from `core/ports/` (to implement them), not the other way around
- `application/` may import from `core/` and `adapters/`
- `api/` and `live/` may import from `application/`, not directly from `adapters/`

## Tech stack

### Backend

- **Python 3.13** with `uv` as package manager
- **FastAPI** for the API
- **Pydantic v2** for configs and validation
- **Polars** for data manipulation (not Pandas)
- **DuckDB** for ad-hoc SQL queries on Parquet
- **XGBoost** + scikit-learn for ML
- **APScheduler** for live job scheduling
- **SQLAlchemy 2.0** for the ORM (decided in Slice 4 — see `ROADMAP.md` decision log)
- **Alembic** for database migrations
- **pytest** for tests
- **ruff** for linting and formatting
- **basedpyright** for static type checking (strict mode)

### Storage

- **Parquet files** for historical OHLCV, features, equity curves
- **PostgreSQL** for live state: trades, positions, orders, strategy configs,
  backtest run metadata, model registry
- **Filesystem (.joblib)** for trained model artifacts

### Frontend

- **SvelteKit** with **Svelte 5** (runes syntax)
- **Tailwind CSS**
- **lightweight-charts** (TradingView library) for financial charts
- **shadcn-svelte** components where relevant

## Folder structure

```
tradingbot/
├── CLAUDE.md
├── README.md
├── backend/
│   ├── pyproject.toml
│   ├── .python-version
│   ├── .env.example
│   ├── src/tradingbot/
│   │   ├── core/                    # Pure logic — NO I/O, NO frameworks
│   │   │   ├── strategies/          # Strategy classes
│   │   │   ├── features/            # Feature engineering (pure funcs on Polars DFs)
│   │   │   ├── models/              # ML training/inference logic
│   │   │   ├── backtest/            # Backtest engine
│   │   │   ├── risk/                # Position sizing, limits
│   │   │   ├── signals/             # Signal generation
│   │   │   └── ports/               # Abstract interfaces (Protocol classes)
│   │   │       ├── market_data.py   # MarketDataProvider
│   │   │       ├── executor.py      # OrderExecutor
│   │   │       └── storage.py       # TradeRepository, ModelRegistry
│   │   │
│   │   ├── adapters/                # Concrete implementations of ports
│   │   │   ├── kraken/              # KrakenProvider, KrakenExecutor
│   │   │   ├── parquet/             # ParquetProvider (backtest data)
│   │   │   ├── simulated/           # SimulatedExecutor (backtest)
│   │   │   ├── postgres/            # SQLAlchemy repositories
│   │   │   └── filesystem/          # Model artifact storage (.joblib)
│   │   │
│   │   ├── application/             # Use-case orchestration (thin)
│   │   │   ├── run_backtest.py      # ParquetProvider + SimulatedExecutor + strategy
│   │   │   ├── train_model.py       # data + feature pipeline + XGBoost
│   │   │   └── execute_tick.py      # KrakenProvider + KrakenExecutor for live
│   │   │
│   │   ├── api/                     # FastAPI — VSA-style
│   │   │   └── features/
│   │   │       ├── strategies/      # routes.py, schemas.py, handlers.py
│   │   │       ├── backtests/
│   │   │       ├── models/
│   │   │       └── live/
│   │   │
│   │   ├── live/                    # Long-running bot process
│   │   │   ├── runner.py            # APScheduler loop
│   │   │   └── command_listener.py  # Polls DB for pause/resume commands
│   │   │
│   │   └── config/                  # Pydantic Settings
│   │
│   ├── tests/
│   ├── scripts/                     # Standalone CLI tools (backfill, train, etc.)
│   └── data/                        # Local, not in git
│       ├── raw/
│       ├── processed/
│       └── models/
├── frontend/
└── configs/                         # YAML strategy configs
    └── strategies/
```

## Data layout (Parquet)

How historical market data sits on disk. No formal ER diagram (Parquet has no
relations), but a fixed convention per file type.

### File layout

```
backend/data/
└── raw/
    └── ohlcv/
        └── {symbol}/
            └── {timeframe}.parquet
```

Example: `backend/data/raw/ohlcv/PF_XBTUSD/1h.parquet`. **One file per
(symbol, timeframe)**, the entire history in it. No partitioning per year/month
for v1 — for 1H BTC data that's ~1 MB per year, comfortably within a single file.

The `raw/` sub-folder reserves room for `processed/` (features) and `models/`
(trained artifacts) at the same level.

### OHLCV schema

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | `Datetime("ms", "UTC")` | Bar OPEN time, tz-aware |
| `open` | `Float64` | Open price |
| `high` | `Float64` | High price |
| `low` | `Float64` | Low price |
| `close` | `Float64` | Close price |
| `volume` | `Float64` | Volume in base currency |

Conventions:

- **`timestamp` = bar OPEN time** (not close). "The 14:00 1H bar" = bar 14:00 → 15:00 UTC.
- **Float64 for prices**, not Decimal. OHLCV is for analysis/indicators. We
  reserve `Decimal` for real money movements (account balance, order quantity,
  P&L). See also Type discipline.
- **Always UTC** — no naive datetimes.

### Invariants per file

- Sorted by `timestamp` ascending
- No duplicate timestamps
- Schema exactly as the table above (ParquetStore validates on read and write)

Gap detection (Kraken downtime) comes in a later slice.

### Write semantics: idempotent backfill

A backfill call for a (possibly overlapping) range does:

1. Read the existing parquet if present
2. Concat with new rows from Kraken
3. Dedupe on `timestamp`
4. Sort ascending
5. Write the whole file back

Fetching the same range twice → no change. Safe to re-run.

The `{symbol}/` folder is auto-created by the adapter.

### Naming (no translation)

Use Kraken's own naming — don't rename:

- Symbol: `PF_XBTUSD` (BTC perpetual)
- Timeframe: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `1d`, `1w` → becomes
  a `Literal` type for type safety

### Future data types (not yet implemented)

- `data/raw/funding/{symbol}.parquet` — funding rates for perpetuals
- `data/raw/trades/{symbol}.parquet` — tick-level trades (only if needed)
- `data/processed/features/{symbol}/{timeframe}.parquet` — engineered features

Each extension gets its own spec section when it's implemented.

## Strategy development cycle

```
1. Formulate hypothesis
2. Configure strategy (YAML)
3. Train on development data with walk-forward
4. Analyze results (IC, Sharpe, drawdown, sanity checks)
5. Good? → Holdout test (once!) → Paper trading → Small live
   Not good? → Max 5 iterations, otherwise a new hypothesis
```

## ML approach (v1)

- **Model:** XGBoost classifier
- **Target:** triple-barrier labeling (López de Prado)
  - Upper barrier: entry + 2.0 × ATR
  - Lower barrier: entry − 1.5 × ATR
  - Time barrier: 6 bars
- **Features:** 15–25 of them, multi-timeframe (4H trend + 1H anchor + 15M momentum)
  - Trend: MA slopes, EMA crosses
  - Momentum: RSI (1H, 4H), MACD histogram
  - Volatility: ATR (1H), Bollinger Band width, realized vol
  - Volume: volume vs MA, OBV trend
  - Market structure: distance from key levels
  - Funding: current funding rate, funding rate trend
  - Time: hour of day, day of week
- **Validation:** purged walk-forward, ~2-year rolling window
- **Metrics:** Sharpe, Deflated Sharpe, Information Coefficient (IC), max
  drawdown, win rate, profit factor, statistical significance via bootstrap

## Risk management

- **Position sizing:** ATR-based, 1% risk per trade of account balance
- **Stop loss:** 1.5 × ATR below entry (long) or above entry (short)
- **Take profit:** 3.0 × ATR (1:2 risk-reward), or triple-barrier exit
- **Time exit:** close position after 6 bars if no TP/SL is hit
- **Circuit breakers:** daily loss limit, max consecutive losses
- **One position at a time** for v1

## Trading constraints

- **Exchange:** Kraken Futures
- **Symbol:** PF_XBTUSD (BTC perpetual)
- **Timeframe:** 1H (decisions), with 4H and 15M data as extra features
- **Order type:** limit orders where possible (maker fees), market as fallback
- **Fees assumption:** 0.02% maker, 0.05% taker (Kraken Futures base tier)
- **Slippage assumption:** 0.05–0.10% per trade
- **Funding rate:** every 4 hours, include in backtest costs

## Development principles for Claude Code

1. **One thing at a time, small and complete.** Finish one file/feature
   entirely before moving to the next. No 10 empty files at once.

2. **Code must be self-explanatory.** Prefer expressive naming over comments.
   Comments for _why_, not _what_.

3. **Type hints everywhere.** Python 3.13 syntax: `list[int]`, `dict[str, float]`,
   `X | None` (not `Optional[X]`).

4. **Pydantic for data validation.** No raw dicts for configs or API payloads.

5. **Polars over Pandas.** Unless there's a very good reason for Pandas.

6. **No premature abstractions.** We create an interface (Protocol or ABC) only
   when we have at least 2 concrete implementations or know they're coming (like
   MarketDataProvider).

7. **Tests with every feature.** Not 100% coverage, but happy path + 1–2
   edge cases per module.

8. **Conventional commits.** `feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
   `chore:`.

## Paradigm choices

Python is multi-paradigm. We mix pure functions, dataclasses, Pydantic, and
classes — each where they fit best. **"More OOP" is not a quality signal**:
anemic classes, single-method classes, and deep inheritance hierarchies are
actually a red flag. Choosing the right paradigm per situation is what makes
modern Python professional.

### Decision framework

- **Pure functions** when: stateless transformation, one-shot computation,
  no lifecycle.
- **Frozen dataclass / Pydantic** when: data container, optionally with
  validation. (Pydantic at system boundaries, dataclass internally.)
- **Classes with behavior** when: state + behavior naturally belong together,
  lifecycle (open/use/close), multiple instances meaningful, implements a Protocol.
- **Protocols** when: interface with multiple implementations (Hexagonal ports).

### Inheritance

**Almost never.** Composition + Protocols are more scalable and testable than
inheritance chains.

- ✅ `class KrakenProvider:` implements the `MarketDataProvider` Protocol —
  no `extends`, just the right signatures (structural typing)
- ✅ Composition: `BacktestEngine` *has a* `Strategy`, *has a*
  `RiskManager`, *has a* `MarketDataProvider`
- ❌ `class MomentumStrategy(BaseStrategy):` with a deep hierarchy

### Per module — concrete choices

| Module | Approach | Reason |
|---|---|---|
| `core/features/` | Pure functions on Polars DataFrames | Stateless, composable, trivial to test |
| `core/signals/` | Pure functions | Transform predictions → signals |
| `core/risk/sizing.py` | Pure functions | `position_size(balance, atr, risk_pct) -> Decimal` |
| `core/risk/manager.py` | Class (`RiskManager`) | Holds limits, consecutive losses, daily P&L |
| `core/strategies/` | Classes | Hold model + params + recent state, implement the `Strategy` Protocol |
| `core/backtest/engine.py` | Class (`BacktestEngine`) | Stateful: portfolio, clock, trade history |
| `core/models/` | Functions + sklearn-style class where needed | XGBoost training is procedural |
| `core/ports/` | Protocol classes | Pure interface definitions |
| `adapters/kraken/` | Classes | Hold HTTP client, credentials, rate limiter |
| `adapters/parquet/` | Class | Holds base path, optional cache |
| `application/*.py` | Functions | Use cases are procedural: wire adapters, run engine |
| `api/.../handlers.py` | Functions | FastAPI handlers are function-idiomatic |
| Configs (`*Config`) | Pydantic `BaseModel` | Data + validation, no behavior |

**Note:** dataclasses, Pydantic models, and Protocols are also classes. In the
"function" rows we still use them as data containers and interfaces, just not as
behavior holders.

## Type discipline

Goal: prevent type errors in production. Configuration lives in
`backend/pyproject.toml` and `.pre-commit-config.yaml`. Three layers:

1. **Static type checker** — `basedpyright` in strict mode. Catches None bugs,
   wrong arguments, and refactor rot before the code runs. Runs in pre-commit
   and CI.
2. **Runtime validation** — `Pydantic v2` at system boundaries (API requests,
   YAML configs, Kraken responses, env vars). **No** Pydantic for internal
   `core/` data — there a frozen `dataclass` or `NamedTuple` is lighter.
3. **Linter** — `ruff` with rules that complement type discipline (incl. `DTZ`
   for tz-aware datetimes, `UP` for modern syntax).

### Mandatory rules in `src/`

- **`Any` is forbidden** (strict mode catches this automatically).
- **`# type: ignore` only with an error code and a reason:**
  `# type: ignore[arg-type]  # kraken-futures stubs missing in 1.2.0`
- **No `cast()`** if a refactor is possible.
- **Public functions have full type signatures** (args + return).
- **Tests are typed too** — otherwise refactors break without you noticing.
- **No `dict[str, Any]`** for structured data — use `TypedDict`,
  `dataclass`, or a Pydantic model.

### Trading-specific type rules

- **Money in `Decimal`**, never `float`. Applies to prices, quantities, P&L,
  fees. `float` is fine for indicators/features (ATR, RSI, etc.).
- **Datetimes always timezone-aware** (`datetime.now(UTC)`). Naive datetimes
  are blocked by the ruff `DTZ` rule.
- **Domain IDs via `NewType`**: `OrderId`, `StrategyId`, `BacktestRunId` —
  so you can't accidentally mix them up.
- **Closed sets via `StrEnum`** (`Side`, `OrderType`, `OrderStatus`) or
  `Literal` for narrow string types (`Timeframe = Literal["15m", "1h", "4h", "1d"]`).
- **Validate Polars schemas explicitly** at entry (Kraken adapter, Parquet
  loader) — Polars has limited static type info.

### Modern syntax (Python 3.13)

```python
def fetch(symbol: str) -> list[Candle] | None: ...     # built-in generics + union
def first[T](items: list[T]) -> T | None: ...           # PEP 695 generics
type Timeframe = Literal["15m", "1h", "4h", "1d"]       # PEP 695 type alias

class MarketDataProvider(Protocol):                      # Protocol for ports
    def fetch_ohlcv(self, symbol: str, since: datetime) -> pl.DataFrame: ...
```

### Enforcement

- **Pre-commit:** ruff + basedpyright on staged files.
  Install: `uv run pre-commit install`.
- **CI:** same checks on all files, blocking for merge to `main`.
- **Pre-deploy:** type check must be green before the live runner may start.

## What we do NOT do

- No "auto-search" or "auto-optimize until profitable" systems
- No tick-level order book features in v1 (too complex for retail)
- No RL in v1 (get XGBoost working well first)
- No deep learning (CNN/LSTM) in v1
- No tight stops on visible support levels (stop-hunting risk)
- No leverage > 2x in v1 (first prove the strategy works)

## Live trading rules

- **Paper trading first** (at least 4 weeks) before live money
- **Live starts with €100–500**, no more
- **Scale only after proof** that live = paper trading
- **System-level stop loss:** if the system loses 10%, automatically
  pause and human review

## Status & roadmap

**The living progress and the step-by-step plan live in
[`ROADMAP.md`](ROADMAP.md) — read that first.** This file (CLAUDE.md) describes
*how* we work (principles, conventions, type discipline); `ROADMAP.md` describes
*where we are* and *what the next step is*. Update `ROADMAP.md` in the same
commit as the code.

In short (as of 5 Jul 2026): **Slices 0–4 done** — full pipeline runs on
real data with pessimistic costs incl. funding; baseline to beat: buy-and-hold
Sharpe 0.21. MA-cross hypothesis rejected (cost churn). ML pipeline exists:
triple-barrier labels → XGBoost (xgb_v1) → MLStrategy. Slice 4: Postgres via
SQLAlchemy 2.0 + Alembic, storage ports, FastAPI (VSA), SvelteKit dashboard
with equity curves. Slice 3 (honest validation): purged walk-forward,
deflated Sharpe, bootstrap CI, holdout protocol (`HOLDOUT.md`, boundary
2026-07-04 after the 5 Jul 2026 rule-4 ruling; enforced in every dev entry
point via `application/holdout.py`). Verdict: xgb_v1's *signal* survives OOS (IC 0.22 across all
folds) but MLStrategy(threshold 0.6) is **rejected** (4 trades/15 months,
OOS Sharpe −1.66 vs buy-and-hold 0.67). Tooling: ruff + basedpyright strict +
pytest + pre-commit + CI. Architecture in **ADR-001** (_thin_ Hexagonal).
Hypotheses are pre-registered in `HYPOTHESES.md` before evaluation (H3
market-structure features: null result, 5 Jul 2026).
**Next step:** the Slice 3 decision point — iterate on the signal→position
mapping (max 5 iterations) or fold the hypothesis.

## External references

- López de Prado: _Advances in Financial Machine Learning_ (concepts:
  triple-barrier, purged CV, deflated Sharpe)
- Stefan Jansen: _Machine Learning for Algorithmic Trading_ (practical code)
- Rob Carver: _Systematic Trading_ (signal combination, speed limit concept)
- Kraken Futures API: https://docs.kraken.com/api/docs/futures-api/

## When in doubt

When Claude Code is in doubt about a choice: ask a question instead of guessing.
Especially for:

- Architecture decisions that touch multiple modules
- External library choices
- Database schema changes
- Risk management parameters
