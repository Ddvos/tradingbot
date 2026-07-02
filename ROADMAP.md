# TradingBot — Roadmap & Progress

> **Living document.** `CLAUDE.md` = *how* we work (principles, conventions,
> type discipline). This document = *where we are* and *what the next step is*.
> Read this **first** when resuming the project — even weeks from now.

## How this document works

- **Reading order when resuming:** (1) this file → "Current status", (2) the
  active slice, (3) `CLAUDE.md` for workflow/conventions.
- **Update agreement:** when a slice is (partly) done, tick the deliverables and
  update "Current status" **in the same commit** as the code. The document never
  lags behind reality.
- **Status legend:** ✅ done · 🚧 in progress · ⬜ todo · ⏸️ parked
- **One slice at a time.** A slice is a *vertical*, self-contained addition
  (data → … → result), not a horizontal layer. Make it complete (incl. tests +
  types green) before moving on.

---

## Current status — 2026-07-02

**Phase:** Slice 0 done — the walking skeleton runs end-to-end on real data.

Done:

- ✅ Architecture & approach decided — see **ADR-001** below: *thin* Hexagonal
  core + VSA api.
- ✅ Backend project init (`uv`, Python 3.13). Tooling: ruff + basedpyright
  (strict) + pytest + pre-commit + GitHub Actions CI.
- ✅ Project skeleton: package structure with a documented `__init__.py` per
  layer (import rules live in the docstrings).
- ✅ `.gitignore`s + `configs/strategies/`.
- ✅ Frontend skeleton (SvelteKit + Svelte 5, bare).
- ✅ **Slice 0** (2 Jul 2026): ports (`MarketDataProvider`, `OrderExecutor`),
  Kraken charts adapter with pagination, ParquetStore with idempotent upsert,
  SimulatedExecutor (Decimal fees + slippage), buy-and-hold BacktestEngine,
  Sharpe/max-drawdown metrics, backfill + backtest CLIs, 20 tests.

**The honest number:** PF_XBTUSD 1h buy-and-hold, 2022-03-23 → 2026-07-02
(37,499 bars, full available history): **Sharpe 0.42, max drawdown −67.2%**,
€10,000 → €14,482 with pessimistic costs (0.05% taker fee, 0.1% slippage).
That is the baseline every strategy must beat.

**Data depth finding (2 Jul 2026):** the Kraken Futures charts API serves
PF_XBTUSD 1h candles from **2022-03-23** only (~4.3 years, no gaps). Enough
for Slice 0–2; tight for the ~2-year walk-forward windows in Slice 3. If more
history is needed for model development, consider Kraken spot XBT/USD as a
supplementary training corpus (decide in Slice 3, not now).

**Next step:** Slice 1 — features + first rule-based strategy (MA-cross) with
realistic costs.

---

## ADR-001 — Thin Hexagonal (9 Jun 2026)

**Decision:** Hexagonal (Ports & Adapters) for the core, but *thin*. We make a
port **only** for a boundary where two real implementations already exist today.

