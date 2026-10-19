---
status: accepted
date: 2026-10-18
---

# Trade the Kraken BTC perpetual long and short at 1x, not spot

The owner wants a real-money bot that earns when Bitcoin rises and when it falls. Spot Bitcoin can only be held or sold to cash, so it can sidestep a fall but never earn on one. We therefore trade one instrument, the Kraken Futures BTC perpetual, in both directions, and cap every position at the size of the account (1x) so that a long cannot be liquidated and a short is closed by its stop long before liquidation. The whole account runs in USD, the contract's own currency, converted once by hand, so the bot carries no currency conversion code.

## Considered options

- **Spot, long or cash only.** Simplest and no liquidation risk, but cannot earn on a decline, which the owner requires.
- **Spot core holding plus a futures short as an overlay.** Earns both ways but needs two balances on two venues kept in sync, and a hedge accounting layer. Rejected as the main source of complexity in the previous attempt at this project.
- **One perpetual, long and short, at 1x.** Chosen. One instrument, one currency, one balance.

## Consequences

- Funding is paid or received every hour while a position is open, so every backtest and the paper simulator must charge it.
- Buy-and-hold Bitcoin is the benchmark every strategy must beat, not something the bot does.
- A 1x short can still be liquidated if Bitcoin roughly doubles while the stop fails to fire. The stop and the drawdown halt, not the 1x cap, are the protection.
