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

## Current status — 2026-07-05

**Phase:** Slices 0–5 built. Slice 3 (honest validation) closed the gate it
guarded, with a split verdict: **the xgb_v1 signal survives out-of-sample;
the strategy built on it does not** — see the walk-forward verdict below.
Slice 5 (paper trading) is code-complete but idle: promoting a strategy is
gated on one that passes validation, so the open decision remains the
Slice 3 decision point.

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
- ✅ **Slice 1** (3 Jul 2026): indicator library (`core/features/`), `Strategy`
  Protocol + Hold/MA-cross strategies, `Signal` enum, ATR risk sizing, and the
  extended engine: next-open execution, intrabar stop/TP (stop wins ties),
  time exit, flat funding cost, signed (short-capable) positions, trade log.
  52 tests total.
- ✅ **Slice 2** (3 Jul 2026): triple-barrier labeling (binary: 2.0×ATR target
  before 1.5×ATR stop within 6 bars), dataset builder with a no-lookahead
  test, XGBoost training on a purged chronological 70/30 split (fixed
  hyperparameters — no tuning), IC/AUC evaluation, `.joblib` ModelStore,
  `MLStrategy` (long when P(target) ≥ 0.6). 71 tests total.
- ✅ **Slice 4** (4 Jul 2026, built out of order — see Phase above): storage
  ports (4 Protocols + frozen-dataclass records), SQLAlchemy 2.0 Postgres
  adapter + Alembic migration, Pydantic Settings + `.env`, docker-compose
  Postgres, FastAPI (VSA: backtests/models/strategies/live + /health),
  `--save`/`--register` script flags, SvelteKit dashboard with
  lightweight-charts equity curve. 87 tests total. Verified end-to-end:
  backtest → Postgres → API → chart in the browser.
- ✅ **Slice 3** (4 Jul 2026): purged + embargoed rolling walk-forward
  (2y train / 90d test / purge 6 = label horizon / embargo 24, retrain per
  fold), evaluation suite (probabilistic + deflated Sharpe, block-bootstrap
  Sharpe CI, win rate, profit factor), stitched OOS equity + report artifact
  (folds.parquet + equity.parquet + report.md per run), holdout protocol in
  `HOLDOUT.md` (boundary 2025-07-01, enforced in code). 102 tests total.

**Walk-forward verdict on xgb_v1 (4 Jul 2026 — the honest evaluation):**
5 folds, OOS test windows 2024-03-25 → 2025-06-18 (~15 months). The
*signal* is real: pooled OOS IC 0.218 / AUC 0.664, stable across every fold
(IC 0.19–0.24) — the Slice-2 dev numbers were not a split artifact. The
*strategy* is not: P(target) ≥ 0.6 fired only 4 trades in 15 months (with
base rate 0.18 the model rarely gets that confident), 1 win, profit factor
0.05. OOS Sharpe **−1.66** (bootstrap 95% CI [−2.81, 0.45]), deflated
Sharpe 0.000, while buy-and-hold did 0.67 on the same windows.
**MLStrategy(xgb_v1, threshold 0.6) is rejected.** The stable IC earns
exactly one thing: a next iteration on the signal→position mapping — the
loss is in how predictions become trades, not in the model's ranking skill.

**Hypothesis H3 — market-structure features (5 Jul 2026):** first entry in
the new pre-registration registry **`HYPOTHESES.md`** (hypothesis, fixed
parameters, and success criteria written down *before* the run). Seven causal
swing-structure features (fractal k=3 with the k-bar confirmation lag;
`core/features/structure.py`) were added to the 13-feature set and evaluated
through the identical walk-forward: pooled OOS IC 0.222 vs 0.218 — inside
the pre-registered ±0.02 parsimony band → **null result, keep the 13-feature
set**. The feature library + tests stay (unwired); the trial is registered
for the deflated Sharpe. 110 tests total.

**Dashboard: walk-forward runs (5 Jul 2026):** new `/walkforward` API slice
(VSA) reads the run artifacts straight from disk — no DB row, the filesystem
is the registry — and the dashboard gained a walk-forward section: run list
(summary metrics recomputed from equity.parquet with the same core
functions, so they match the report exactly), stitched OOS equity curve,
per-fold table (NaN/inf → null at the JSON boundary), and the report.md
verdict. 116 tests total.

