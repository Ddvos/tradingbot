# TradingBot

The vocabulary of a bot that finds Bitcoin's turning points on a chart and, once it does that well, trades them with real money on one exchange after paper trading has proven it out.

## Market

**Spot**:
Bitcoin itself, bought with and sold for dollars on Kraken. It can be held or sold to cash, never shorted.
_Avoid_: cash market, coin, physical

**Perpetual**:
The Kraken Futures Bitcoin contract the bot trades. It has no expiry and can be held long or short.
_Avoid_: perp, future, contract

**Candle**:
The open, high, low, close and volume of one timeframe's period.
_Avoid_: bar, OHLC, kline

**Timeframe**:
The period one candle covers: one hour, four hours or one day.
_Avoid_: resolution, interval, period

**Position**:
The bot's current exposure in the perpetual: long, short, or flat.
_Avoid_: holding, exposure

**Funding**:
The hourly payment exchanged between long and short holders of the perpetual; a cost or an income of holding a position.
_Avoid_: interest, carry

**Benchmark**:
Buying Bitcoin at the start of a period and holding it to the end. Every strategy is judged against it.
_Avoid_: baseline, control, buy-and-hold strategy

## Turning points

**Turning point**:
A top or a bottom, found in hindsight: the price extreme before the market moved at least the reversal size the other way. Tops and bottoms alternate.
_Avoid_: peak, trough, swing high, swing low, pivot, zigzag point, reversal

**Top**:
A turning point at a high: the highest price before a fall of at least the reversal size.
_Avoid_: peak, swing high, resistance

**Bottom**:
A turning point at a low: the lowest price before a rise of at least the reversal size.
_Avoid_: trough, swing low, dip, support

**Confirmed**:
A turning point is confirmed by the first later candle that completes the reversal size; from that candle on it is known and counts as a level.
_Avoid_: detected, validated, locked in

**Reversal size**:
The percentage move against the prevailing direction that, in hindsight, makes the preceding extreme a turning point.
_Avoid_: threshold, deviation, sensitivity

**Detector**:
A set of explicit, readable rules that, at the close of each candle, decide whether to place a mark.
_Avoid_: model, classifier, signal generator, algorithm

**Mark**:
A detector's claim, made at the close of the latest candle, that this candle is at a top or a bottom. Marks are never placed on earlier candles.
_Avoid_: signal, label, prediction, point, dot

**Hit**:
A mark with a turning point of the same kind inside the tolerance.
_Avoid_: true positive, correct signal

**Miss**:
A turning point with no hit.
_Avoid_: false negative, missed signal

**False mark**:
A mark with no turning point of its kind inside the tolerance.
_Avoid_: false positive, fake-out

**Tolerance**:
How far a mark may be from a turning point, in candles and in percent of price, and still count as a hit.
_Avoid_: window, margin, slack

**Timing**:
The number of candles a hit is early or late relative to its turning point.
_Avoid_: lag, delay, lead

**Give-up**:
How far, as a percentage, a hit's close is from its turning point's extreme price.
_Avoid_: slippage, cost of confirmation

**Score**:
How a detector did over a period: hit rate, false-mark rate, median timing, median give-up and the raw counts.
_Avoid_: accuracy, performance, metrics

**Settled**:
A mark whose outcome, hit or false mark, no later candle can change. Until then the mark is pending.
_Avoid_: final, resolved, confirmed

**Floor**:
The reference detector every candidate must beat: it marks a top on the first candle that closes a fixed distance below the highest high since its last bottom mark, and the mirror image for a bottom. It is never a candidate itself.
_Avoid_: baseline, benchmark, naive detector

**Level**:
The price of a recent top or bottom, where the market may turn again. A level counts only until a set age; after that it is forgotten.
_Avoid_: support, resistance, key level, S/R

**Zone**:
The band around a level inside which a detector is allowed to place a mark.
_Avoid_: area, region, band

**Higher high**:
A candle whose high is above the previous candle's high.
_Avoid_: HH, up bar, swing high

**Lower low**:
A candle whose low is below the previous candle's low.
_Avoid_: LL, down bar, swing low

**Run**:
Consecutive higher highs, or consecutive lower lows, ending at a given candle. An equal high or low ends the run; a later candle whose high falls short of the previous high, or whose low stays above the previous low, fails it.
_Avoid_: streak, impulse, leg

**Detector one**:
The first candidate detector: a mark inside a zone on the candle that fails a run of at least three higher highs (a top) or lower lows (a bottom).
_Avoid_: the detector, v1, the levels detector

**Detector two**:
The second iteration of detector one's family: detector one's rule with levels that expire.
_Avoid_: v2, the expiring detector, one with expiry

**Replay**:
Feeding stored candles to a detector one at a time in time order, so that at every step nothing later is visible.
_Avoid_: simulation, playback, loop, backtest

## Trading

**Strategy**:
A set of explicit, readable rules that turn marks and market data into a desired position.
_Avoid_: model, algorithm, signal generator

**Trade**:
One round trip: opening a position and closing it again, with the resulting profit or loss.
_Avoid_: order, fill

**Stop**:
The price at which an open position is closed to cap the loss of that trade.
_Avoid_: stop-loss, SL, halt

**Account**:
The money the bot is allowed to trade with, held at the exchange and measured in one currency.
_Avoid_: wallet, balance, capital, portfolio

**Risk per trade**:
The largest loss a single trade is planned to take if its stop is hit, expressed as a percentage of the account.
_Avoid_: max loss, fixed euro/dollar amount per trade

**Drawdown halt**:
The bot stops trading and alerts the operator when the account has fallen a set percentage below its peak. Only a human restarts it.
_Avoid_: kill switch, circuit breaker, stop

## Validation

**Backtest**:
A run of a strategy over past market data to see how it would have traded.
_Avoid_: simulation, replay

**Success criterion**:
The pass/fail rule a detector or strategy must meet, written down before its replay or backtest runs.
_Avoid_: gate, target, hypothesis

**Family**:
The detectors that test one hypothesis, each a new iteration of the last. A family gets one out-of-sample check in all, and is dropped when it fails it.
_Avoid_: lineage, version line, series

**Iteration**:
One pre-registered rule of a family, written down with its success criterion before its single development run. A fail leads to the next iteration, never to an adjusted rerun.
_Avoid_: version, attempt, tweak, v2

**Out-of-sample check**:
A replay or backtest over a period that was never looked at while designing or tuning the detector or strategy.
_Avoid_: holdout, validation, test set

**Out-of-sample boundary**:
The fixed moment that ends the development period; candles from it on are reserved for out-of-sample checks.
_Avoid_: cutoff, split date, holdout start

**Development period**:
The stored history before the out-of-sample boundary: the only candles a detector, a replay or a chart may read while a detector is being designed.
_Avoid_: training set, in-sample, backtest period

**Paper trading**:
Running the bot against live market data with simulated orders and a simulated account.
_Avoid_: demo, dry run, simulation

**Go-live gate**:
The conditions paper trading must meet before the bot is allowed to trade real money.
_Avoid_: promotion, graduation
