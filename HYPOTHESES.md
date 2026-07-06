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

## H2 — ML triple-barrier momentum (xgb_v1) ❌ folded after 3 of 5 iterations (6 Jul 2026)

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

### Iteration 3 — 4h decision timeframe (pre-registered 6 Jul 2026)

**Change (timeframe only — mapping, model, features, label shape
unchanged):** decisions move from 1h to 4h bars, still PF_XBTUSD futures.
Same 13 causal features computed on 4h bars; same triple-barrier labels
(2.0×ATR target / 1.5×ATR stop / 6-bar time barrier — now a 24-hour
horizon); same hysteresis mapping as iteration 2 (enter long at
P ≥ 1.5× the fold's training base rate, stay while ≥ 1.0×, signal-only
exits, `HOLD_RULES`).

**Why this change (reasoned before running):**

- The emerging pattern across H1–H4 and both H2 mappings names
  cost-per-decision, not signal quality: a real edge (pooled OOS IC 0.218,
  stable) is worth less per 1h decision than the ~0.3% round-trip cost.
- On 4h bars each decision spans 4× the time. Volatility grows roughly
  with √time, so the typical move per decision (and the ATR-scaled
  barriers) roughly doubles while the round-trip cost stays fixed — edge
  per decision vs cost improves ~2×, and decision count falls ~4×.
- Iteration 2's mapping is kept byte-identical so iterations 2 and 3
  differ only in the clock: if 4h materially improves on −1.93, the
  cost-per-decision diagnosis is confirmed; if not, this signal likely
  cannot clear retail costs at any of these speeds.

**Specification (all fixed a priori):**

- Data: PF_XBTUSD 4h (Kraken charts API serves 2022-03-23 onward, same
  as 1h — 9,398 bars backfilled 6 Jul 2026). Same evaluation window as
  iterations 1–2: clamped to `H2_EVAL_END` 2025-07-01 for comparability.
- Feature/label windows are **bar-parameterized by design** (as the 1h
  set was defined): ATR(14) = 14 four-hour bars, the 6-bar label horizon
  = 24h. No calendar-matching of window lengths — that would be a new
  feature set, i.e. a different hypothesis.
- Walk-forward geometry, same calendar durations as iterations 1–2:
  train 4,380 bars (2y) / test 540 bars (90d) / purge 6 (= label
  horizon) / min test 180 bars (30d) / embargo **24 bars** (96h —
  bar-count parity with the 1h runs, deliberately more conservative in
  calendar time). Fresh model per fold, same fixed XGBoost
  hyperparameters.
- Costs: same pessimistic assumptions — 0.05% taker, 0.1% slippage, and
  the same ~11%/yr flat funding, charged per bar **scaled to bar
  duration** (0.00005 per 4h bar; the 1h engine charged 0.0000125 per 1h
  bar). Bootstrap CI keeps one-day blocks (6 bars on 4h) — calendar
  parity with iterations 1–2.
- Known risk, accepted: each fold trains on 4,380 samples instead of
  17,520 — a weaker model is possible. IC/AUC are therefore reported per
  fold; if the 4h signal itself collapses (pooled OOS IC < 0.10) the
  iteration is rejected on signal grounds, distinct from the cost
  question.

**Protocol:** identical walk-forward machinery, run
`uv run python scripts/walkforward.py --name xgb_v1_4h_hysteresis --timeframe 4h --mapping hysteresis`.
Registered as trial `ml_xgb_v1_4h_hysteresis` when read.

**Success criteria (pre-registered, identical to iteration 2):**

- **Pass** (→ holdout consideration per the development cycle): OOS
  Sharpe > buy-and-hold over the same test windows **and** profit factor
  > 1.0 **and** ≥ 30 trades.
- **Progress, iterate again**: 0 < OOS Sharpe ≤ buy-and-hold —
  pre-register iteration 4 first.
- **Reject the iteration**: OOS Sharpe ≤ 0 (or the IC-collapse clause
  above). Three of five H2 iterations then spent.

**Result — rejected, 6 Jul 2026.** Run `4h_xgb_v1_4h_hysteresis_20260706_200940`:

- OOS Sharpe **−2.27** (criterion: > 0 to survive; buy-and-hold did 0.69
  on the same windows). Bootstrap 95% CI [−3.94, −0.57] — solidly
  negative. Final equity 10,000 → 4,513, max DD −56.4%. Deflated Sharpe
  0.000.
- The timeframe did what it promised *mechanically*: 152 trades (vs 360
  at 1h), each decision spanning 4× the time. The economics got **worse**,
  not better: profit factor 0.55 vs 0.77 at 1h, win rate 0.375.
- The signal weakened on 4h but did not collapse: pooled OOS IC 0.188
  (1h: 0.218; the pre-registered floor was 0.10), AUC 0.636, per-fold IC
  0.123–0.267. The quarter-sized training windows (4,380 samples) are the
  likely cause — the risk the spec accepted.
