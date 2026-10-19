# TradingBot

A bot that finds Bitcoin's turning points on a chart and, once it does that well, trades them with real money on Kraken. The vocabulary is in `GLOSSARY.md`; the decisions are in `docs/adr/`.

This is slice 1: the full hourly history of Kraken spot `XBTUSD` in one SQLite file, resampled to 4-hour and daily candles, served by a small API and shown as candlesticks in a dashboard. No turning points or trading yet.

## Requirements

- [uv](https://docs.astral.sh/uv/) with Python 3.13 (uv installs it if missing)
- Node.js 22 with npm, for the dashboard

## Install

```sh
uv sync
cd dashboard && npm install && cd ..
```

Settings have defaults, so no `.env` is required. To override them, copy `.env.example` to `.env` (and `dashboard/.env.example` to `dashboard/.env`) and run the Python commands with `uv run --env-file .env ...`.

| Setting          | Default                  | Meaning                                  |
| ---------------- | ------------------------ | ---------------------------------------- |
| `TRADINGBOT_DB`  | `data/candles.sqlite`    | SQLite file that holds the hourly candles |
| `PUBLIC_API_URL` | `http://localhost:8000`  | Where the dashboard reads candles from    |

## Get the archive

Kraken publishes its whole spot history as downloadable OHLCVT files (open, high, low, close, volume, trades). The support article [Downloadable historical OHLCVT data](https://support.kraken.com/hc/en-us/articles/360047124832-Downloadable-historical-OHLCVT-Open-High-Low-Close-Volume-Trades-data) has the links. As of October 2026 the full archive comes in parts named `Kraken_OHLCVT_Full.zip.part00` to `part04` under `https://assets.kraken.com/marketing/institutions/`, plus one standalone zip per later quarter (`Kraken_OHLCVT_2026Q3.zip` and so on).

```sh
cat Kraken_OHLCVT_Full.zip.part0* > Kraken_OHLCVT_Full.zip
unzip Kraken_OHLCVT_Full.zip 'XBTUSD_60.csv'
```

The file you need is `XBTUSD_60.csv`: one row per hour, no header, columns `timestamp,open,high,low,close,volume,trades`, timestamps in Unix seconds UTC. Hours with no trades (common in the early years) simply have no row.

## Import the archive

```sh
uv run tradingbot import path/to/XBTUSD_60.csv
```

Prints the number of new hours and the stored date range. Re-running it stores nothing new. Pass several files at once (for example the full archive and a quarterly update) to import them in one go.

## Catch up from the REST endpoint

```sh
uv run tradingbot catch-up
```

Fetches the newest hourly candles from Kraken's public OHLC endpoint and appends the ones newer than the store's newest hour. The hour that is still forming is never stored, so you can run it at any moment; running it again stores zero new rows except any newly completed hour. The endpoint reaches back only 720 hours (30 days). If the store is older than that, the command warns which hours are missing: import the quarterly archive that covers them.

## Start the API

```sh
uv run tradingbot serve
```

Serves `GET http://localhost:8000/candles?timeframe=1h|4h|1d&from=...&to=...`. `from` and `to` are optional, as Unix seconds or ISO 8601 (`2024-01-01T00:00:00Z`), and are widened to whole periods, so 4-hour and daily candles are always built from every hour they cover. 4-hour candles start at 00:00, 04:00, ... UTC; daily candles at 00:00 UTC. Interactive docs are at `http://localhost:8000/docs`.

## Start the dashboard

```sh
cd dashboard && npm run dev -- --open
```

One page: a candlestick chart of the whole stored history with a 1h / 4h / 1d switch. It reads from the API, so start that first.

## Run the checks

```sh
uv run pytest
uv run ruff check
uv run ruff format --check
uv run pyright
cd dashboard && npm run check
```

## Layout

```
src/tradingbot/
  candles.py   Candle, Timeframe and resampling of hourly candles to 4h and 1d
  store.py     the SQLite store of hourly candles
  kraken.py    the OHLCVT archive reader, the REST endpoint client and catch-up
  api.py       the FastAPI app with GET /candles
  cli.py       the tradingbot command: import, catch-up, serve
tests/         pytest suite
dashboard/     SvelteKit app
docs/adr/      architecture decision records
GLOSSARY.md    the project's vocabulary
```
