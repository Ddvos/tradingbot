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

**Level**:
The price of an earlier top or bottom, where the market may turn again.
_Avoid_: support, resistance, key level, S/R

**Zone**:
The band around a level inside which a detector is allowed to place a mark.
_Avoid_: area, region, band

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

**Out-of-sample check**:
A replay or backtest over a period that was never looked at while designing or tuning the detector or strategy.
_Avoid_: holdout, validation, test set

**Paper trading**:
Running the bot against live market data with simulated orders and a simulated account.
_Avoid_: demo, dry run, simulation

**Go-live gate**:
The conditions paper trading must meet before the bot is allowed to trade real money.
_Avoid_: promotion, graduation
