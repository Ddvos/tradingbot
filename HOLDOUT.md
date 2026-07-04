# Holdout protocol

> The final exam of a strategy. Read this before touching any data after the
> boundary below. Referenced from `ROADMAP.md` (Slice 3) and enforced in code
> by `application/run_walkforward.py` (`HOLDOUT_START`).

## The boundary

**Holdout = all PF_XBTUSD data with `timestamp >= 2025-07-01T00:00:00Z`.**

Everything before it is development data: walk-forward folds, feature work,
label experiments, threshold and risk-rule choices all live there. The
holdout is roughly the final 12 months of history and keeps growing as new
bars arrive — data the strategy has genuinely never seen.

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

- `run_walk_forward()` clamps all data to `timestamp < HOLDOUT_START`
  unconditionally; the walkforward CLI exposes no flag to cross it.
- The one-time holdout run will get its own explicitly named script when a
  strategy earns it — crossing the boundary must never be a default code path.

## Holdout usage log

| Date | Strategy family | Verdict | Notes |
|---|---|---|---|
| — | — | — | never used |
