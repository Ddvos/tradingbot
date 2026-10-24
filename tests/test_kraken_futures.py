"""The public Kraken Futures endpoints: the perpetual's mark price and the funding history,
read from recorded answers of 24 October 2026."""

import httpx
import pytest

from tradingbot.kraken_futures import KrakenFutures, MarkPrice, parse_time

TICKER = {
    "result": "success",
    "serverTime": "2026-10-24T17:07:27.733Z",
    "ticker": {
        "symbol": "PF_XBTUSD",
        "last": 80129,
        "lastTime": "2026-10-24T17:07:22.300690135Z",
        "tag": "perpetual",
        "pair": "XBT:USD",
        "markPrice": 80127.44715696647,
        "bid": 80128,
        "ask": 80129,
        "fundingRate": 0.932235825433360037,
        "fundingRatePrediction": 1.0150405852575,
        "relativeFundingRate": 0.000011636666666667,
        "relativeFundingRatePrediction": 0.00001266775,
        "suspended": False,
        "indexPrice": 80121.43,
        "postOnly": False,
        "change24h": -1.88,
    },
}

FUNDING = {
    "result": "success",
    "serverTime": "2026-10-24T17:18:22.87Z",
    "rates": [
        {
            "timestamp": "2025-10-15T08:00:00Z",
            "fundingRate": 0.768276293491824937,
            "relativeFundingRate": 0.000006820506944444,
        },
        {
            "timestamp": "2025-10-15T09:00:00Z",
            "fundingRate": 0.917136157122824767,
            "relativeFundingRate": 0.000008114481944444,
        },
        # 10:00 was not published
        {
            "timestamp": "2025-10-15T11:00:00Z",
            "fundingRate": -1.034964364807413855,
            "relativeFundingRate": -0.000009212052777778,
        },
    ],
}


def client(answer: dict, seen: list[httpx.URL]) -> KrakenFutures:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=answer)

    return KrakenFutures(http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_the_ticker_answers_the_mark_price_and_the_servers_time() -> None:
    seen: list[httpx.URL] = []

    mark = client(TICKER, seen).mark_price()

    assert mark == MarkPrice(80127.44715696647, 1_792_861_647)
    assert seen[0].host == "futures.kraken.com"
    assert seen[0].path == "/derivatives/api/v3/tickers/PF_XBTUSD"


def test_the_funding_history_is_keyed_by_the_hours_start_with_the_relative_rate() -> None:
    seen: list[httpx.URL] = []

    rates = client(FUNDING, seen).funding_rates()

    assert rates == {
        1_760_515_200: 0.000006820506944444,
        1_760_518_800: 0.000008114481944444,
        1_760_526_000: -0.000009212052777778,
    }
    assert 1_760_522_400 not in rates, "an hour Kraken did not publish has no rate"
    assert seen[0].path == "/derivatives/api/v4/historicalfundingrates"
    assert dict(seen[0].params) == {"symbol": "PF_XBTUSD"}


def test_an_error_answer_is_raised() -> None:
    source = client({"result": "error", "error": "apiLimitExceeded"}, [])

    with pytest.raises(RuntimeError, match="apiLimitExceeded"):
        source.mark_price()


def test_a_failed_request_is_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    source = KrakenFutures(http=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(httpx.HTTPStatusError):
        source.funding_rates()


def test_the_apis_times_are_read_with_and_without_fractions() -> None:
    assert parse_time("2026-10-24T17:07:27.733Z") == 1_792_861_647
    assert parse_time("2025-10-15T08:00:00Z") == 1_760_515_200
