"""Run a strategy backtest and report the honest numbers.

Prints Sharpe, max drawdown, final equity, and trade statistics; writes the
equity curve to data/processed/equity/{symbol}/{timeframe}_{strategy}.parquet.

Usage:
    uv run python scripts/backtest.py
    uv run python scripts/backtest.py --strategy buy_and_hold
    uv run python scripts/backtest.py --strategy ma_cross --fast 20 --slow 50
"""

import argparse
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import cast, get_args

from tradingbot.application.run_backtest import (
    BacktestReport,
    run_buy_and_hold,
    run_ma_cross,
    run_ma_cross_trend,
)
from tradingbot.core.ports.market_data import Timeframe

BACKEND_DIR = Path(__file__).parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data" / "raw" / "ohlcv"
DEFAULT_OUT_DIR = BACKEND_DIR / "data" / "processed" / "equity"


class _Args(argparse.Namespace):
    strategy: str
    fast: int
    slow: int
    symbol: str
    timeframe: str
    capital: Decimal
    data_dir: Path
    out_dir: Path


def print_trade_stats(report: BacktestReport) -> None:
    trades = report.result.trades
    if not trades:
        print("  Trades          :            0")
        return
    wins = [t for t in trades if t.pnl > 0]
    gross_profit = sum((t.pnl for t in wins), start=Decimal(0))
    gross_loss = -sum((t.pnl for t in trades if t.pnl <= 0), start=Decimal(0))
    print(f"  Trades          : {len(trades):>12}")
    print(f"  Win rate        : {len(wins) / len(trades):>12.1%}")
    if gross_loss > 0:
        print(f"  Profit factor   : {gross_profit / gross_loss:>12.2f}")
    reasons = Counter(t.reason.value for t in trades)
    print(f"  Exit reasons    : {dict(reasons)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strategy",
        default="ma_cross",
        choices=["ma_cross", "ma_cross_trend", "buy_and_hold"],
    )
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=50)
    parser.add_argument("--symbol", default="PF_XBTUSD")
    parser.add_argument("--timeframe", default="1h", choices=get_args(Timeframe.__value__))
    parser.add_argument("--capital", type=Decimal, default=Decimal(10000))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(namespace=_Args())

    timeframe = cast(Timeframe, args.timeframe)  # narrowed by argparse choices
    if args.strategy == "ma_cross":
        report = run_ma_cross(
            args.data_dir, args.symbol, timeframe, args.capital, fast=args.fast, slow=args.slow
        )
    elif args.strategy == "ma_cross_trend":
        report = run_ma_cross_trend(
            args.data_dir, args.symbol, timeframe, args.capital, fast=args.fast, slow=args.slow
        )
    else:
        report = run_buy_and_hold(args.data_dir, args.symbol, timeframe, args.capital)

    curve = report.result.equity_curve
    out_path = args.out_dir / args.symbol / f"{timeframe}_{args.strategy}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    curve.write_parquet(out_path)

    start, end = curve[0, "timestamp"], curve[-1, "timestamp"]
    print(f"{args.strategy} {args.symbol} {timeframe}: {report.num_bars} bars, {start} -> {end}")
    print(f"  Initial capital : {report.result.initial_capital:>12.2f}")
    print(f"  Final equity    : {report.result.final_equity:>12.2f}")
    print(f"  Sharpe (ann.)   : {report.sharpe:>12.2f}")
    print(f"  Max drawdown    : {report.max_drawdown:>12.2%}")
    print_trade_stats(report)
    print(f"Equity curve written to {out_path}")


if __name__ == "__main__":
    main()