- **This result weakens the cost-per-decision diagnosis.** If round-trip
  costs were the binding constraint, fewer and larger decisions should
  have helped; they hurt instead. The loss concentrates where iteration
  2's did: a long-only regime riding elevated P through periods where the
  model kept disagreeing with realized direction (fold 0, 2024-04→07:
  Sharpe −4.71, PF 0.20). The one mildly positive fold is again
  2025-03→06 (Sharpe 0.12, PF 1.03).
- Registered as trial `ml_xgb_v1_4h_hysteresis` (−2.27). **Three of five
  H2 iterations spent.** If iteration 4 is proposed, the evidence now
  points away from further cost mitigation and toward the mapping's
  directional asymmetry — a long-only conversion of a ranking signal
  whose IC measures ranking, not long-side profitability. Candidates
  consistent with this evidence: a symmetric short side, or
  confidence-scaled sizing (needs fractional-position engine support).
  Pre-registered first, as always.

### Fold decision — 6 Jul 2026, after 3 of 5 iterations

H2 is folded without spending iterations 4–5, on arithmetic rather than
another run. The label is a bet that wins +2.0×ATR or loses −1.5×ATR, so
break-even needs a win probability of 1.5/3.5 ≈ **0.43** before costs;
with ~0.3% round-trip costs (≈0.5×ATR on 1h bars) the bar rises to
roughly **0.55–0.60**. The model's probability distribution (base rate
0.18, AUC 0.66) almost never reaches that region — which is exactly why
threshold 0.6 fired 4 trades in 15 months. Iteration 1 was not unlucky;
the model was correctly reporting that the barrier bet is almost never
+EV. The regime mappings (iterations 2–3) sidestepped the barriers but
thereby traded something the model was never trained to predict, and
both lost. The remaining candidates cannot escape this bind:
confidence-scaled sizing scales exposure but cannot flip a negative
expectancy, and a symmetric short side trades low-P bars that the label
construction says mean "chop" as much as "down".

**What survives the fold:** the feature pipeline, triple-barrier
labeling, walk-forward machinery, and the finding that a stable OOS IC
(0.19–0.22) is *not sufficient* for a tradable strategy — the label must
define a bet the model's confidence distribution can actually clear
after costs. Any future ML hypothesis should design the label around
that constraint from the start.

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

---

## H5 — Daily time-series momentum ✅ passed its gate — weak evidence, candidate (6 Jul 2026)

### Hypothesis

