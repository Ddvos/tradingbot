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

## H2 — ML triple-barrier momentum (xgb_v1) 🚧 open, iterations 1–2 of 5 spent, both rejected (5 Jul 2026)

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

### Iteration 2 — hysteresis regime mapping (pre-registered 5 Jul 2026)

**Change (mapping only — model, features, labels, folds, costs unchanged):**
the binary threshold 0.6 with per-trade barriers becomes a *regime*: enter
long when P ≥ **1.5×** the fold's training-window base rate; stay long
while P ≥ **1.0×** base rate; flat below. Exits are the signal itself
(`HOLD_RULES`: all-in, no ATR stop, no take-profit, no time exit).

**Why this mapping (reasoned before running):**

- Iteration 1 failed on trade count: with base rate ~0.18 the model almost
  never reaches an absolute 0.6, so the bar must key off the base rate the
  model was trained against, not a fixed number.
- Every strategy so far died of cost churn. The two-bar hysteresis gap is a
  turnover buffer: a P hovering around a single threshold flips positions
  every wobble; enter-high/exit-low merges consecutive warm bars into one
  held position, amortizing entry costs over many bars.
- Per-trade barriers cap winners and force exit/re-enter cycles (ROADMAP
  finding #2 applied to ML: iteration 1's own exits). A regime mapping
  holds exactly as long as the model keeps seeing better-than-base odds.
- Multipliers 1.5/1.0 are fixed a priori: enter on meaningfully
  better-than-base odds, leave when the advantage is gone. Not scanned;
  changing them later is a new pre-registered iteration.

**Protocol:** identical walk-forward (5 folds, purge/embargo, pessimistic
costs), same evaluation window as iteration 1 (`H2_EVAL_END` 2025-07-01)
for comparability. Run:
`uv run python scripts/walkforward.py --name xgb_v1_hysteresis --mapping hysteresis`.
Registered as trial `ml_xgb_v1_hysteresis` when read.

**Success criteria (pre-registered):**

- **Pass** (→ holdout consideration per the development cycle): OOS Sharpe
  > buy-and-hold over the same test windows **and** profit factor > 1.0
  **and** ≥ 30 trades.
- **Progress, iterate again**: 0 < OOS Sharpe ≤ buy-and-hold — the mapping
  direction works but not enough; iteration 3 may refine it (pre-registered
  first).
- **Reject the iteration**: OOS Sharpe ≤ 0. Two of five H2 iterations then
  spent.

**Result — rejected, 5 Jul 2026.** Run `1h_xgb_v1_hysteresis_20260705_203817`:

- OOS Sharpe **−1.93** (criterion: > 0 to survive; buy-and-hold did 0.67 on
  the same windows). Bootstrap 95% CI [−3.66, −0.22] — solidly negative,
  not small-sample noise. Final equity 10,000 → 4,707, max DD −58.5%.
- The mapping did what it was designed to do: 360 trades (vs iteration 1's
  4), win rate 0.392, positions held while the signal stayed warm. The
  economics still lose: profit factor 0.77 — average losers outweigh
  average winners under signal-only exits, and ~0.3% round-trip costs on
  360 trades compound on top.
- The signal itself is unchanged and intact (pooled IC 0.218, AUC 0.664 —
  identical to iteration 1, as expected since only the mapping changed).
  One fold (2025-03→06) was mildly positive (Sharpe 0.55, PF 1.09); fold
  2024-09→12 was disastrous (−5.83) — the regime rode long through a
  period where elevated P kept disagreeing with realized direction.
- **Emerging pattern across H1–H4 and both H2 mappings:** a real but small
  edge (IC 0.22) appears to be worth less than 1h taker costs + slippage
  under every prediction→position mapping tried. Iteration 3 candidates
  that respond to *this* diagnosis rather than re-rolling the dice:
  confidence-scaled position *sizing* (small positions at moderate P —
  needs engine support for fractional positions), or moving the decision
  timeframe up (4h labels/features, fewer decisions each worth more vs
  costs). Registered as trial `ml_xgb_v1_hysteresis` (−1.93). Three
  iterations remain.

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

---

## H4 — Structure trend-following (pure price action, long/short) ❌ rejected (5 Jul 2026)

### Hypothesis

Trend *is* market structure: discretionary traders define an uptrend as
higher highs plus higher lows and a downtrend as the mirror image, and they
position accordingly — so once a structure reversal is *confirmed*, the new
trend attracts follow-on order flow and persists long enough to trade. No
indicators; entries and exits come only from confirmed swing structure.

Prior evidence is respected, not hidden: H1 rejected 1h trend persistence
under an MA(20/50) definition (cost churn beat a real but small edge, PF
0.85 at 447 flips), and H3 found swing structure adds little *6-bar*
predictive information. H4 differs on both counts — a structure-based trend
definition instead of an arbitrary MA pair, symmetric shorts, and far fewer
position flips (a flip needs a full confirmed reversal of both swing
series). That is the specific gap this hypothesis claims matters. The prior
is low; the test is cheap; the criteria below are binding either way.

### Specification (all fixed a priori — no tuning against results)

Swing detection: the H3 fractal, unchanged — `core/features/structure.py`,
half-width **k = 3**, confirmation lag k bars (the no-lookahead rule). Same
value as H3, chosen there a priori; reusing it is deliberate — picking a new
k now would be a degree of freedom.

Signal per bar (causal, from confirmed swings only):

- last two confirmed swing highs rising **and** last two confirmed swing
  lows rising → **LONG**
- last two confirmed swing highs not rising **and** last two confirmed
  swing lows not rising → **SHORT**
- structure mixed (series disagree, or fewer than two swings each) → carry
  the previous signal; **FLAT** until the first full structure confirms

So the position flips only on a fully confirmed opposite structure —
"wait for the reversal to confirm, then follow the trend."

Execution and costs, matched to the thesis (H1 finding #2 — exits must fit
the signal's horizon): signal-only exits, all-in sizing, no ATR stop, no
take-profit, no time exit (`HOLD_RULES`, exactly as ma_cross_trend); the
standard pessimistic costs (0.05% taker, 0.1% slippage, flat funding both
directions).

### Protocol

- One backtest over the development window (clamped automatically to
  `HOLDOUT_START` 2026-07-04 by `run_backtest.py`; the holdout is currently
  regrowing, so the dev window is the full present history 2022-03 →
  2026-07-02): `uv run python scripts/backtest.py --strategy structure_trend --save`.
- The candidate is appended to `TRIAL_SHARPES_ANNUALIZED` when the run is
  read, as `structure_trend_k3`.
- Comparison baseline: buy-and-hold over the same window — annualized
  Sharpe **0.21**, max DD −71% (ROADMAP.md → The honest numbers).

### Success criteria (pre-registered)

- **Pass** (→ candidate for paper trading per the development cycle) if
  annualized Sharpe > 0.21 (buy-and-hold) **and** profit factor > 1.0
  **and** ≥ 30 trades (fewer means the number is luck, not evidence).
- **Reject** otherwise. Iterations (≤ 5 total for H4, each pre-registered
  first) may vary the *rules* — e.g. 4h timeframe where trend-per-cost is
  more favorable — but never scan k or add filters chosen by looking at
  which would have worked.

### Result — rejected, 5 Jul 2026

Run `476d22db` (saved to the dashboard; equity curve
`data/processed/equity/PF_XBTUSD/1h_structure_trend.parquet`), development
window 2022-03-23 → 2026-07-02, 37,499 bars:

- Annualized Sharpe **−2.45** (criterion: > 0.21) — fail.
- Profit factor **0.83** (criterion: > 1.0) — fail.
- 1,388 trades (criterion ≥ 30 — met, abundantly), win rate 30.8%,
  final equity 10,000 → **34** (max drawdown −99.8%). All exits were signal
  flips, so the matched-exit design worked as specified; the signal itself
  loses.
- **Why (diagnosis, not excuse):** k=3 swing structure on 1h bars reverses
  constantly — 1,388 full structure flips in 4.3 years, *three times* the
  churn of MA-cross(20/50)'s 447 crossings — and the edge per flip (PF 0.83)
  is the same size as H1's (0.85). Same disease as H1, worse dose: at 1h
  with retail costs, BTC trend persistence is too weak to pay for the flips,
  under any of the two trend definitions tried so far.
- Registered as trial `structure_trend_k3` (−2.45). H4 budget: iteration
  1 of 5 spent. If anyone proposes iteration 2, the only version consistent
  with this evidence is a *slower* structure — 4h bars (≈4× fewer flips) —
  pre-registered first; k-scanning or entry filters chosen in hindsight
  remain forbidden.
