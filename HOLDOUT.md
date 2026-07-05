# Holdout protocol

> The final exam of a strategy. Read this before touching any data after the
> boundary below. Referenced from `ROADMAP.md` (Slice 3) and enforced in code
> by `application/holdout.py` (`HOLDOUT_START`).

## The boundary

**Holdout = all PF_XBTUSD data with `timestamp >= 2026-07-04T00:00:00Z`.**

Everything before it is development data: walk-forward folds, feature work,
label experiments, threshold and risk-rule choices all live there. The
holdout starts (nearly) empty and grows as new bars arrive (~720 per month)
— data the strategy has genuinely never seen.

**Boundary history:** originally 2025-07-01 (declared 4 Jul 2026). Moved to
2026-07-04 on 5 Jul 2026 by applying rule 4 to two contamination events
found in review (see the usage log below). Note for H2: its walk-forward
iterations keep evaluating on data before 2025-07-01 (`H2_EVAL_END` in
`application/holdout.py`) — not as holdout discipline but so iterations 2–5
stay comparable to iteration 1, which was scored on exactly that window.

## Why it exists

Walk-forward validation is honest about *time* (every prediction is
out-of-sample), but not about *iteration*: every time we look at walk-forward
results and adjust anything — a feature, a threshold, a hyperparameter — we
leak information about the development period into our choices. After five
iterations the walk-forward numbers are quietly overfit to the development
data. The holdout answers one question those iterations cannot contaminate:
**does the frozen, finished strategy work on data nobody has ever looked at?**

## The rules

1. **One shot per strategy.** A strategy family (model + features + labels +
   threshold + risk rules) gets exactly one holdout run, ever. Run it only
   when walk-forward results already justify going to paper trading — the
   holdout confirms a decision, it never drives one.
2. **Freeze first.** Before the run: commit the exact config, and record what
   result was expected. The holdout run uses the same walk-forward procedure
   (rolling retrain, same costs), only on holdout data.
3. **The result is final.** Good → proceed to paper trading. Bad → the
   strategy family is rejected. There is no "fix it and try the holdout
   again" — any variant designed after seeing holdout results is already
   contaminated by them.
4. **Burned is burned.** If holdout data influences development in any way —
   even a glance at a chart to "understand what went wrong" — that data
   moves permanently into the development set, and the holdout boundary
   moves forward to data that arrived since. Log it below either way.
5. **Failed hypotheses don't unlock a rerun.** Max 5 development iterations
   per hypothesis (CLAUDE.md → Strategy development cycle), then a *new*
   hypothesis — which, being a new strategy family, gets its own single
   holdout shot on the then-current boundary.

## Enforcement

- `application/holdout.py` owns the boundary; `clamp_to_development()` caps
  every caller-supplied window at `HOLDOUT_START`, so no code path can cross
  it.
- Every development entry point that reads market data clamps through it:
  `scripts/train.py`, the `run_strategy` use case behind `scripts/backtest.py`,
  and `run_walk_forward()`. None of them exposes a flag to cross the boundary.
- `scripts/backfill.py` deliberately does **not** clamp: collecting holdout
  bars into Parquet is required — reading them during development is what's
  forbidden.
- The one-time holdout run will get its own explicitly named script when a
  strategy earns it — crossing the boundary must never be a default code path.

## Holdout usage log

| Date | Strategy family | Verdict | Notes |
|---|---|---|---|
| 2026-07-03 | (market-level) | burned | Full-history backtests (buy-and-hold Sharpe 0.21, MA-cross −0.59, `ROADMAP.md` → "The honest numbers") were computed through 2026-07-02, observing aggregate behavior of the then-holdout year before the boundary was even declared. |
| 2026-07-04 | xgb_v1 | burned | `scripts/train.py` had no clamp: its 70/30 chronological split put ~78% of the validation window past 2025-07-01, and the printed validation AUC 0.656 / IC 0.208 were read as development feedback. |
| 2026-07-05 | — | rule 4 applied | Both events logged; boundary moved 2025-07-01 → 2026-07-04; clamps added to every dev entry point (this commit). The 2025-07 → 2026-07 year is development data now. |
