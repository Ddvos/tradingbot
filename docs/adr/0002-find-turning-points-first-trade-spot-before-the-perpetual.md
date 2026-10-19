---
status: accepted
date: 2026-10-19
---

# Find turning points first, trade spot before the perpetual

ADR-0001 chose to trade the Kraken BTC perpetual long and short at 1x and rejected spot because spot cannot earn on a fall. On 19 October 2026 the owner reordered the project. Every earlier attempt went straight from market data to trading rules and lost to costs; this time the bot must first prove, visibly on a chart, that it can find Bitcoin's tops and bottoms. So the project builds a detector of turning points, scored in hindsight through replay against a pre-registered success criterion. Only a detector that passes earns a strategy, and that strategy first trades spot, long or cash, because spot has no funding, no liquidation and no forced stop. The perpetual, with its short side, comes after spot trading has proven out. The candle store therefore holds spot BTC/USD, whose public history reaches back to 2013, rather than the perpetual's, which starts in March 2022.

## Considered options

- **Keep ADR-0001's order: a strategy on the perpetual straight away.** Rejected. The owner wants the turning points proven in isolation first, and the perpetual adds funding, liquidation and stops before the core question is answered.
- **Detector first, then the perpetual directly, skipping spot.** Rejected. The first real-money phase should be the simplest possible; spot long-or-cash needs no funding model, no stop and no liquidation logic.
- **Detector first, then spot, then the perpetual.** Chosen.

## Consequences

- ADR-0001's instrument reasoning still holds for the final phase; only its rejection of spot is superseded, and only for the first trading phase.
- A detector is a separate concept from a strategy: a detector turns candles into marks, a strategy turns marks into a position. Both have their own success criteria.
- Turning points are defined in hindsight by a reversal size. A detector places marks only on the latest candle and is scored on hits, misses, false marks, timing and give-up, only ever through replay, so no future candle can leak.
- Readable rules come first. Any AI or reinforcement-learning detector must beat the readable detector on the same score through the same replay before the project adopts it.
- Risk per trade, the drawdown halt and the account size are decided when spot trading starts, not now.
- Funding only has to be modelled once the perpetual phase begins.