Time-series momentum — an asset's own trailing return predicts its next
return — is the most robustly documented anomaly in the systematic-trading
literature (Moskowitz, Ooi & Pedersen 2012; Rob Carver's core assumption),
persisting across asset classes and decades, and usually attributed to slow
capital flows and behavioral under-reaction. Every trend hypothesis
rejected so far (H1, H4, H2's regimes) operated at 1h–4h, where BTC's
trend-per-decision is smaller than retail costs. At a *daily* horizon the
cost arithmetic inverts: a position held for weeks pays ~0.3% round-trip
against moves of 10–30%. The specific claim: the sign of BTC's trailing
90-day return, traded long/short on daily bars, beats buy-and-hold net of
pessimistic costs.

### Specification (all fixed a priori — no tuning against results)

- Timeframe: **1d** bars, PF_XBTUSD (1,566 bars backfilled 6 Jul 2026,
  2022-03-23 onward — same depth as 1h/4h).
- Signal per bar close: trailing return over **lookback = 90** bars
  (~3 months). Positive → **LONG**, negative → **SHORT**, warmup (first 90
  bars) or exactly zero → **FLAT**. 90 days sits inside the 1–12-month band
  the literature supports and respects crypto's faster cycles vs the 4.3y
  sample; chosen on that reasoning, not searched.
- Execution: signal-only exits, all-in sizing, no stop/TP/time exit
  (`HOLD_RULES` — exits matched to the signal's multi-week horizon, ROADMAP
  finding #2). Standard pessimistic costs: 0.05% taker, 0.1% slippage, flat
  ~11%/yr funding charged per bar scaled to the 1d duration, both
  directions.
- Long **and** short: the literature's TSMOM is symmetric, and the flat
  funding assumption charges (never pays) both sides, so shorts are not
  subsidized by the cost model.

### Protocol

- One backtest over the development window (auto-clamped to
  `HOLDOUT_START` 2026-07-04):
  `uv run python scripts/backtest.py --strategy ts_momentum --timeframe 1d`.
- Baseline: buy-and-hold over the same window on the same 1d bars
  (`--strategy buy_and_hold --timeframe 1d`) — the 1h baseline Sharpe 0.21
  is not comparable across bar sizes.
- The candidate is appended to `TRIAL_SHARPES_ANNUALIZED` as
  `tsmom_90d_1d` when the run is read.

### Success criteria (pre-registered)

- **Pass** (→ candidate for the development cycle's next gate): annualized
  Sharpe > buy-and-hold on the same 1d window **and** profit factor > 1.0
  **and** ≥ 10 closed round-trips (below that, one lucky trend carries the
  number).
- **Reject** otherwise.
- Power caveat, stated up front: ~4.3 years of daily bars holds on the
  order of 15–25 independent trend decisions. Even a pass is weak evidence
  — it earns the walk-forward/holdout path, not a promotion. Iterations
  (≤ 5, pre-registered) may vary the *rules* (e.g. a vol-scaled position,
  a slower/faster class of lookback), but never scan the lookback against
  results.

### Result — pass on all three criteria, 6 Jul 2026 (weak evidence)

Development window 2022-03-23 → 2026-07-03, 1,564 bars (equity curve
`data/processed/equity/PF_XBTUSD/1d_ts_momentum.parquet`):

- Annualized Sharpe **0.33** vs buy-and-hold **0.22** on the same 1d
  window (criterion: beat it) — pass.
- Profit factor **1.44** (criterion: > 1.0) — pass.
- **56** closed round-trips (criterion: ≥ 10) — pass.
- €10,000 → €12,391 vs buy-and-hold's €8,112; max drawdown −52.8% vs
  −70.6%. Win rate 30.4% — the textbook trend-following shape (many small
  losses, few large wins), which is what the hypothesis predicts and a
  fitted artifact would not need to look like.

Supplementary significance (diagnostic, computed once — not criteria):
moving-block bootstrap 95% CI for the Sharpe **[−0.58, 1.25]** (one-week
blocks); probabilistic Sharpe P(SR > 0) = **0.756**; deflated Sharpe vs
the 8-trial registry ≈ **0.003**. In words: the point estimate beats the
baseline, but 4.3 years cannot statistically separate this from luck,
exactly as the power caveat anticipated. First strategy in the project to
pass a pre-registered gate; the pass earns candidacy, not belief.

**Next gate:** the holdout is 2 days old (regrowing since the 2026-07-04
boundary move) and useless for years — so the only genuinely
out-of-sample test available is **paper trading** (Slice 5, built and
idle). Promoting H5 requires two pieces of plumbing: 1d-tick support in
the live runner (today hard-cron'd hourly) and a `ts_momentum` strategy
kind in the live config factory. Registered as trial `tsmom_90d_1d`
(0.33).

---

## H6 — Funding-rate carry 📅 registered 6 Jul 2026 — evaluation deferred to ≥ 2027-07

### Hypothesis

Perpetual funding transfers wealth from the crowded side to the other
side, by construction: when leveraged longs bid the perp above index,
longs pay shorts every hour, and vice versa. Sustained extreme funding
therefore *pays* a position held against the crowd — an income stream
that, unlike H1–H5, does not require forecasting price at all. This is
the classic carry risk premium, documented across FX, rates, and crypto;
the compensation is for bearing the crash risk of the crowded trade
unwinding through you.

### Data reality (the reason evaluation is deferred)

Kraken serves hourly funding settlements but **only the trailing ~12
months**, with no pagination (verified 6 Jul 2026: 8,859 rows,
2025-07-02 → 2026-07-06). Twelve months of carry data contains too few
funding-extreme episodes to decide anything. The archive
(`data/raw/funding/PF_XBTUSD.parquet`, `FundingStore`) is therefore the
system of record and **must be grown by running
`scripts/backfill_funding.py` at least monthly** — every skipped month
is lost forever. Evaluation runs when the archive spans **≥ 24
contiguous months** (≈ July 2027 at the earliest).

### Specification (fixed now, so 2027-us cannot tune against the data)

- Decisions on **1d** bars at close. Signal: trailing **7-day** mean of
  hourly `relative_rate`, annualized (×24×365). **SHORT** when >
  **+22%/yr**, **LONG** when < **−22%/yr**, **FLAT** otherwise.
  Signal-only exits, all-in sizing.
- The ±22%/yr threshold is anchored at 2× the project's long-standing
  flat pessimistic funding assumption (~11%/yr), not scanned. Disclosure
  of degrees of freedom: the trailing-year funding distribution (calm,
  ~3–6%/yr) was visible when these numbers were fixed; the anchor to a
  pre-existing constant is the defense.
- Engine prerequisite (build when evaluating, not before): the backtest
  must charge/credit **real signed funding** from the archive — longs
  pay positive rates and receive negative ones, shorts the mirror — in
  place of the flat both-ways charge. This adapter is needed for live
  trading (Slice 6/7) anyway.

### Success criteria (pre-registered)

- **Pass**: annualized Sharpe > buy-and-hold over the same window
  **and** profit factor > 1.0 **and** ≥ 10 closed round-trips.
- **Reject** otherwise. Time-in-market is reported (carry is mostly
  flat) but decides nothing. Iterations (≤ 5, pre-registered) may vary
  the rules, never scan thresholds against results.
