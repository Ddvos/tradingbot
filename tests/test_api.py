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


def test_a_time_range_may_be_given_as_iso_8601_or_unix_seconds(client: TestClient) -> None:
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


def test_a_time_range_inside_a_period_still_yields_the_whole_period(client: TestClient) -> None:
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


OUT_OF_SAMPLE_BOUNDARY = 1_729_296_000  # 2024-10-19T00:00:00Z


def sixteen_hours() -> list[Candle]:
    """The hand-built series of test_turning_points: bottom 03:00, top 08:00, bottom 12:00."""
    rows = [
        (0, 96.0, 94.0, 95.0),
        (1, 95.0, 92.0, 93.0),
        (3, 93.0, 90.0, 91.0),
        (4, 94.0, 91.0, 93.0),
        (5, 96.0, 92.0, 95.0),
        (6, 98.0, 94.0, 97.0),
        (7, 99.0, 96.0, 98.0),
        (8, 100.0, 97.0, 99.0),
        (9, 99.0, 95.0, 96.0),
        (10, 97.0, 93.0, 94.0),
        (11, 95.0, 91.0, 92.0),
        (12, 93.0, 90.0, 91.0),
        (13, 95.0, 91.0, 94.0),
        (14, 98.0, 93.0, 97.0),
        (15, 101.0, 96.0, 100.0),
    ]
    return [Candle(DAY_START + h * H, c, hi, lo, c, 1.0, 1) for h, hi, lo, c in rows]


@pytest.fixture
def harness_client(tmp_path: Path) -> TestClient:
    db = tmp_path / "candles.sqlite"
    with CandleStore(db) as store:
        store.upsert(sixteen_hours())
    return TestClient(create_app(db))


def test_turning_points_are_served_on_the_hourly_candles(harness_client: TestClient) -> None:
    body = harness_client.get("/turning-points", params={"timeframe": "1h"}).json()

    assert body == {
        "timeframe": "1h",
        "turning_points": [
            {
                "kind": "bottom",
                "time": DAY_START + 3 * H,
                "price": 90.0,
                "confirmed_at": DAY_START + 6 * H,
            },
            {
                "kind": "top",
                "time": DAY_START + 8 * H,
                "price": 100.0,
                "confirmed_at": DAY_START + 11 * H,
            },
            {
                "kind": "bottom",
                "time": DAY_START + 12 * H,
                "price": 90.0,
                "confirmed_at": DAY_START + 14 * H,
            },
        ],
    }


def test_on_four_hour_candles_a_turning_point_sits_on_the_candle_holding_the_hour(
    harness_client: TestClient,
) -> None:
    body = harness_client.get("/turning-points", params={"timeframe": "4h"}).json()

    assert [(p["kind"], p["time"], p["price"]) for p in body["turning_points"]] == [
        ("bottom", DAY_START, 90.0),
        ("top", DAY_START + 8 * H, 100.0),
        ("bottom", DAY_START + 12 * H, 90.0),
    ]


def test_a_replay_answers_candles_turning_points_marks_and_score(
    harness_client: TestClient,
) -> None:
    body = harness_client.get("/replay", params={"detector": "floor"}).json()

    assert body["detector"] == "floor"
    assert len(body["candles"]) == 15
    assert [p["time"] for p in body["turning_points"]] == [
        DAY_START + 3 * H,
        DAY_START + 8 * H,
        DAY_START + 12 * H,
    ]
    # The floor marks a top at 01:00 (close 93 is 3.1% below the high of 96 at 00:00), a
    # bottom at 04:00, a top at 09:00 and a bottom at 13:00; none is within 2% of a
    # turning point, so all four are false marks and all three turning points are misses.
    assert [(m["kind"], m["time"], m["price"]) for m in body["marks"]] == [
        ("top", DAY_START + H, 93.0),
        ("bottom", DAY_START + 4 * H, 93.0),
        ("top", DAY_START + 9 * H, 96.0),
        ("bottom", DAY_START + 13 * H, 94.0),
    ]
    assert body["marks"][0] == {
        "kind": "top",
        "time": DAY_START + H,
        "price": 93.0,
        "hit": False,
        "turning_point": None,
        "timing": None,
        "give_up": None,
        "settled_at": DAY_START + 15 * H,
    }
    assert body["score"] == {
        "turning_points": 3,
        "marks": 4,
        "hits": 0,
        "false_marks": 4,
        "hit_rate": 0.0,
        "false_mark_rate": 1.0,
        "median_timing": None,
        "median_give_up": None,
    }


def test_an_unknown_detector_is_rejected(harness_client: TestClient) -> None:
    response = harness_client.get("/replay", params={"detector": "oracle"})

    assert response.status_code == 404
    assert "floor" in response.json()["detail"]


@pytest.fixture
def straddling_client(tmp_path: Path) -> TestClient:
    """Three flat hours before the boundary, then a crash and a recovery after it.

    Read past the boundary, the crash would make the last flat hour a top and the
    crash hour a bottom, and the floor would place marks. Read correctly, there is
    nothing but three flat candles.
    """
    db = tmp_path / "candles.sqlite"
    with CandleStore(db) as store:
        store.upsert(
            [
                Candle(OUT_OF_SAMPLE_BOUNDARY - 3 * H, 100.0, 100.0, 100.0, 100.0, 1.0, 1),
                Candle(OUT_OF_SAMPLE_BOUNDARY - 2 * H, 100.0, 100.0, 100.0, 100.0, 1.0, 1),
                Candle(OUT_OF_SAMPLE_BOUNDARY - H, 100.0, 100.0, 100.0, 100.0, 1.0, 1),
                Candle(OUT_OF_SAMPLE_BOUNDARY, 100.0, 100.0, 50.0, 60.0, 1.0, 1),
                Candle(OUT_OF_SAMPLE_BOUNDARY + H, 60.0, 110.0, 60.0, 100.0, 1.0, 1),
                Candle(OUT_OF_SAMPLE_BOUNDARY + 2 * H, 100.0, 100.0, 100.0, 100.0, 1.0, 1),
            ]
        )
    return TestClient(create_app(db))


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/candles", {"timeframe": "1h"}),
        ("/candles", {"timeframe": "1h", "to": OUT_OF_SAMPLE_BOUNDARY + 2 * H}),
        ("/candles", {"timeframe": "1d"}),
        ("/turning-points", {"timeframe": "1h"}),
        ("/replay", {"detector": "floor"}),
    ],
)
def test_no_route_reads_candles_past_the_boundary(
    straddling_client: TestClient, path: str, params: dict[str, str | int]
) -> None:
    body = straddling_client.get(path, params=params).json()

    assert all(c["time"] < OUT_OF_SAMPLE_BOUNDARY for c in body.get("candles", []))
    assert body.get("turning_points", []) == []
    assert body.get("marks", []) == []
    if path == "/candles" and params["timeframe"] == "1h":
        assert len(body["candles"]) == 3
