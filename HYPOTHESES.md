# Hypothesis registry

> **Pre-register before you peek.** Every strategy or feature hypothesis gets
> an entry here *before* its evaluation runs: the economic/behavioral
> motivation, the exact specification with all parameters fixed a priori, and
> the success criteria. The verdict is filled in afterwards and never edited.
> This file is what makes "we tested X" checkable — without it, iteration
> quietly becomes search-until-profitable.
>
> Companion documents: `HOLDOUT.md` (the one-shot final exam),
> `TRIAL_SHARPES_ANNUALIZED` in `application/run_walkforward.py` (the
> deflated-Sharpe trial count), `ROADMAP.md` (where each verdict lands).

---

## H1 — 1h MA-cross trend persistence ❌ rejected (3 Jul 2026)

**Hypothesis:** BTC 1h trends persist long enough that a 20/50 SMA crossover
captures them net of costs.

**Result:** rejected. With exits matched to the signal's horizon the edge is
real but too small: 447 crossings of cost churn beat it (profit factor 0.85,
Sharpe −0.59 vs buy-and-hold 0.21). Full numbers: `ROADMAP.md` → "The honest
numbers" and Findings 1–3.

---

## H2 — ML triple-barrier momentum (xgb_v1) 🚧 open, iteration 1 of 5 spent (4 Jul 2026)

**Hypothesis:** short-horizon direction (hit +2.0×ATR before −1.5×ATR within
6 bars) is partially predictable from 13 causal 1h features; a classifier's
probability clears costs when traded selectively.

**Result so far:** split verdict. The *signal* survives honest validation
(pooled OOS IC 0.218 / AUC 0.664, stable across all 5 walk-forward folds) but
the *strategy* MLStrategy(threshold 0.6) is rejected: 4 trades in 15 OOS
months, Sharpe −1.66 vs buy-and-hold 0.67. The loss is in the
prediction→position mapping, not the model's ranking skill. Report:
`backend/data/processed/walkforward/PF_XBTUSD/1h_xgb_v1_20260704_211036/`.

**Iteration budget:** threshold-0.6 mapping = iteration 1. Up to 4 mapping
iterations remain (each re-validated through the same walk-forward);
candidate ideas: confidence-scaled sizing with a turnover buffer, lower
threshold, symmetric short side.

---

## H3 — Market-structure features improve the ML signal ⚖️ null result — keep v1 (5 Jul 2026)

### Hypothesis

Traders collectively watch the same swing highs/lows: limit orders and stops
cluster around prior extremes, and "higher highs + higher lows" is how
discretionary traders define a trend. Price approaching a prior swing, or a
break of the HH/HL sequence, therefore triggers real order flow that the
current indicator-only feature set (H2's 13 features) cannot see. Adding
causal market-structure features should improve the model's ranking of
triple-barrier outcomes — measured as pooled out-of-sample IC.

This is a **feature hypothesis**, not a new prediction→position mapping: the
label, model, hyperparameters, walk-forward protocol, and costs stay exactly
as in H2.

### Specification (all fixed a priori — no tuning against results)

Swing detection: a **fractal** with half-width **k = 3** — a swing high is a
bar whose high strictly exceeds the highs of the 3 bars on each side (swing
low mirrored on lows). k = 3 defines a local extremum over a 7-hour window,
matching the 6-bar label horizon; chosen on that reasoning, not searched.
Strict inequality means exact-tie double tops do not register — accepted
scope limit.

**Confirmation lag (the no-lookahead rule):** a swing at bar *t* is only
knowable at *t + k*, once the 3 right-hand bars have closed. Every feature
uses exclusively swings whose confirmation bar ≤ current bar. This lag is
load-bearing: without it the backtest knows a top is "in" while a live bot
cannot. Enforced in `core/features/structure.py`, tested by truncation
invariance.

New features (7, added to H2's 13 → 20 total, within the 15–25 target):

| Feature | Definition |
|---|---|
| `dist_sh_atr` | (close − last confirmed swing high) / ATR(14) |
| `dist_sl_atr` | (close − last confirmed swing low) / ATR(14) |
| `higher_high` | 1.0 if last confirmed swing high > the one before it, else 0.0 |
| `higher_low` | 1.0 if last confirmed swing low > the one before it, else 0.0 |
| `range_pos` | (close − swing low) / (swing high − swing low); may exit [0, 1] on breakouts |
| `bars_since_sh` | bars since the last confirmed swing high bar |
| `bars_since_sl` | bars since the last confirmed swing low bar |

ATR(14) normalization keeps distances scale-free (same reasoning as
`atr_pct` in H2). Deferred to a later iteration *if this base set shows
promise*: touch-count levels, multi-timeframe (4H) structure.

### Protocol

- Same purged walk-forward as H2: train 17520 / test 2160 / purge 6 /
  embargo 24, fresh model per fold, pessimistic costs, development data only
  (holdout untouched, boundary 2025-07-01).
- Run: `uv run python scripts/walkforward.py --name xgb_v2`.
- The candidate is appended to the deflated-Sharpe trial registry before
  results are read.
- Comparison baseline: the H2 report `1h_xgb_v1_20260704_211036`
  (pooled OOS IC **0.218**, AUC 0.664, per-fold IC 0.19–0.24).

### Success criteria (pre-registered)

Primary metric: **pooled out-of-sample IC** (signal quality), not Sharpe —
the prediction→position mapping is H2's open iteration axis and threshold
0.6 is known-broken; its Sharpe is reported but does not decide this
hypothesis.

- **Adopt v2 features** if pooled OOS IC ≥ 0.238 (v1 + 0.02) and no fold's
  IC degrades below 0.15.
- **Keep v1 (parsimony)** if pooled OOS IC lands within ±0.02 of v1 —
  7 extra features must pay rent.
- **Reject** if pooled OOS IC < 0.198 (v1 − 0.02) — the features add noise.

One evaluation run decides; no re-runs with adjusted k, normalization, or
feature subsets against these results (that would be a new pre-registered
iteration, and H3 has a budget of 5 like every hypothesis — this run is
iteration 1).

### Result — keep v1 (parsimony), 5 Jul 2026

Run `1h_xgb_v2_20260704_221613` (report under
`backend/data/processed/walkforward/PF_XBTUSD/`):

- Pooled OOS IC **0.2221** vs v1's 0.2180 → +0.004, inside the ±0.02
  parsimony band. Per-fold IC 0.201–0.245 (no fold below 0.15, so no damage
  either). Pooled AUC 0.667 vs 0.664.
- **Pre-registered verdict: keep v1.** The 7 structure features do not pay
  rent — whatever swing structure knows about the 6-bar triple-barrier
  outcome, the momentum/volatility indicators apparently already encode.
- Secondary observations (reported, not criteria): threshold-0.6 fired 10
  trades (v1: 4) at Sharpe −2.12 — the mapping is still the broken part,
  exactly as H2's verdict said. Registered in the trial registry as
  `ml_xgb_v2_structure_features_threshold_0.6` (−2.12).
- Code disposition: `core/features/structure.py` + its tests are kept as a
  library (causal swing detection is reusable), but the features are removed
  from `feature_expressions()` per this verdict. H3 budget: iteration 1 of 5
  spent; remaining pre-registered candidates if someone wants iteration 2:
  multi-timeframe (4H) structure, touch-count levels.
