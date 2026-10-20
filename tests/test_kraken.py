"""Kraken spot data sources: the OHLCVT archive file and the REST OHLC endpoint."""

import json
from pathlib import Path

import httpx
import pytest

from tradingbot.candles import Candle, Timeframe
from tradingbot.kraken import KrakenSpot, read_archive

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z

ARCHIVE_CSV = (
    # timestamp,open,high,low,close,volume,trades; no header; 01:00 has no trades
    "1704067200,100.0,110.0,95.0,105.0,1.5,10\n"
    "1704074400,105.0,120.0,100.0,115.0,2.25,20\n"
    "1704078000,115.0,118.0,90.0,92.0,3.0,30\n"
)


def test_archive_rows_become_candles(tmp_path: Path) -> None:
    csv = tmp_path / "XBTUSD_60.csv"
    csv.write_text(ARCHIVE_CSV)

    assert list(read_archive(csv)) == [
        Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.5, 10),
        Candle(T0 + 2 * H, 105.0, 120.0, 100.0, 115.0, 2.25, 20),
        Candle(T0 + 3 * H, 115.0, 118.0, 90.0, 92.0, 3.0, 30),
    ]


OHLC_RESPONSE = {
    "error": [],
    "result": {
        "XXBTZUSD": [
            [
                1792400400,
                "82734.5",
                "82999.7",
                "82643.9",
                "82675.1",
                "82856.9",
                "51.99652256",
                4725,
            ],
            [1792404000, "82675.0", "82688.0", "82635.3", "82688.0", "82660.2", "4.18657929", 284],
        ],
        "last": 1792400400,
    },
}


def test_rest_endpoint_rows_become_candles() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=OHLC_RESPONSE)

    source = KrakenSpot(http=httpx.Client(transport=httpx.MockTransport(handler)))

    candles = source.candles(Timeframe.H1, since=1792400400)

    assert candles == [
        Candle(1792400400, 82734.5, 82999.7, 82643.9, 82675.1, 51.99652256, 4725),
        Candle(1792404000, 82675.0, 82688.0, 82635.3, 82688.0, 4.18657929, 284),
    ]
    assert seen[0].host == "api.kraken.com"
    assert seen[0].path == "/0/public/OHLC"
    assert dict(seen[0].params) == {"pair": "XBTUSD", "interval": "60", "since": "1792400400"}


def test_rest_endpoint_errors_are_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": ["EGeneral:Invalid arguments"], "result": {}})

    source = KrakenSpot(http=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(RuntimeError, match="EGeneral:Invalid arguments"):
        source.candles(Timeframe.H1, since=None)


def test_rest_endpoint_is_asked_for_everything_when_since_is_none() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=json.dumps(OHLC_RESPONSE))

    KrakenSpot(http=httpx.Client(transport=httpx.MockTransport(handler))).candles(
        Timeframe.H1, None
    )

    assert "since" not in seen[0].params


def test_fifteen_minute_candles_are_asked_for_with_interval_15() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=OHLC_RESPONSE)

    KrakenSpot(http=httpx.Client(transport=httpx.MockTransport(handler))).candles(
        Timeframe.M15, since=1792400400
    )

    assert dict(seen[0].params) == {"pair": "XBTUSD", "interval": "15", "since": "1792400400"}
