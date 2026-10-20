---
status: accepted
date: 2026-10-20
---

# False marks are reported per hit, not barred; each strategy prices them

Detector three, the first iteration of family two, passed the hit-rate bar in every era on 20 October 2026 (90.0%, 89.8% and 91.1%) and failed ADR-0005's false-mark bar with 4,698 false marks against 719 hits, 6.5 per hit. The looks recorded on #20 say why no rule that reads candles will pass that bar. At the first fifteen-minute candle short of the extreme a top and a pause in a trend look alike, and the harness leaves no room to wait for the difference: the next hourly candle's close is within tolerance B for only 48.4% of turning points (ADR-0006). In hindsight, free of any detector, a swing that has reached the reversal size shows a median 4 and a mean 6.7 pauses before its turning point, 21.8% of turning points show exactly one, and a top's swing shows twice the pauses of a bottom's (a mean of 9.0 against 4.5). Of the recorded run's false marks, 54.8% were pauses in a trend that went on a median 10.4% further. Of twelve price-structure conditions read at the pause, none lifts the share of marks at a turn past 25% in any bucket. The three waits that fit inside tolerance B reach 4.2 false marks per hit at best, and the fall below the last higher low, the earliest structural confirmation, sits a median 4.2% below the extreme and is within tolerance B for 19.8% of turning points. A bar of one false mark per hit therefore asks a rule to pick the one true pause out of a median four that look alike within 2% and 24 hours. On 20 October 2026 the owner ruled, under ADR-0004:

- **No false-mark bar.** A detector's success criterion is the hit-rate bar of ADR-0005, at least 80% in every era under tolerance B over the scoring period, and nothing else. The score reports **false marks per hit**, for the period and per era, next to the false-mark rate, and every pre-registration predicts it.
- **Each strategy prices its false marks.** A false mark costs money only once a strategy acts on it, and the cost differs by market: in spot a false top mark is a sale into a rising market, the move missed until the next bottom mark; in the perpetual it is a short against the trend, plus funding. Each strategy's backtest charges its false marks at its own fees and rules, and the strategy's success criterion, beating the benchmark after costs, is where false marks are barred. The detector stays free of any market, usable by the spot strategy and the perpetual strategy alike (ADR-0002).
- **Family two's one out-of-sample check goes to detector three as it stands** (#28), under this criterion. The 1% depth variant measured on #20 (87.3% kept, 4.2 false marks per hit) is not sent instead: picking the iteration by the development tables is the selection the one check exists to catch.
- **The four recorded runs are re-scored** with the per-hit line and the numbers appended to #11, #12, #16 and #20 (#27). No other number changes, because no definition does.
- **The 13 September 2019 flash spike stays** (#26). A scan of the development period's hourly highs and lows against the neighbouring closes finds 33 candles in the scoring period with a wick of 8% or more, among them the crashes of 13 March 2020, 19 May 2021 and 4 December 2021; the spike is the only two-sided one. It traded, and a hand list for traded candles, or a rule fitted to one candle, would be the goalpost moving ADR-0004 forbids. Its two turning points, of 798, stay in the score.

## Considered options

- **Keep both bars.** Rejected: the looks leave trade-by-trade order flow as the only input ADR-0003 still allows, gigabytes of data for an ingredient whose coarser forms, volume and trade count at the extreme, showed no lift on #20; and the four iterations family two has left would be spent proving what the tables already show.
- **A relaxed bar, such as three false marks per hit.** Rejected: every number between one and 6.5 is read off the development tables, which ADR-0004 forbids, and no measured rule reaches three while keeping 80% in every era.
- **A third outcome for marks near a turn that another mark hit**, 16.1% of the recorded false marks. Rejected for the reason ADR-0004 gave ladder scoring: a mark stays one claim. The glossary's wording of "false mark" is tightened to match the score instead.
- **Report false marks per hit, bar them in the strategy.** Chosen.

## Consequences

- The detector phase proves that a detector finds the turns, nine in ten within a median 1.3% for detector three, and reports how often it cries wolf. Whether that is affordable is a strategy question with a price in money, a better bar than any count picked today.
- A strategy backtest may find six false marks per hit unaffordable. The way back is then a new family with its bar stated as a cost per false mark, checked on a forward out-of-sample period, since the one before the boundary will have been read; paper trading provides such a period anyway.
- ADR-0005's bars bullet is superseded in its false-mark clause only; the hit-rate bar, tolerance B, the scoring period and the eras stand.
- The scripts behind the facts above are recorded with their tables: the looks and the pause count on #20, the spike scan on #26, as ADR-0004 asks.