- ✅ **Holdout enforcement + boundary move** (5 Jul 2026): review found two
  rule-4 contamination events (full-history baselines; `train.py`'s
  unclamped validation split) → boundary moved to **2026-07-04**, clamps
  added to every dev entry point via `application/holdout.py`, both events
  logged in `HOLDOUT.md`. Also fixed: `KrakenProvider` no longer returns
  (and backfill no longer persists) the still-forming candle. 120 tests.
- ✅ **Slice 5** (5 Jul 2026): paper trading, built while the strategy
  question stays open (the machinery is strategy-agnostic). `TickEngine`
  with tested backtest parity, `execute_tick` (idempotent, replays missed
  bars), APScheduler runner + command listener, `positions` /
  `bot_commands` / `paper_account` storage (migration 0002), `/live` API
  (status, trades, pause/resume/promote/demote), dashboard paper section.
  **Nothing is promoted** — see the Slice 5 gate note. 147 tests total.

**Dashboard: trades on the price chart (6 Jul 2026):** the engine records
the stop/take-profit levels each position actually ran with (`Trade.stop`
/ `.take_profit`); every backtest writes a trade log
(`…_trades.parquet` next to its equity curve) and walk-forward runs
persist `trades.parquet`; new candles + trades endpoints on both API
slices (OHLCV served from `ohlcv_dir`). The dashboard draws a candlestick
chart with entry/exit markers (arrows by side, dots colored by exit
reason) and, on click, zooms to a trade and draws its entry, stop, and
take-profit levels. Older artifacts predate the trade logs — re-running
the backtest/walk-forward regenerates them (verified deterministic:
identical metrics). 165 tests total.

**H2 iteration 2 — hysteresis mapping (5 Jul 2026): rejected.** Enter long
at P ≥ 1.5× train base rate, stay while ≥ 1.0×, signal-only exits
(pre-registered in `HYPOTHESES.md`). Same walk-forward, same eval window as
iteration 1: OOS Sharpe **−1.93** (CI [−3.66, −0.22]), 360 trades, PF 0.77
vs buy-and-hold 0.67. Trade-count problem solved, economics still negative;
IC unchanged at 0.218. Pattern across all candidates so far: a real but
small edge loses to 1h taker costs under every mapping tried. 154 tests
total. Two of five H2 iterations spent.