**Why:** the only reason the indirection is worth its weight is **backtest↔live
parity**. The #1 way retail bots blow up is that the backtest quietly cheats
(lookahead, fills that wouldn't happen) and diverges from live. If the strategy
only sees `MarketDataProvider` + `OrderExecutor`, then backtest (Parquet +
Simulated) and live (Kraken + Kraken) run *byte-for-byte the same strategy
code*. basedpyright (strict) enforces that every adapter conforms to the port.

| Has a port (now) | Reason |
|---|---|
| `MarketDataProvider` | 2 impls: `KrakenProvider` (live) + `ParquetProvider` (backtest) |
| `OrderExecutor` | 2 impls: `KrakenExecutor` (live) + `SimulatedExecutor` (backtest) |

| Deliberately NO port (yet) | Reason |
|---|---|
| `TradeRepository`, `ModelRegistry` | 1 impl → YAGNI. Port only in Slice 4 when the in-memory test fake becomes the 2nd impl. |
| DTO/mapper layers core↔adapter | A Polars frame or frozen dataclass crosses the boundary fine. |
| Postgres + SQLAlchemy + Alembic | Not needed to run a backtest — deferred to Slice 4. |

**Not MVC:** the bot is a scheduler-loop with no user-per-tick; there is no
Controller/View. MVC would be a mismatch for the dominant part of the system.
VSA stays for the API.

**Structure ≠ abstraction:** the full directory structure is already in place
(for navigability), but empty documented packages are not premature abstraction
— no interface/code is committed yet. Logic arrives per slice.

---

## Per-slice workflow (definition of done)

A slice is done only when:

- [ ] Happy path + 1–2 edge cases tested (pytest).
- [ ] `uv run basedpyright` green (strict — no `Any`, no bare `type: ignore`).
- [ ] `uv run ruff check` + `uv run ruff format` green.
- [ ] Conventional commit (`feat:`, `fix:`, `test:`, …).
- [ ] Deliverables below ticked + "Current status" updated.

---

## The roadmap

### Slice 0 — Walking skeleton: one honest number ✅

**Goal:** prove the whole pipeline end-to-end — no ML, no DB, no API. Real BTC
1h data → Parquet → buy-and-hold backtest → Sharpe + equity curve. Also the
empirical test of whether the thin-Hexagonal boundary feels comfortable.

**Deliverables:**

- [x] `core/ports/market_data.py` — `MarketDataProvider` Protocol
      (`fetch_ohlcv(symbol, timeframe, since) -> pl.DataFrame`) + OHLCV schema
      contract + `validate_ohlcv`
- [x] `core/ports/executor.py` — `OrderExecutor` Protocol + `Side`,
      `OrderRequest`, `Fill`, `OrderId`
- [x] `adapters/kraken/provider.py` — `KrakenProvider.fetch_ohlcv` (httpx,
      pagination via `more_candles`, Pydantic validation at entry)
- [x] `adapters/parquet/store.py` — `ParquetStore`: read/write with schema +
      invariants (sorted, no dupes, UTC) + idempotent backfill semantics
- [x] `adapters/simulated/executor.py` — `SimulatedExecutor` (fill at close,
      fees + slippage in `Decimal`)
- [x] `core/backtest/engine.py` — minimal `BacktestEngine` (buy-and-hold)
- [x] `core/backtest/metrics.py` — Sharpe, max drawdown, equity curve
- [x] `application/run_backtest.py` — wires Parquet + Simulated + buy-and-hold
- [x] `scripts/backfill.py` — CLI: PF_XBTUSD 1h → Parquet (idempotent, re-runnable)
      (+ `scripts/backtest.py` — prints the report, writes the equity curve)
- [x] Tests: store invariants, metrics, engine happy path (20 tests)
- [x] Add dep: `pydantic` explicitly (now only transitive via FastAPI)

**Done when:** `scripts/backfill.py` writes
`backend/data/raw/ohlcv/PF_XBTUSD/1h.parquet`; a backtest prints buy-and-hold
Sharpe + writes an equity curve; types + lint green.

**Note:** this is also the architecture smoke test. Does the port boundary feel
heavy? Then we trim before Slice 1.

### Slice 1 — Features + first (rule-based) strategy ⬜

**Goal:** OHLCV → features (pure Polars functions); the `Strategy` abstraction;
a simple rule-based strategy (e.g. MA-cross) runs through the engine with
realistic costs. No ML yet — first the plumbing + an honest baseline above
buy-and-hold.

**Deliverables:**

- [ ] `core/features/` — pure functions: returns, ATR, RSI, MACD-hist, BB-width,
      MA-slopes, volume vs MA, OBV, time features (hour/day). Each with a test.
- [ ] `core/strategies/base.py` — `Strategy` Protocol
- [ ] `core/strategies/ma_cross.py` — baseline strategy (no ML)
- [ ] `core/signals/` — predictions/rules → discrete signals (long/flat/short)
- [ ] `core/risk/sizing.py` — `position_size(balance, atr, risk_pct) -> Decimal`
- [ ] `core/backtest/engine.py` — extended: entries/exits, stop (1.5×ATR) +
      TP (3.0×ATR), time exit (6 bars), one position at a time, fees + slippage +
      funding costs (Slice 1 uses a flat, conservative funding assumption —
      real funding-rate data arrives in Slice 3)
- [ ] Tests per feature + engine behavior

**Done when:** the MA-cross backtest runs with realistic costs; metrics
reported; tests green.

### Slice 2 — Labels + ML training ⬜

**Goal:** triple-barrier labels + XGBoost classifier, trained with strict data
separation (no leakage). Inference → signals that feed the strategy.

**Deliverables:**

- [ ] `core/models/labeling.py` — triple-barrier (López de Prado): upper
      2.0×ATR, lower 1.5×ATR, time 6 bars
- [ ] `core/models/dataset.py` — align X/y without lookahead
- [ ] `core/models/train.py` — XGBoost training (procedural)
- [ ] `core/models/inference.py` — load model + predict
- [ ] `adapters/filesystem/model_store.py` — save/load `.joblib` (concrete,
      no port yet)
- [ ] `core/strategies/ml_strategy.py` — strategy that uses model predictions
- [ ] `scripts/train.py` — CLI
- [ ] Tests: labeling correctness, no-leakage check

**Done when:** a model trains on dev data, predicts, and the predictions drive a
strategy; in-sample sanity (IC not NaN).

### Slice 3 — Honest validation ⬜

**Goal:** the rigor this project exists for. Purged walk-forward + embargo,
deflated Sharpe, IC, bootstrap significance, holdout discipline.

**Deliverables:**

- [ ] `core/models/walk_forward.py` — purged, embargoed rolling splits (~2 years)
- [ ] `core/models/evaluation.py` — Sharpe, **deflated** Sharpe, IC, max DD,
      win rate, profit factor, bootstrap CI
- [ ] `application/run_walkforward.py` — full eval run
- [ ] Report artifact per run (Parquet + short markdown)
- [ ] Documented holdout protocol (one-time use, then never again)

**Done when:** a full walk-forward eval produces an honest metrics report;
holdout untouched.

**Decision point:** good → toward paper trading. Not good → max 5 iterations,
otherwise a new hypothesis (see `CLAUDE.md` → Strategy development cycle).

### Slice 4 — Persistence + API + dashboard ⬜

**Goal:** now finally Postgres, the API (VSA), and the SvelteKit dashboard. Here
the storage port becomes justified (2nd impl: postgres + in-memory fake).

**Deliverables:**

- [ ] `config/settings.py` — Pydantic Settings (env, db-url, kraken keys)
- [ ] `core/ports/storage.py` — `TradeRepository`, `ModelRegistry`,
      `BacktestRunRepository` Protocols
- [ ] `adapters/postgres/` — SQLAlchemy 2.0 repos: trades, runs, positions,
      configs, model registry
- [ ] Alembic migrations
- [ ] `api/features/{strategies,backtests,models,live}/` — routes + schemas +
      handlers (VSA)
- [ ] Frontend: list backtests + equity curve (lightweight-charts)
- [ ] Tests: repo fakes, API happy path

**Done when:** the dashboard shows a backtest equity curve from the DB; API
typed; migrations run.

### Slice 5 — Paper trading ⬜

**Goal:** the live runner, but against live Kraken data + simulated execution.
The two-process design (bot + API share the DB) goes live in paper mode.

**Deliverables:**

- [ ] `live/runner.py` — APScheduler 1h tick: fetch → features → predict →
      signal → risk → (simulated) execute → persist
- [ ] `live/command_listener.py` — polls DB flags (pause/resume/switch strategy)
- [ ] `application/execute_tick.py` — KrakenProvider (live data) +
      SimulatedExecutor (paper)
- [ ] "Promoted strategy" pointer (one live strategy at a time)
- [ ] Tests: tick loop against fakes

**Done when:** the bot runs unattended on schedule in paper mode, writes paper
trades to the DB, dashboard shows them. → then ≥4 weeks paper (live rules).

### Slice 6 — Live hardening (reliability) ⬜

**Goal:** what "autonomous" actually requires — mostly reliability engineering,
no architecture. This is the most underestimated step toward running unattended.

**Deliverables:**

- [ ] `OrderExecutor` idempotency: client order IDs + dedupe
- [ ] Startup reconciliation: bot view vs actual exchange positions/orders
- [ ] Circuit breakers: daily loss limit, max consecutive losses,
      10% system-stop → auto-pause + alert
- [ ] Reconnect/retry/backoff on Kraken; structured logging; health check;
      alerting (email/Telegram)
- [ ] Crash recovery: resume cleanly from DB state
- [ ] Chaos tests: kill mid-tick, network down → no double orders / corrupt state

**Done when:** chaos tests pass; kill-switch works; the bot recovers cleanly.

### Slice 7 — Small live capital ⬜

**Goal:** real money, €100–500, one promoted strategy, after ≥4 weeks of paper
that proves paper ≈ expected.

**Deliverables:**

- [ ] `adapters/kraken/executor.py` — `KrakenExecutor` live, behind the same port
- [ ] Pre-deploy gate: types green, tests green, paper-vs-expected within tolerance
- [ ] Monitoring + manual kill-switch
- [ ] Live checklist (see `CLAUDE.md` → Live trading rules)

**Done when:** one small live trade executes and reconciles correctly. Scale only
after proof that live = paper.

---

## Target structure (which slice fills which package)

```
backend/src/tradingbot/
├── core/
│   ├── ports/         # market_data + executor (S0) · storage (S4)
│   ├── features/      # S1
│   ├── signals/       # S1
│   ├── strategies/    # base + ma_cross (S1) · ml_strategy (S2)
│   ├── models/        # labeling + train + inference (S2) · walk_forward + evaluation (S3)
│   ├── backtest/      # engine + metrics (S0, extended S1)
│   └── risk/          # sizing (S1) · manager (S6)
├── adapters/
│   ├── kraken/        # provider (S0) · executor (S7)
│   ├── parquet/       # store (S0)
│   ├── simulated/     # executor (S0)
│   ├── filesystem/    # model_store (S2)
│   └── postgres/      # repositories (S4)
├── application/       # run_backtest (S0) · run_walkforward (S3) · execute_tick (S5)
├── api/features/      # strategies, backtests, models, live (S4)
├── live/              # runner + command_listener (S5, hardening S6)
└── config/            # settings (S4)
```

The canonical (extended) structure + data layout: see `CLAUDE.md`.

---

## Decision log & open questions

**Decided:**

- ADR-001: *thin* Hexagonal (see above).
- Postgres deferred to Slice 4; backtests/ML run on Parquet + filesystem.
- `ROADMAP.md` = living progress; `CLAUDE.md` = workflow/conventions.
- Slice 0 verdict on the architecture smoke test (2 Jul 2026): the port
  boundary is *not* heavy — core imports nothing from adapters, the engine
  feeds the SimulatedExecutor via an `on_bar` callable wired in `application/`.
  Keep as is.
- Funding costs: flat conservative assumption in Slice 1; real funding-rate
  data (`data/raw/funding/{symbol}.parquet`) in Slice 3 (2 Jul 2026).

**Open (decide later, not now):**

- SQLAlchemy 2.0 vs SQLModel → decide in Slice 4.
- Supplementary training data (Kraken spot XBT/USD) if 4.3y of PF_XBTUSD is too
  little for walk-forward → decide in Slice 3.
- Alerting channel (email vs Telegram) → Slice 6.
- Frontend: bare SvelteKit routes suffice for now; FSD only when the dashboard
  grows.

---

## Backlog / explicitly not now (see `CLAUDE.md` → "What we do NOT do")

- No auto-search / optimize-until-profitable.
- No order-book/tick features, RL, or deep learning in v1.
- No leverage > 2x in v1.
