---
status: accepted
date: 2026-10-20
---

# The harness changes only by ADR, on detector-free facts, and every recorded run is re-scored

After two failed iterations of detector one's family the owner wanted to change the scoring itself: a ladder, where several marks around one turn count as steps of one hit. Regrouping the three recorded runs showed what that would do. The hit rate does not move, because the score already gives each turning point its nearest mark. The false-mark rate falls only by relabelling: detector two's 92.7% becomes 80.8% without one better mark. Scored by the closest step the give-up is hindsight selection; scored by the mean of the steps, which is what acting on every step gets, detector two's 0.96% becomes 1.47% and fails the bar it passed. The floor alternates by construction and never ladders, so it stops being comparable. On 20 October 2026 the owner therefore ruled: a mark stays one claim, and the harness's definitions, the turning point, the mark, the tolerance, the score, the scoring period and the success bars, change only by an ADR written before any run, justified only by hindsight facts about candles and turning points that involve no candidate detector. Every recorded run is then re-scored under the new definitions and the new numbers are appended to its issue, never edited in place. Iterations count detector rules; a harness change costs a family nothing.

## Considered options

- **Ladder scoring.** Rejected for the numbers above. Spreading an action over several marks is position sizing, which ADR-0002 places in the strategy; the idea is parked as an issue for that phase.
- **Changing the harness freely with each iteration.** Rejected: that is moving the goalposts, and the one-run protocol exists to prevent it.
- **Freezing the slice 2 definitions for good.** Rejected: they were fixed before the wick cost of an hourly candle was measured, and a yardstick that fails a perfect-timing mark measures nothing (ADR-0005).

## Consequences

- ADR-0005 and ADR-0006 are the first changes under this rule; the floor, detector one and detector two are re-scored under them in slice 5.
- The hindsight scripts behind every such fact are recorded in the issue that uses them, as #16 did, so a reader can rerun them.
- Reading a recorded run's marks again, as the regrouping above did, is allowed; running a candidate detector before its pre-registration is not.
