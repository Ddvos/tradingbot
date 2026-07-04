"""Run the purged walk-forward evaluation and write the report artifact.

The honest verdict on a model: per-fold retraining, out-of-sample test
windows only, pessimistic costs, deflated Sharpe against the trial
registry. Writes three files per run under
data/processed/walkforward/{symbol}/{timeframe}_{name}_{stamp}/:
folds.parquet, equity.parquet, report.md. Only development data is used —
the holdout (see HOLDOUT.md) stays untouched.

Usage:
    uv run python scripts/walkforward.py
    uv run python scripts/walkforward.py --name xgb_v1 --threshold 0.6
    uv run python scripts/walkforward.py --train-bars 17520 --test-bars 2160
"""

import argparse
import math
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast, get_args

import polars as pl

from tradingbot.application.run_walkforward import WalkForwardReport, run_walk_forward
from tradingbot.core.models.walk_forward import WalkForwardConfig
from tradingbot.core.ports.market_data import Timeframe

BACKEND_DIR = Path(__file__).parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data" / "raw" / "ohlcv"
DEFAULT_OUT_DIR = BACKEND_DIR / "data" / "processed" / "walkforward"


class _Args(argparse.Namespace):
    symbol: str
    timeframe: str
    name: str
    capital: Decimal
    threshold: float
    train_bars: int
    test_bars: int
    purge_bars: int
    embargo_bars: int
    min_test_bars: int
    data_dir: Path
    out_dir: Path


def _fmt(value: float, precision: int = 2) -> str:
    if math.isnan(value):
        return "n/a"
    if math.isinf(value):
        return "inf"
    return f"{value:.{precision}f}"


def folds_frame(report: WalkForwardReport) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "fold": [f.fold.index for f in report.folds],
            "test_start": [f.test_start for f in report.folds],
            "test_end": [f.test_end for f in report.folds],
            "n_test": [f.fold.test_end - f.fold.test_start for f in report.folds],
            "auc": [f.auc for f in report.folds],
            "ic": [f.ic for f in report.folds],
            "sharpe": [f.sharpe for f in report.folds],
            "max_drawdown": [f.max_drawdown for f in report.folds],
            "n_trades": [f.n_trades for f in report.folds],
            "win_rate": [f.win_rate for f in report.folds],
            "profit_factor": [f.profit_factor for f in report.folds],
        }
    )


def render_markdown(report: WalkForwardReport, run_stamp: str) -> str:
    c = report.config
    ci_low, ci_high = report.sharpe_ci
    lines = [
        f"# Walk-forward report — {report.symbol} {report.timeframe} ({run_stamp})",
        "",
        f"- Development data: {report.data_start:%Y-%m-%d} -> {report.data_end:%Y-%m-%d}"
        f" ({report.dataset_rows} dataset rows); holdout from"
        f" {report.holdout_start:%Y-%m-%d} untouched (see HOLDOUT.md)",
        f"- Splits: train {c.train_bars} bars, test {c.test_bars}, purge {c.purge_bars},"
        f" embargo {c.embargo_bars} -> {len(report.folds)} folds, model retrained per fold",
        f"- Strategy: long when P(target) >= {report.threshold}, v1 risk rules,"
        f" take-profit 2.0x ATR (aligned to the label)",
        "- Costs: 0.05% taker fee, 0.1% slippage, flat pessimistic funding",
        "",
        "## Out-of-sample result (all test windows stitched)",
        "",
        "| Metric | ML strategy | Buy-and-hold (same windows) |",
        "|---|---|---|",
        f"| Sharpe (ann.) | {_fmt(report.oos_sharpe)} | {_fmt(report.baseline_sharpe)} |",
        f"| Max drawdown | {report.oos_max_drawdown:.1%} | {report.baseline_max_drawdown:.1%} |",
        f"| Final equity ({report.initial_capital}) | {report.oos_final_equity:.0f}"
        f" | {report.baseline_final_equity:.0f} |",
        "",
        f"- Probabilistic Sharpe P(SR > 0): {_fmt(report.probabilistic_sharpe, 3)}",
        f"- **Deflated Sharpe** (vs {len(report.trial_sharpes_annualized)} trials):"
        f" {_fmt(report.deflated_sharpe, 3)}",
        f"- Bootstrap 95% CI for the annualized Sharpe:"
        f" [{_fmt(ci_low)}, {_fmt(ci_high)}] (block bootstrap, 24-bar blocks)",
        f"- Pooled IC: {_fmt(report.oos_ic, 4)} | pooled AUC: {_fmt(report.oos_auc, 3)}",
        f"- Trades: {report.n_trades} | win rate: {_fmt(report.win_rate, 3)}"
        f" | profit factor: {_fmt(report.profit_factor)}",
        "",
        "## Per fold",
        "",
        "| Fold | Test window | AUC | IC | Sharpe | Max DD | Trades | Win | PF |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {f.fold.index} | {f.test_start:%Y-%m-%d} -> {f.test_end:%Y-%m-%d}"
        f" | {_fmt(f.auc, 3)} | {_fmt(f.ic, 3)} | {_fmt(f.sharpe)}"
        f" | {f.max_drawdown:.1%} | {f.n_trades} | {_fmt(f.win_rate, 2)}"
        f" | {_fmt(f.profit_factor)} |"
        for f in report.folds
    )
    lines += [
        "",
        "## Trial registry (deflated-Sharpe input)",
        "",
    ]
    lines.extend(
        f"- {name}: annualized Sharpe {sharpe:.2f}"
        for name, sharpe in report.trial_sharpes_annualized.items()
    )
    lines += [
        "",
        "Every strategy candidate evaluated against the development data must be",
        "appended to `TRIAL_SHARPES_ANNUALIZED` in `application/run_walkforward.py`",
        "before its results are read — that registry is what keeps the deflated",
        "Sharpe honest.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="PF_XBTUSD")
    parser.add_argument("--timeframe", default="1h", choices=get_args(Timeframe.__value__))
    parser.add_argument("--name", default="xgb_v1")
    parser.add_argument("--capital", type=Decimal, default=Decimal(10000))
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--train-bars", type=int, default=WalkForwardConfig.train_bars)
    parser.add_argument("--test-bars", type=int, default=WalkForwardConfig.test_bars)
    parser.add_argument("--purge-bars", type=int, default=WalkForwardConfig.purge_bars)
    parser.add_argument("--embargo-bars", type=int, default=WalkForwardConfig.embargo_bars)
    parser.add_argument("--min-test-bars", type=int, default=WalkForwardConfig.min_test_bars)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(namespace=_Args())
    timeframe = cast(Timeframe, args.timeframe)  # narrowed by argparse choices

    config = WalkForwardConfig(
        train_bars=args.train_bars,
        test_bars=args.test_bars,
        purge_bars=args.purge_bars,
        embargo_bars=args.embargo_bars,
        min_test_bars=args.min_test_bars,
    )
    report = run_walk_forward(
        args.data_dir,
        args.symbol,
        timeframe,
        config=config,
        threshold=args.threshold,
        initial_capital=args.capital,
    )

    run_stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = args.out_dir / args.symbol / f"{timeframe}_{args.name}_{run_stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    folds_frame(report).write_parquet(run_dir / "folds.parquet")
    report.equity_curve.write_parquet(run_dir / "equity.parquet")
    markdown = render_markdown(report, run_stamp)
    (run_dir / "report.md").write_text(markdown)

    print(markdown)
    print(f"Report written to {run_dir}")


if __name__ == "__main__":
    main()
