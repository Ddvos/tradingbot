# TradingBot

The vocabulary of a bot that trades Bitcoin with real money on one exchange, after paper trading has proven it out.

## Market

**Perpetual**:
The Kraken Futures Bitcoin contract the bot trades. It has no expiry and can be held long or short.
_Avoid_: perp, future, contract, spot

**Position**:
The bot's current exposure in the perpetual: long, short, or flat.
_Avoid_: holding, exposure

**Funding**:
The hourly payment exchanged between long and short holders of the perpetual; a cost or an income of holding a position.
_Avoid_: interest, carry

**Benchmark**:
Buying Bitcoin at the start of a period and holding it to the end. Every strategy is judged against it.
_Avoid_: baseline, control, buy-and-hold strategy

## Trading

**Strategy**:
A set of explicit, readable rules that turn market data into a desired position.
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
The pass/fail rule a strategy must meet, written down before its backtest runs.
_Avoid_: gate, target, hypothesis

**Out-of-sample check**:
A backtest over a period that was never looked at while designing or tuning the strategy.
_Avoid_: holdout, validation, test set

**Paper trading**:
Running the bot against live market data with simulated orders and a simulated account.
_Avoid_: demo, dry run, simulation

**Go-live gate**:
The conditions paper trading must meet before the bot is allowed to trade real money.
_Avoid_: promotion, graduation
