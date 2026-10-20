---
status: accepted
date: 2026-10-20
---

# Marks on 15-minute candles, turning points and tolerance on hourly candles

Family one's mechanism, marking the hourly candle that fails to extend the move, is capped by the hourly candle itself: in the scoring period that candle's close is within tolerance B for 48.4% of turning points, a median 2.66% from the extreme. The same measurement on 15-minute candles, pulled from Kraken's archive and clamped to the out-of-sample boundary, gives 84.7%, a median 1.59%. On 20 October 2026 the owner ruled that family two's detectors read 15-minute candles and place their marks at 15-minute closes, while everything that defines the target stays hourly: turning points at the 8% reversal size, tolerance B measured against the extreme hourly candle's close, the 24-candle window counted in hourly candles by the hour a mark falls in, timing in hourly candles, and the eras. Inside a 15-minute replay the hourly candles are built from the 15-minute stream as each hour completes and checked against the stored hourly table. A detector places at most one mark per 15-minute candle.

Tolerance B stays on the hourly candle on purpose. Held to its own 15-minute candle, the swing rule of detector three scores 71.7% instead of 87.3% over the scoring period, and under plain 2% it scores 65.0%. A causal detector can never mark the extreme candle itself, at any timeframe, so a yardstick that shrinks with the detector's candle always demands the impossible by roughly the same margin. The target is the hourly turning point; the yardstick is what an observer of hourly candles could have done; a detector on finer candles that beats that is genuinely better, and its give-up is reported in plain percent so the gain stays visible.

## Considered options

- **Stay hourly and mark early, during the run.** Rejected: a close within 2% exists in the run before the extreme for 64.6% of turning points, but no pure-price selector in the hindsight tables separates those candles from the 29 others per turning point; the near-turn rate stays between 5.7% and 16%.
- **Tolerance B on the mark's own candle.** Rejected for the reason above, with its number recorded here.
- **5-minute or 1-minute candles.** Not now: the archive has them, but the 15-minute ceiling already clears 80%. Finer candles are a later family if give-up must fall further.

## Consequences

- Store, import, catch-up, replay, scoring, the API and the dashboard learn a fifteen-minute timeframe (slice 5). A 15-minute replay has four times the candles.
- The floor stays an hourly reference; no 15-minute floor is built, since the bars are absolute (ADR-0005).
- Family one is closed on #16 with the 48.4% ceiling as its refuting fact; family two opens with its own hypothesis and its own single out-of-sample check.
