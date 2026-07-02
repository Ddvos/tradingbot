"""Run the buy-and-hold backtest and report the honest number (Slice 0).

Prints Sharpe, max drawdown, and final equity; writes the equity curve to
data/processed/equity/{symbol}/{timeframe}_buy_and_hold.parquet.

Usage:
    uv run python scripts/backtest.py
    uv run python scripts/backtest.py --capital 10000
"""

import argparse
from decimal import Decimal
from pathlib import Path
from typing import cast, get_args

from tradingbot.application.run_backtest import run_buy_and_hold
from tradingbot.core.ports.market_data import Timeframe

BACKEND_DIR = Path(__file__).parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data" / "raw" / "ohlcv"
DEFAULT_OUT_DIR = BACKEND_DIR / "data" / "processed" / "equity"


class _Args(argparse.Namespace):
    symbol: str
    timeframe: str
    capital: Decimal
    data_dir: Path
    out_dir: Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="PF_XBTUSD")
    parser.add_argument("--timeframe", default="1h", choices=get_args(Timeframe.__value__))
    parser.add_argument("--capital", type=Decimal, default=Decimal(10000))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(namespace=_Args())

    timeframe = cast(Timeframe, args.timeframe)  # narrowed by argparse choices
    report = run_buy_and_hold(args.data_dir, args.symbol, timeframe, args.capital)

    curve = report.result.equity_curve
    out_path = args.out_dir / args.symbol / f"{timeframe}_buy_and_hold.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    curve.write_parquet(out_path)

    start, end = curve[0, "timestamp"], curve[-1, "timestamp"]
    print(f"Buy-and-hold {args.symbol} {timeframe}: {report.num_bars} bars, {start} -> {end}")
    print(f"  Initial capital : {report.result.initial_capital:>12.2f}")
    print(f"  Final equity    : {report.result.final_equity:>12.2f}")
    print(f"  Sharpe (ann.)   : {report.sharpe:>12.2f}")
    print(f"  Max drawdown    : {report.max_drawdown:>12.2%}")
    print(f"Equity curve written to {out_path}")


if __name__ == "__main__":
    main()