**Hypothesis H4 — structure trend-following (5 Jul 2026):** pure price
action, long/short: higher highs + higher lows → long, the mirror → short,
position flips only on a fully confirmed opposite structure (k=3 swings
from the H3 library), signal-only exits per finding #2. Pre-registered in
`HYPOTHESES.md`, one dev-window backtest: **rejected** — Sharpe −2.45,
profit factor 0.83, 1,388 structure flips (3× MA-cross's churn),
€10,000 → €34. Third strike for 1h trend persistence. 150 tests total.

**Slice 2 scope notes:** features are 1h-only for now (multi-timeframe 4H/15M
set deferred); labels are binary long-only; threshold 0.6 fixed a priori.

**The honest numbers** (PF_XBTUSD 1h, 2022-03-23 → 2026-07-02, 37,499 bars,
pessimistic costs: 0.05% taker, 0.1% slippage, ~11%/yr flat funding):

| Run | Sharpe | Max DD | €10,000 → |
|---|---|---|---|
| Buy-and-hold (**the baseline to beat**) | **0.21** | −71% | €7,963 |
| MA-cross 20/50, v1 risk rules (6-bar time exit) | −10.1 | −100% | €0.11 |
| MA-cross 20/50, signal-only exits | −0.59 | −70% | €3,330 |
| Structure trend k=3, signal-only exits (H4) | −2.45 | −99.8% | €34 |

Note the Slice 0 baseline (Sharpe 0.42, €14,482) is superseded: the engine now
fills at next-bar open and charges funding, both of which buy-and-hold on a
perp genuinely pays.

**Findings (3 Jul 2026):**

1. **Funding matters enormously**: it turns buy-and-hold from +45% into −20%.
2. **The v1 exit rules are horizon-bound**: the 6-bar time exit is calibrated
   for the triple-barrier ML horizon (Slice 2). Applied to a slow trend
   signal it forces ~4,300 exit/re-enter round trips whose costs compound to
   −100%. Exit rules must match the signal's holding horizon.
3. **Hypothesis "1h MA-cross trend persistence" is rejected** — even with
   matched exits, 447 crossings of cost churn beat the edge (profit factor
   0.85). Per the development cycle this hypothesis is done; the ML approach
   (Slice 2) is the next hypothesis, not MA-parameter tweaking (that would be
   search-until-profitable).

**Data depth finding (2 Jul 2026):** the Kraken Futures charts API serves
PF_XBTUSD 1h candles from **2022-03-23** only (~4.3 years, no gaps). Enough
for Slice 0–2; tight for the ~2-year walk-forward windows in Slice 3. If more
history is needed for model development, consider Kraken spot XBT/USD as a
supplementary training corpus — resolved 4 Jul 2026: not needed (see
decision log).

**Next step:** the Slice 3 decision point. MLStrategy(xgb_v1, 0.6) is
rejected, but the OOS IC says the underlying signal survives honest
validation — so the hypothesis is not dead, and the iteration budget
applies (max 5 per hypothesis; threshold/mapping changes count as
iterations and must be re-validated through the same walk-forward). Decide:
iterate on the prediction→position mapping, or fold the hypothesis. The
feature axis was explored on 5 Jul (H3, null result), a pure price-action
trend strategy was rejected the same day (H4, Sharpe −2.45), and mapping
iteration 2 (hysteresis regime) was rejected as well (−1.93) — three H2
iterations remain. The evidence points at cost-per-decision, not signal
quality: iteration 3 candidates are confidence-scaled *sizing* (needs
fractional-position engine support) or a 4h decision timeframe. Slice 5 is
built and waiting: the moment a candidate passes, promote it and the
≥4-week paper clock starts.

**Running the stack (Slice 4):**

```bash
docker compose up -d                                  # Postgres 17 (repo root)
cd backend
uv run alembic upgrade head                           # create/upgrade schema
uv run python scripts/backtest.py --strategy buy_and_hold --save
uv run python scripts/walkforward.py                  # honest eval (Slice 3), dev data only
uv run uvicorn tradingbot.api.app:app --reload        # API on :8000
uv run python -m tradingbot.live.runner               # paper bot (Slice 5), ticks hourly
cd ../frontend && bun install && bun run dev          # dashboard on :5173
```

The paper bot idles until a strategy config is promoted (dashboard →
Paper trading, or `POST /live/promote`). Configs are saved rows in
`strategy_configs` with a `kind` param (`hold`, `ma_cross`, `ml`).

Configuration lives in `backend/.env` (copy from `.env.example`). Kraken API
keys are **not** needed yet — the public charts API covers backfill; keys
become relevant in Slice 5+.

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

### Slice 1 — Features + first (rule-based) strategy ✅

**Goal:** OHLCV → features (pure Polars functions); the `Strategy` abstraction;
a simple rule-based strategy (e.g. MA-cross) runs through the engine with
realistic costs. No ML yet — first the plumbing + an honest baseline above
buy-and-hold.

**Deliverables:**

- [x] `core/features/` — pure Polars expressions: returns, ATR, RSI, MACD-hist,
      BB-width, MA-slopes, volume vs MA, OBV, time features (hour/day). Each
      with a test. (`indicators.py` + `temporal.py`)
- [x] `core/strategies/base.py` — `Strategy` Protocol (causal signals contract)
- [x] `core/strategies/ma_cross.py` — baseline strategy (no ML) + `hold.py`
- [x] `core/signals/` — `Signal` StrEnum (long/flat/short) + direction mapping
- [x] `core/risk/sizing.py` — `position_size(...)` (risk-from-stop) +
      `all_in_size(...)`, notional capped at balance (no leverage)
- [x] `core/backtest/engine.py` — extended: next-open execution, intrabar stop
      (1.5×ATR) + TP (3.0×ATR) with stop-wins-ties, time exit (6 bars), one
      position at a time (long *and* short), fees + slippage + flat funding
      (real funding-rate data deferred to Slice 5), `TradeRules`, trade log
- [x] Tests per feature + engine behavior (52 total)

**Done when:** the MA-cross backtest runs with realistic costs; metrics
reported; tests green. ✅ — result honest and negative, see Findings above.

### Slice 2 — Labels + ML training ✅

**Goal:** triple-barrier labels + XGBoost classifier, trained with strict data
separation (no leakage). Inference → signals that feed the strategy.

**Deliverables:**

- [x] `core/models/labeling.py` — triple-barrier (López de Prado): upper
      2.0×ATR, lower 1.5×ATR, time 6 bars; binary label, stop-wins ties
- [x] `core/models/dataset.py` — align X/y without lookahead (13 causal 1h
      features, price-normalized where scale-dependent)
- [x] `core/models/train.py` — XGBoost training (procedural, fixed params,
      purged chronological split) + `core/models/evaluation.py` (IC)
- [x] `core/models/inference.py` — predict from artifact
- [x] `adapters/filesystem/model_store.py` — save/load `.joblib` (concrete,
      no port yet); artifact bundles model + feature list + metrics
- [x] `core/strategies/ml_strategy.py` — strategy that uses model predictions
- [x] `scripts/train.py` — CLI
- [x] Tests: labeling correctness, no-leakage check (truncation invariance)

**Done when:** a model trains on dev data, predicts, and the predictions drive a
strategy; in-sample sanity (IC not NaN). ✅ IC 0.208, finite — see caveats in
Current status.

### Slice 3 — Honest validation ✅

**Goal:** the rigor this project exists for. Purged walk-forward + embargo,
deflated Sharpe, IC, bootstrap significance, holdout discipline.

**Deliverables:**

- [x] `core/models/walk_forward.py` — purged, embargoed rolling splits
      (2y train / 90d test; purge 6 = label horizon; embargo 24; truncated
      tail folds kept only above a 30-day minimum)
- [x] `core/models/evaluation.py` — **deflated** Sharpe + probabilistic
      Sharpe (Bailey & López de Prado 2014), moving-block bootstrap Sharpe
      CI, win rate, profit factor. Plain Sharpe/max-DD stay in
      `core/backtest/metrics.py` (reused, not duplicated); IC was already here.
- [x] `application/run_walkforward.py` — full eval run: fresh XGBoost per
      fold (same fixed hyperparameters as `train.py`, via the shared
      `fit_classifier`), OOS predictions backtested through the real engine
      with pessimistic costs (TP aligned to the 2.0×ATR label barrier),
      per-fold curves stitched into one OOS equity curve. Clamps to
      pre-holdout data unconditionally. Buy-and-hold is run over the same
      test windows as the baseline.
- [x] Report artifact per run: `scripts/walkforward.py` writes
      `folds.parquet` + `equity.parquet` + `report.md` under
      `data/processed/walkforward/{symbol}/`.
- [x] Documented holdout protocol → **`HOLDOUT.md`** (repo root): boundary
      2025-07-01, one-shot-per-strategy rules, usage log, enforcement notes.

**Done when:** a full walk-forward eval produces an honest metrics report;
holdout untouched. ✅ report produced 4 Jul 2026; holdout untouched.

**Result (4 Jul 2026):** split verdict — signal survives, strategy dies.
Pooled OOS IC 0.218 / AUC 0.664, stable across all 5 folds; but only 4
trades in 15 OOS months (threshold 0.6 vs base rate 0.18), profit factor
0.05, OOS Sharpe −1.66 (95% CI [−2.81, 0.45]), deflated Sharpe 0.000 vs
buy-and-hold 0.67 on the same windows. Full numbers in the Current-status
verdict above and in the report artifact.

**Decision point:** not good → max 5 iterations on this hypothesis or a new
one (see `CLAUDE.md` → Strategy development cycle). The stable OOS IC makes
the signal→position mapping the obvious iteration target; any change counts
against the budget and re-runs the same walk-forward.

### Slice 4 — Persistence + API + dashboard ✅

**Goal:** now finally Postgres, the API (VSA), and the SvelteKit dashboard. Here
the storage port becomes justified (2nd impl: postgres + in-memory fake).

**Deliverables:**

- [x] `config/settings.py` — Pydantic Settings (env, db-url, kraken keys as
      `SecretStr`) + `.env.example`/`.env` + docker-compose Postgres
- [x] `core/ports/storage.py` — `TradeRepository`, `ModelRegistry`,
      `BacktestRunRepository` **+ `StrategyConfigRepository`** Protocols,
      records as frozen dataclasses, IDs as `NewType(UUID)`
- [x] `adapters/postgres/` — SQLAlchemy 2.0 repos: runs, trades, configs,
      model registry. *Positions deferred to Slice 5*: their consumer is the
      live runner; designing that table without it would be speculation.
- [x] Alembic migrations (`backend/migrations/`, URL from Settings; verified
      against Postgres 17)
- [x] `api/features/{strategies,backtests,models,live}/` — routes + schemas +
      handlers (VSA); `live/status` is an explicit stub until Slice 5;
      equity-curve endpoint joins DB metadata with the Parquet curve file
- [x] Frontend: list backtests + equity curve (lightweight-charts)
- [x] Tests: in-memory fakes (the 2nd port impl per ADR-001), repo
      round-trips on SQLite in-memory, API happy paths (87 tests total)

**Done when:** the dashboard shows a backtest equity curve from the DB; API
typed; migrations run. ✅ all three verified 4 Jul 2026.

**Slice 4 scope notes:** backtest scripts persist with `--save` (opt-in — a
backtest without DB still works); equity curves stay in Parquet, the DB row
stores the path; `trades` table exists but nothing writes it until the paper
runner (Slice 5); the models/strategies endpoints return `[]` until
`train.py --register` runs / configs are saved.

### Slice 5 — Paper trading ✅ (code-complete 5 Jul 2026 — see gate note)

**Goal:** the live runner, but against live Kraken data + simulated execution.
The two-process design (bot + API share the DB) goes live in paper mode.

**Deliverables:**

- [x] `core/live/tick_engine.py` — `TickEngine`: one closed bar at a time,
      restart-safe state, same barrier/sizing mechanics as the backtest
      (shared pure functions extracted from `BacktestEngine`); **parity is
      tested** — identical trades + cash on the same bars and signals
- [x] `live/runner.py` — APScheduler 1h tick (HH:00:45 UTC): fetch → signal
      → risk → (simulated) execute → persist; a failed tick never kills the
      scheduler; missed bars replay in order on the next tick
- [x] `live/command_listener.py` — polls DB flags every 30s (log visibility;
      each tick re-reads the flags itself)
- [x] `application/execute_tick.py` — KrakenProvider (live data, closed bars
      only) + SimulatedExecutor (paper, pessimistic taker + slippage);
      idempotent on no-new-bar
- [x] "Promoted strategy" pointer — `bot_commands` singleton row (pause +
      promoted config name), written by the API, read by the bot
- [x] Storage: `positions` + `bot_commands` + `paper_account` tables,
      ports + Postgres repos + in-memory fakes, Alembic migration 0002
      (verified against Postgres 17)
- [x] API: `/live/status`, `/live/trades`, `/live/pause|resume|promote|demote`
- [x] Dashboard: paper-trading section (status card, controls, trades table)
- [x] Tests: tick loop + engine parity + repos + API against fakes
      (147 backend tests)

**Done when:** the bot runs unattended on schedule in paper mode, writes paper
trades to the DB, dashboard shows them. → then ≥4 weeks paper (live rules).

**Gate note (5 Jul 2026):** the machinery is built and tested, but per the
Slice 3 decision point **nothing is promoted**: promoting a real strategy
still requires one that passes walk-forward. `hold` may be promoted as a
smoke test of the loop (it goes all-in long — promote it knowingly, or just
leave the bot idle). The ≥4-week paper clock starts only when a validated
strategy is promoted.

**Deferred within the slice:** real funding-rate data (paper charges the same
flat pessimistic rate as the backtest — that parity is deliberate, see the
decision log); retry/backoff on Kraken and crash-recovery chaos tests are
Slice 6 as planned.

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
│   ├── backtest/      # engine + metrics (S0, extended S1, shared helpers S5)
│   ├── live/          # tick_engine (S5)
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
  **Amended 4 Jul 2026: moved to Slice 5.** The flat assumption charges
  funding pessimistically in both directions, so it can only understate
  backtest results — the walk-forward verdict stays conservative without
  real funding data, and the live loop needs that data anyway.
- **SQLAlchemy 2.0 over SQLModel** (4 Jul 2026): the native typed ORM
  (`Mapped[]`/`mapped_column`) passes basedpyright strict, and it keeps
  Pydantic at the system boundaries per the type discipline — SQLModel's
  Pydantic-SQLAlchemy hybrid classes would blur exactly that line.
- Slice 4 built before Slice 3 (4 Jul 2026, user decision): pure
  infrastructure, independent of the validation work. Slice 3 stays the gate
  for xgb_v1 — nothing in Slice 4 promotes or trades a strategy.
- API DI via `app.dependency_overrides` on a typed stub (`api/deps.py`)
  instead of `app.state` — keeps handlers fully typed, tests inject fakes the
  same way (4 Jul 2026).
- **Holdout boundary: 2025-07-01** (4 Jul 2026) — everything from that
  timestamp on is holdout (~12 months, growing as new bars arrive); protocol
  and usage log in `HOLDOUT.md`, clamp enforced in `run_walkforward.py`.
  **Amended 5 Jul 2026: boundary moved to 2026-07-04** by applying HOLDOUT.md
  rule 4 — review found the original holdout year had been observed at
  aggregate level (full-history baseline backtests; `train.py`'s unclamped
  validation split). The 2025-07 → 2026-07 year is development data now and
  the holdout regrows from the new boundary. Enforcement centralized in
  `application/holdout.py` and applied in every dev entry point (`train.py`,
  `backtest.py`, walk-forward); H2's walk-forward keeps evaluating on data
  before 2025-07-01 (`H2_EVAL_END`) so iterations stay comparable.
- Supplementary spot training data: **not needed** (4 Jul 2026) — the 3.3y
  development window hosts 5 walk-forward folds / 15 OOS months, enough for
  a verdict; staying futures-only keeps microstructure and costs consistent
  with the traded instrument.
- Deflated-Sharpe trial registry (4 Jul 2026): `TRIAL_SHARPES_ANNUALIZED` in
  `application/run_walkforward.py` counts strategy *candidates*, not
  diagnostic reruns — the ma-cross-under-v1-rules run (−10.1) is excluded as
  a mechanics mismatch of the same hypothesis (finding #2). Every new
  candidate must be appended there before its results are read.
- **Hypothesis pre-registration** (5 Jul 2026): every strategy/feature
  hypothesis gets a `HYPOTHESES.md` entry — motivation, exact spec with
  a-priori parameters, success criteria — *before* its evaluation runs;
  verdicts are appended, never edited. First use: H3 (market-structure
  features) → null result, keep the 13-feature set.
- **Tick execution model** (5 Jul 2026): the paper/live tick processes the
  just-closed bar exactly as the backtest does (barriers against its
  high/low with stop-wins-ties, funding + time exit at its close) and fills
  the fresh signal at tick time — the last close standing in for the next
  open, a gap well inside the slippage assumption. Parity is enforced by a
  test that runs the same bars/signals through both engines and demands
  identical trades and cash. Shared mechanics live as pure functions in
  `core/backtest/engine.py`; `TickEngine` in `core/live/`.
- **Paper funding stays flat** (5 Jul 2026, amends the 4 Jul funding
  decision): paper charges the same flat pessimistic rate the backtest
  charges, so a paper run is comparable to the walk-forward verdict that
  justified promoting the strategy. The real funding-rate adapter moves to
  Slice 6/7 with the other live-hardening work — live capital genuinely
  needs it; paper parity is better served without it.
- **Promotion by config name** (5 Jul 2026): `bot_commands` (singleton row)
  holds `is_paused` + `promoted_strategy` (a `strategy_configs.name`); the
  API validates the name on promote. One live strategy at a time, exactly
  as CLAUDE.md prescribes.

**Open (decide later, not now):**

- Alerting channel (email vs Telegram) → Slice 6.
- Frontend: bare SvelteKit routes suffice for now; FSD only when the dashboard
  grows.

---

## Backlog / explicitly not now (see `CLAUDE.md` → "What we do NOT do")

- No auto-search / optimize-until-profitable.
- No order-book/tick features, RL, or deep learning in v1.
- No leverage > 2x in v1.
