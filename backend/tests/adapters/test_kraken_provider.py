import json
from datetime import UTC, datetime

import httpx

from tradingbot.adapters.kraken.provider import BASE_URL, KrakenProvider
from tradingbot.core.ports.market_data import OHLCV_SCHEMA, validate_ohlcv

HOUR_MS = 3_600_000
T0 = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp()) * 1000


def candle(time_ms: int, price: float) -> dict[str, int | str]:
    return {
        "time": time_ms,
        "open": str(price),
        "high": str(price + 1),
        "low": str(price - 1),
        "close": str(price),
        "volume": "12.5",
    }


def paginating_handler(requests_seen: list[httpx.Request]) -> httpx.MockTransport:
    """First call returns 2 candles with more_candles=True, second call the final one."""

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        start_ms = int(request.url.params["from"]) * 1000
        if start_ms <= T0:
            body = {
                "candles": [candle(T0, 100.0), candle(T0 + HOUR_MS, 101.0)],
                "more_candles": True,
            }
        else:
            body = {"candles": [candle(T0 + 2 * HOUR_MS, 102.0)], "more_candles": False}
        return httpx.Response(200, content=json.dumps(body))

    return httpx.MockTransport(handler)


def make_provider(requests_seen: list[httpx.Request]) -> KrakenProvider:
    client = httpx.Client(transport=paginating_handler(requests_seen), base_url=BASE_URL)
    return KrakenProvider(client=client)


def test_fetch_ohlcv_paginates_and_parses() -> None:
    requests_seen: list[httpx.Request] = []
    since = datetime(2024, 1, 1, tzinfo=UTC)

    df = make_provider(requests_seen).fetch_ohlcv("PF_XBTUSD", "1h", since)

    assert len(requests_seen) == 2
    assert df.schema == OHLCV_SCHEMA
    assert df.get_column("close").to_list() == [100.0, 101.0, 102.0]
    assert df.get_column("timestamp").to_list()[0] == since
    validate_ohlcv(df)


def test_second_page_starts_after_last_candle() -> None:
    requests_seen: list[httpx.Request] = []
    since = datetime(2024, 1, 1, tzinfo=UTC)

    make_provider(requests_seen).fetch_ohlcv("PF_XBTUSD", "1h", since)

    second_from = int(requests_seen[1].url.params["from"])
    assert second_from == (T0 + HOUR_MS) // 1000 + 3600
