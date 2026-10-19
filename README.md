# TradingBot

A bot that finds Bitcoin's turning points on a chart and, once it does that well, trades them with real money on Kraken. The vocabulary is in `GLOSSARY.md`; the decisions are in `docs/adr/`.

Slice 1 put the hourly history of Kraken spot `XBTUSD` in one SQLite file, resampled to 4-hour and daily candles, served by a small API and shown as candlesticks in a dashboard. Slice 2 adds the harness that judges a detector before any detector exists: the true tops and bottoms of the history in hindsight, a replay that hands candles to a detector one hour at a time, the floor detector every candidate must beat, and the score. No trading yet.

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
unzip -d data Kraken_OHLCVT_Full.zip XBTUSD_60.csv
```

The file you need is `XBTUSD_60.csv`: one row per hour, no header, columns `timestamp,open,high,low,close,volume,trades`, timestamps in Unix seconds UTC. Hours with no trades (common in the early years) simply have no row. The `data/` folder and any `XBTUSD_*.csv` are ignored by git, so the archive never ends up in a commit.

## Import the archive

```sh
uv run tradingbot import data/XBTUSD_60.csv
```

Prints the number of new hours and the stored date range. Re-running it stores nothing new. Pass several files at once (for example the full archive and a quarterly update) to import them in one go.

## Catch up from the REST endpoint

```sh
uv run tradingbot catch-up
```

Fetches the newest hourly candles from Kraken's public OHLC endpoint and appends the ones newer than the store's newest hour. The hour that is still forming is never stored, so you can run it at any moment; running it again stores zero new rows except any newly completed hour. The endpoint reaches back only 720 hours (30 days). If the store's newest hour is older than that, the command warns which hours it could not reach: import the quarterly archive that covers them.

## Start the API

```sh
uv run tradingbot serve
```

Serves `GET http://localhost:8000/candles?timeframe=1h|4h|1d&from=...&to=...`. `from` and `to` are optional, as Unix seconds or ISO 8601 (`2024-01-01T00:00:00Z`), and are widened to whole periods, so 4-hour and daily candles are always built from every hour they cover. 4-hour candles start at 00:00, 04:00, ... UTC; daily candles at 00:00 UTC. Interactive docs are at `http://localhost:8000/docs`.

Two more routes serve the harness: `GET /turning-points?timeframe=1h|4h|1d` answers the turning points of the window (on 4h and 1d they sit on the candle that holds the hourly extreme), and `GET /replay?detector=floor` replays the hourly candles through a detector and answers the candles, the turning points, every mark with its outcome, and the score. All three routes stop at the out-of-sample boundary (see below).

## Start the dashboard

```sh
cd dashboard && npm run dev -- --open
```

One page, two modes. It reads from the API, so start that first.

**Hindsight** shows the whole development period as candlesticks with a 1h / 4h / 1d switch and the true turning points drawn as blue dots on their extremes.

**Replay** hands the hourly candles to a detector one at a time. Press *Play* to watch candles appear at the chosen speed, *Pause* to stop, *Step* to advance one candle, *Restart* to begin again from nothing. There is no way to step backwards. A mark appears on the candle it was placed on, as a grey arrow (down for a top, up for a bottom) while its outcome is still open, and turns green (hit, with its timing in candles) or red (false mark) as soon as no later candle can change it: two tolerances after the mark and once the earliest candle that can still become a turning point lies beyond the mark's window. Turning points appear as they are confirmed. The line under the controls is the detector's score over the whole development period, the same number the batch command prints.

## Replay from the command line

```sh
uv run tradingbot replay floor
```

Replays the development period through the named detector, prints its score and writes the chart data (the same JSON the API answers for `/replay`) to `replay-<detector>.json` next to the store, or to `--out`. The score is identical run to run. Only `floor` exists so far.

```
Replayed floor over the development period: 2654 candles from 2024-06-30T00:00:00Z to 2024-10-18T13:00:00Z.
  turning points   4
  marks            41
  hits             0  (hit rate 0.0%)
  false marks      41  (false-mark rate 100.0%)
  median timing    n/a (no hits)
  median give-up   n/a (no hits)
```

## Definitions fixed in slice 2

These were fixed in issue #11 before any detector was built. Changing any of them is a new decision, to be recorded before the next detector. The numbers live as constants in the modules named below.

| Definition | Value | Where |
| --- | --- | --- |
| Turning point | hindsight, on hourly candles, reversal size 8%; the extreme is the candle high for a top and the candle low for a bottom, the reversal is measured to a later candle's low or high; tops and bottoms alternate | `turning_points.py` |
| Mark | placed only on the latest candle, at its close | `detectors.py` |
| Tolerance | a mark is a hit when a turning point of its kind lies within 24 candles before or after it and the mark's close is within 2% of the extreme; one hit per turning point, the nearest mark in candles; the rest are false marks | `scoring.py` |
| Score | hit rate, false-mark rate, median timing in candles (negative early, positive late), median give-up in percent, plus the raw counts | `scoring.py` |
| Floor detector | top on the first close 3% below the highest high since the last bottom mark, bottom on the first close 3% above the lowest low since the last top mark | `detectors.py` |
| Out-of-sample boundary | `2024-10-19T00:00:00Z` | `development.py` |

Distances in candles count candles of the hourly series, so a missing hour neither widens nor narrows a tolerance.

## The out-of-sample boundary

Development data is every hourly candle before the boundary. Every development entry point, the three API routes and the batch replay, reads through one function that clamps the window to the boundary, so no command can read past it by accident. `import` and `catch-up` still store newer candles; they are kept for the out-of-sample check, which goes through a separate, explicit command that logs each use (slice 3). The local store must hold candles from before the boundary for any of this to show anything: the quarterly archives only reach back to 2026, so the development period comes from the full archive.

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
  candles.py         Candle, Timeframe and resampling of hourly candles to 4h and 1d
  store.py           the SQLite store of hourly candles
  kraken.py          the OHLCVT archive reader and the REST endpoint client
  sync.py            archive import and catch-up, the two ways the store is updated
  development.py     the out-of-sample boundary and the only way to read development candles
  turning_points.py  turning points in hindsight, found one candle at a time
  detectors.py       the Detector interface, Mark, and the floor detector
  scoring.py         hits, misses, false marks, timing, give-up and the score
  replay.py          replay: candles to a detector one at a time, then the score
  api.py             the FastAPI app with GET /candles, /turning-points and /replay
  cli.py             the tradingbot command: import, catch-up, serve, replay
tests/               pytest suite
dashboard/           SvelteKit app: hindsight view and replay
docs/adr/            architecture decision records
GLOSSARY.md          the project's vocabulary
```
