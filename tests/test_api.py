"""GET /candles: hourly candles and their 4-hour and daily resamples as JSON."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradingbot.api import create_app
from tradingbot.candles import Candle
from tradingbot.store import CandleStore

H = 3600
DAY_START = 1_704_067_200  # 2024-01-01T00:00:00Z


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db = tmp_path / "candles.sqlite"
    with CandleStore(db) as store:
        store.upsert(
            [
                Candle(DAY_START, 100.0, 110.0, 95.0, 105.0, 1.0, 10),
                Candle(DAY_START + H, 105.0, 120.0, 100.0, 115.0, 2.0, 20),
                # 02:00 has no candle
                Candle(DAY_START + 3 * H, 115.0, 118.0, 90.0, 92.0, 3.0, 30),
                Candle(DAY_START + 4 * H, 92.0, 100.0, 91.0, 99.0, 4.0, 40),
                Candle(DAY_START + 5 * H, 99.0, 101.0, 98.0, 100.0, 5.0, 50),
            ]
        )
    return TestClient(create_app(db))


def test_hourly_candles_are_returned_as_json(client: TestClient) -> None:
    response = client.get("/candles", params={"timeframe": "1h"})

    assert response.status_code == 200
    body = response.json()
    assert body["timeframe"] == "1h"
    assert len(body["candles"]) == 5
    assert body["candles"][0] == {
        "time": DAY_START,
        "open": 100.0,
        "high": 110.0,
        "low": 95.0,
        "close": 105.0,
        "volume": 1.0,
        "trades": 10,
    }


def test_four_hour_candles_are_built_from_the_hourly_ones(client: TestClient) -> None:
    body = client.get("/candles", params={"timeframe": "4h"}).json()

    assert body["candles"] == [
        {
            "time": DAY_START,
            "open": 100.0,
            "high": 120.0,
            "low": 90.0,
            "close": 92.0,
            "volume": 6.0,
            "trades": 60,
        },
        {
            "time": DAY_START + 4 * H,
            "open": 92.0,
            "high": 101.0,
            "low": 91.0,
            "close": 100.0,
            "volume": 9.0,
            "trades": 90,
        },
    ]


def test_a_window_may_be_given_as_iso_8601_or_unix_seconds(client: TestClient) -> None:
    by_iso = client.get(
        "/candles",
        params={"timeframe": "1h", "from": "2024-01-01T01:00:00Z", "to": "2024-01-01T03:00:00Z"},
    ).json()
    by_seconds = client.get(
        "/candles",
        params={"timeframe": "1h", "from": DAY_START + H, "to": DAY_START + 3 * H},
    ).json()

    assert [c["time"] for c in by_iso["candles"]] == [DAY_START + H, DAY_START + 3 * H]
    assert by_seconds == by_iso


def test_a_window_inside_a_period_still_yields_the_whole_period(client: TestClient) -> None:
    body = client.get(
        "/candles",
        params={"timeframe": "4h", "from": "2024-01-01T01:00:00Z", "to": "2024-01-01T01:00:00Z"},
    ).json()

    assert body["candles"] == [
        {
            "time": DAY_START,
            "open": 100.0,
            "high": 120.0,
            "low": 90.0,
            "close": 92.0,
            "volume": 6.0,
            "trades": 60,
        }
    ]


def test_an_unknown_timeframe_is_rejected(client: TestClient) -> None:
    response = client.get("/candles", params={"timeframe": "15m"})

    assert response.status_code == 422


def test_an_unreadable_time_is_rejected(client: TestClient) -> None:
    response = client.get("/candles", params={"timeframe": "1h", "from": "yesterday"})

    assert response.status_code == 422
