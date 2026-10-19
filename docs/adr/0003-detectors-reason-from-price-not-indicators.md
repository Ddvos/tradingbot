---
status: accepted
date: 2026-10-19
---

# Detectors reason from price levels and candle structure, not indicators

A detector must place its mark on the latest candle, at or near the turning point itself. Indicators such as moving averages, RSI or MACD are averages of the past, so by construction they confirm a turn only after price has already moved away from it, which is exactly the give-up a detector is scored against. The owner therefore ruled on 19 October 2026 that detectors reason only from raw price: the levels of earlier tops and bottoms, the sequence of higher highs and lower lows in the candles, and, if a later iteration pre-registers it, volume or order flow. No smoothed or averaged indicator is an input to any detector.

## Considered options

- **Classic indicator signals** (moving-average crosses, oscillator extremes). Rejected: they lag by design, and the old project's hourly indicator strategies lost to costs for that reason.
- **Trained models on indicator features.** Rejected for the same reason; the inputs are late before the model sees them.
- **Raw price levels and candle structure.** Chosen. Readable on the chart, no fitted parameters, and the earliest information available about a turn.

## Consequences

- Detector one uses levels from confirmed turning points and the first failed higher high or lower low inside a zone; nothing else.
- Volume per candle and trade-by-trade order flow may be added in later pre-registered iterations, because they are raw market data, not derived averages.
- Order-book data has no public history, so it is not recorded and not used until the owner decides otherwise.
