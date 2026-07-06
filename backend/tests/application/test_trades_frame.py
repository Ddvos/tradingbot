from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl

from tradingbot.application.run_backtest import TRADES_SCHEMA, trades_frame, trades_path_for
from tradingbot.core.backtest.engine import ExitReason, Trade
from tradingbot.core.ports.executor import Fill, OrderId, Side

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def fill(side: Side, price: str, hours: int) -> Fill:
    return Fill(
        order_id=OrderId("o1"),
        symbol="PF_XBTUSD",
        side=side,
        quantity=Decimal("0.5"),
        price=Decimal(price),
        fee=Decimal("2.5"),
        timestamp=_T0 + timedelta(hours=hours),
    )


def test_trades_frame_values() -> None:
    trade = Trade(
        entry_fill=fill(Side.BUY, "50000", 0),
        exit_fill=fill(Side.SELL, "51000", 4),
        reason=ExitReason.TAKE_PROFIT,
        pnl=Decimal("495.0"),
        stop=Decimal("49250"),
        take_profit=Decimal("51000"),
    )

    row = trades_frame([trade]).row(0, named=True)

    assert row["side"] == "long"
    assert row["entry_time"] == _T0
    assert row["exit_time"] == _T0 + timedelta(hours=4)
    assert row["entry_price"] == 50000.0
    assert row["stop_price"] == 49250.0
    assert row["take_profit_price"] == 51000.0
    assert row["fees"] == 5.0
    assert row["reason"] == "take_profit"


def test_trades_frame_empty_and_barrierless_trades_keep_the_schema() -> None:
    empty = trades_frame([])
    assert empty.height == 0
    assert empty.columns == list(TRADES_SCHEMA)

    barrierless = Trade(
        entry_fill=fill(Side.SELL, "50000", 0),
        exit_fill=fill(Side.BUY, "49000", 8),
        reason=ExitReason.SIGNAL,
        pnl=Decimal("495.0"),
    )
    row = trades_frame([barrierless]).row(0, named=True)
    assert row["side"] == "short"
    assert row["stop_price"] is None
    assert row["take_profit_price"] is None


def test_trades_path_sits_next_to_the_equity_curve() -> None:
    path = trades_path_for(Path("data/equity/PF_XBTUSD/1h_ma_cross.parquet"))
    assert path == Path("data/equity/PF_XBTUSD/1h_ma_cross_trades.parquet")


def test_trades_frame_roundtrips_through_parquet(tmp_path: Path) -> None:
    trade = Trade(
        entry_fill=fill(Side.BUY, "50000", 0),
        exit_fill=fill(Side.SELL, "51000", 4),
        reason=ExitReason.STOP_LOSS,
        pnl=Decimal("-100"),
    )
    target = tmp_path / "trades.parquet"
    trades_frame([trade]).write_parquet(target)

    assert pl.read_parquet(target).row(0, named=True)["reason"] == "stop_loss"
