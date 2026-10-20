---
status: accepted
date: 2026-10-20
---

# Score what the hourly candle allows: tolerance B, a scoring period from 2016, per-era bars

The slice 2 harness scored a mark as a hit when its close was within 2% of the extreme. Measured in hindsight over the development period, the close of the extreme hourly candle itself is a median 1.70% from the extreme and only 54.8% of turning points have it within 2%: a detector with perfect timing would score 55%, and the hourly candle after the extreme, the earliest any causal rule can react, is within 2% for 33.4%. The years 2013 to 2015 are missing 40%, 62% and 50% of their hours, hold 31.5% of all turning points with a median swing of 7 candles, and contain three impossible hourly prints that became turning points. On 20 October 2026 the owner therefore ruled, under ADR-0004:

- **Tolerance B**: a mark is a hit when a turning point of its kind lies within 24 hourly candles and the mark's close is within 2% of the extreme, or no further from it than the extreme hourly candle's own close when that is further. The 24 candles and the 2% are unchanged.
- **Scoring period** from `2016-01-01T00:00:00Z` to the out-of-sample boundary. Replays still start at the first stored candle so a detector carries its state in, but nothing before the period is scored.
- **Three prints dropped** at import, by a hand list of their hours (UTC): 2013-11-07 07:00 (high 3,484), 2013-11-10 04:00 (high and close 4,000), 2013-11-12 06:00 (high 4,000). A scan of all eleven years against neighbouring closes finds nothing else, so there is no general rule.
- **Eras**: 2016 to 2018, 2019 to 2021, 2022 to 2024. The score is given for the whole period and per era, and the hit-rate bar must hold in every era.
- **Bars**: hit rate at least 80% in every era; false marks at most equal to hits over the period; no separate give-up bar, since the tolerance already states the acceptable give-up per turning point, and median give-up stays in the score and in every prediction.
- **No adaptive parameters.** Rules are scale-free where they can be, expressed in the reversal size and the candle rather than in fitted numbers, and the per-era bar refuses a rule that only works in one regime.

## Considered options

Tolerance, with the hindsight ceilings over the development period:

| tolerance | extreme candle is a hit | next candle | best close within 24 candles |
| --- | --- | --- | --- |
| A: within 2% of the extreme, as before | 54.8% | 33.4% | 86.7% |
| B: 2%, or the extreme candle's own close | 100% | 45.8% | 100% |
| C: a quarter of the swing, at least 2% | 73.3% | 55.4% | 94.3% |

B was chosen as the smallest change that stops failing a perfect mark. C ties the bar to the trade, a median swing of 14% giving a median tolerance of 3.5%, but still fails a perfect mark one time in four.

Scoring period: keeping 2013 was rejected because the hit rate was dominated by thin, gappy years whose swings a 24-candle tolerance spans three times over; 2017, the first year with no missing hours, was passed over because 2016 misses only 2% and adds just 36 turning points, so the cut went where the series becomes continuous.

False-mark bar: "lower than the floor's" was dropped because the floor no longer sets any bar; "at most two per hit" and "a rate of at most 80%" were considered. "At most equal to hits" was chosen because it says what a detector is: right at least as often as wrong. No candidate so far is within a mile of it, and that is recorded knowingly.

Adaptive parameters, estimated from the recent past, were rejected as fitted indicators by another name (ADR-0003). Run length at the extreme is stable from 2016 on, with 73% to 79% of turning points ending a run of two or more; what changes across eras is the time scale, which rules in candles and percentages already absorb.

## Consequences

- The floor, detector one and detector two are re-scored under these definitions in slice 5 and the numbers appended to #11, #12 and #16.
- Dropping the three prints removes two spurious levels, 3,484 and 4,000, that detector one would otherwise meet in 2017; the scoring period alone would not have removed them.
- This decision is conservative for the candidates: most of their recorded hits fell in the years now unscored.
