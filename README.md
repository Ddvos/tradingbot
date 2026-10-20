# TradingBot

A bot that finds Bitcoin's turning points on a chart and, once it does that well, trades them with real money on Kraken. The vocabulary is in `GLOSSARY.md`; the decisions are in `docs/adr/`.

Slice 1 put the hourly history of Kraken spot `XBTUSD` in one SQLite file, resampled to 4-hour and daily candles, served by a small API and shown as candlesticks in a dashboard. Slice 2 added the harness that judges a detector before any detector exists: the true tops and bottoms of the history in hindsight, a replay that hands candles to a detector one hour at a time, the floor detector kept for reference, and the score. Slice 3 added detector one, the first candidate, pre-registered in issue #12 and judged by that harness, and the one explicit command that reads past the out-of-sample boundary. Slice 4 added detector two, the second iteration of the same family, pre-registered in issue #16: detector one's rule with levels that expire after 30 days, and the levels drawn on the replay chart. Family one closed on #16. Slice 5 changes the harness by ADR-0004 to ADR-0006 before family two runs: fifteen-minute candles next to the hourly ones, a replay that hands a detector fifteen-minute candles while the turning points stay hourly, tolerance B, a scoring period from 2016 split in three eras, three impossible prints dropped, and the three recorded runs re-scored under the new definitions (issue #19). No new detector and no trading yet.

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
| `TRADINGBOT_DB`  | `data/candles.sqlite`    | SQLite file that holds the candles        |
| `PUBLIC_API_URL` | `http://localhost:8000`  | Where the dashboard reads candles from    |

## Get the archive

Kraken publishes its whole spot history as downloadable OHLCVT files (open, high, low, close, volume, trades). The support article [Downloadable historical OHLCVT data](https://support.kraken.com/hc/en-us/articles/360047124832-Downloadable-historical-OHLCVT-Open-High-Low-Close-Volume-Trades-data) has the links. As of October 2026 the full archive comes in parts named `Kraken_OHLCVT_Full.zip.part00` to `part04` under `https://assets.kraken.com/marketing/institutions/`, plus one standalone zip per later quarter (`Kraken_OHLCVT_2026Q3.zip` and so on).

```sh
cat Kraken_OHLCVT_Full.zip.part0* > Kraken_OHLCVT_Full.zip
unzip -d data/full-archive Kraken_OHLCVT_Full.zip XBTUSD_60.csv XBTUSD_15.csv
```

The files you need are `XBTUSD_60.csv` (one row per hour) and `XBTUSD_15.csv` (one row per fifteen minutes): no header, columns `timestamp,open,high,low,close,volume,trades`, timestamps in Unix seconds UTC. Periods with no trades (common in the early years) simply have no row. The `data/` folder and any `XBTUSD_*.csv` are ignored by git, so the archive never ends up in a commit.

## Import the archive

```sh
uv run tradingbot import data/full-archive/XBTUSD_60.csv
uv run tradingbot import --timeframe 15m data/full-archive/XBTUSD_15.csv
```

Prints the number of new candles and the stored date range. Re-running it stores nothing new. Pass several files at once (for example the full archive and a quarterly update) to import them in one go. Hourly candles go to the table `candles_1h`, fifteen-minute candles to `candles_15m`, both in the same file; 4-hour and daily candles are never stored. Three impossible hourly prints of November 2013 are skipped at import, and so is every fifteen-minute candle inside those hours (see slice 5 below).

## Catch up from the REST endpoint

```sh
uv run tradingbot catch-up
uv run tradingbot catch-up --timeframe 15m
```

Fetches the newest candles of the timeframe from Kraken's public OHLC endpoint and appends the ones newer than the store's newest one. The candle that is still forming is never stored, so you can run it at any moment; running it again stores zero new rows except any newly completed candle. The endpoint reaches back only 720 candles: 30 days of hourly candles, 7.5 days of fifteen-minute ones. If the store's newest candle is older than that, the command warns which candles it could not reach: import the quarterly archive that covers them.

## Start the API

```sh
uv run tradingbot serve
```

Serves `GET http://localhost:8000/candles?timeframe=15m|1h|4h|1d&from=...&to=...`. Fifteen-minute and hourly candles come from their own tables; 4-hour and daily candles are resampled from the hourly ones. `from` and `to` are optional, as Unix seconds or ISO 8601 (`2024-01-01T00:00:00Z`), and are widened to whole periods, so a resampled candle is always built from every hour it covers. 4-hour candles start at 00:00, 04:00, ... UTC; daily candles at 00:00 UTC. Interactive docs are at `http://localhost:8000/docs`.

Two more routes serve the harness over the development period: `GET /turning-points?timeframe=15m|1h|4h|1d` answers the turning points, always found on the hourly candles (on 15m they sit on the fifteen-minute candle that holds the extreme, on 4h and 1d on the candle that holds the hour), and `GET /replay?detector=floor` replays the candles of the detector's timeframe through it and answers every candle it read, the turning points, the levels the detector read with their active spans, every mark with its outcome where the scoring period scored it, and the score over the scoring period, for the period and per era. All three routes stop at the out-of-sample boundary (see below).

## Start the dashboard

```sh
cd dashboard && npm run dev -- --open
```

One page, two modes. It reads from the API, so start that first.

**Hindsight** shows the whole development period as candlesticks with a 15m / 1h / 4h / 1d switch and the true turning points drawn as blue dots on their extremes.

**Replay** hands the candles of the detector's timeframe to the chosen detector (`floor`, `one` or `two`, all hourly) one at a time, from the first stored candle on. Press *Play* to watch candles appear at the chosen speed, *Pause* to stop, *Step* to advance one candle, *Restart* to begin again from nothing. There is no way to step backwards. A mark appears on the candle it was placed on, as a grey arrow (down for a top, up for a bottom) while its outcome is still open, and turns green (hit, with its timing in hourly candles) or red (false mark) as soon as no later candle can change it; a mark before the scoring period stays light grey, unscored: two tolerances after the mark and once the earliest candle that can still become a turning point lies beyond the mark's tolerance. Turning points appear as they are confirmed. The levels the detector sees at the latest candle are drawn as orange lines, each from the candle that confirmed its turning point up to the latest candle, and a line disappears when its level expires; the floor reads no levels, so it draws none. The lines under the controls are the detector's score over the scoring period and per era, the same numbers the batch command prints.

## Replay from the command line

```sh
uv run tradingbot replay floor
```

Replays the whole development period through the named detector, so it carries its state into the scoring period, scores the marks from 2016 on (for the period and per era) and writes the chart data (the same JSON the API answers for `/replay`) to `replay-<detector>.json` next to the store, or to `--out`. The chart data records the whole run, every candle the detector read and every mark it placed, with the marks before the scoring period unscored, so the run can be re-scored later (ADR-0004). The score is identical run to run. A recorded run is never replaced: the command refuses to overwrite an existing chart-data file, so pass `--out` for a fresh run. Three detectors exist, all on hourly candles: `floor`, the reference, `one`, the first candidate, and `two`, its second iteration. This is the floor's reference score, re-scored under the slice 5 definitions from the run recorded on issue #11 (the re-scored numbers are appended there too):

```
Re-scored floor under ADR-0005: 4463 marks, identical in number and time to the recorded run in data/replay-floor.json.
Replayed floor over 85857 candles from 2013-10-06T21:00:00Z to 2024-10-18T23:00:00Z, scored over the scoring period: 76881 candles from 2016-01-01T04:00:00Z to 2024-10-18T23:00:00Z.
  turning points   798
  marks            3180
  hits             259  (hit rate 32.5%)
  false marks      2921  (false-mark rate 91.9%)
  median timing    +0.0 candles (on time)
  median give-up   3.80%
  2016-2018        360 turning points, 1331 marks, 140 hits (hit rate 38.9%), 1191 false marks (false-mark rate 89.5%), median timing +0.0 candles (on time), median give-up 3.59%
  2019-2021        315 turning points, 1212 marks, 101 hits (hit rate 32.1%), 1111 false marks (false-mark rate 91.7%), median timing +0.0 candles (on time), median give-up 4.09%
  2022-2024        123 turning points, 637 marks, 18 hits (hit rate 14.6%), 619 false marks (false-mark rate 97.2%), median timing +0.0 candles (on time), median give-up 3.43%
```

The floor sets no bar (ADR-0005): the bars are absolute. Detector one's and detector two's scores are not in this file on purpose: issues #12 and #16 pre-register their success criteria, and each one's single development run, its verdict and its re-scoring are recorded as comments there.

## Re-score a recorded run

```sh
uv run tradingbot re-score floor
```

ADR-0004 rules that a recorded run is re-scored, never re-run, when the harness changes. The command reads the recorded run's chart data (`replay-<detector>.json` next to the store, or `--recorded`), replays its own candles through the detector, never past the out-of-sample boundary, and refuses to report unless the marks are identical in number and time to the recorded ones. It then prints the score under the current definitions, for the scoring period and per era, in the same shape as `replay`. The three family-one files hold every candle their runs read, three dropped prints included, which is why the marks come out identical although the store no longer holds those prints; detector one's 2017 marks in the zones of the two spurious levels those prints made (3,484 and 4,000) stay in its recorded run and are scored with it.

## Check the hourly candles built from the fifteen-minute ones

```sh
uv run tradingbot check-hourly
```

A fifteen-minute replay finds its turning points on hourly candles it builds from the fifteen-minute stream (ADR-0006). This command builds them the same way from the stored fifteen-minute candles and compares them with the stored hourly table over the scoring period: hours only in one table, hours whose candles differ, and turning points found on one series and not the other. On the full archive, imported on 20 October 2026, every count is zero: 76,881 hours and 798 turning points on both sides.

## Definitions fixed in slice 2

These were fixed in issue #11 before any detector was built. Changing any of them is a new decision, recorded in an ADR before any run (ADR-0004); slice 5 changed the tolerance, added the scoring period and the eras, and made the floor a reference that sets no bar. The numbers live as constants in the modules named below.

| Definition | Value | Where |
| --- | --- | --- |
| Turning point | hindsight, on hourly candles, reversal size 8%; the extreme is the candle high for a top and the candle low for a bottom, the reversal is measured to a later candle's low or high; tops and bottoms alternate | `turning_points.py` |
| Mark | placed only on the latest candle, at its close | `detectors.py` |
| Tolerance | a mark is a hit when a turning point of its kind lies within 24 candles before or after it and the mark's close is within 2% of the extreme; one hit per turning point, the nearest mark in candles; the rest are false marks | `scoring.py` |
| Score | hit rate, false-mark rate, median timing in candles (negative early, positive late), median give-up in percent, plus the raw counts | `scoring.py` |
| Floor detector | top on the first close 3% below the highest high since the last bottom mark, bottom on the first close 3% above the lowest low since the last top mark | `detectors.py` |
| Out-of-sample boundary | `2024-10-19T00:00:00Z` | `development.py` |

Distances in candles count candles of the hourly series, so a missing hour neither widens nor narrows a tolerance.

## Definitions fixed in slice 5

Decided on 20 October 2026 and recorded in ADR-0004, ADR-0005 and ADR-0006 before any detector of family two runs (issue #19). The harness changes only this way: by an ADR written before any run, justified by hindsight facts about candles and turning points alone, and every recorded run is re-scored under the new definitions.

| Definition | Value | Where |
| --- | --- | --- |
| Timeframe `15m` | fifteen-minute candles, stored next to the hourly ones in `candles_15m`; 4h and 1d stay resampled from hourly | `candles.py`, `store.py` |
| Tolerance B | a hit lies within 24 hourly candles of a turning point of its kind, and its close is within 2% of the extreme or no further than the extreme hourly candle's own close (ADR-0005) | `scoring.py` |
| Scoring period | from `2016-01-01T00:00:00Z` (Unix 1451606400) to the boundary; replays still start at the first stored candle | `scoring.py` |
| Eras | 2016 to 2018, 2019 to 2021, 2022 to 2024; every score is printed for the period and per era | `scoring.py` |
| Bars | hit rate at least 80% in every era; false marks at most equal to hits; no give-up bar | issue #20 |
| Dropped prints | the hourly candles at Unix 1383807600, 1384056000 and 1384236000 (2013-11-07 07:00, 2013-11-10 04:00, 2013-11-12 06:00 UTC) and every 15-minute candle inside those hours; skipped at import, deleted once from the existing store | `sync.py` |
| A 15-minute mark | placed at the 15-minute close; scored by the hour it falls in; timing in hourly candles; give-up from the 15-minute close; at most one mark per 15-minute candle | `scoring.py`, `replay.py` |
| Hourly candles in a 15-minute replay | built from the 15-minute stream when the hour completes (the candle ending at the hour, the first candle of a later hour, or the last candle of the series), fed to the turning-point finder, and compared with the stored hourly table over the scoring period | `replay.py`, `hourly_check.py` |

A turning point confirmed by the hour a fifteen-minute candle completes is visible to the detector on that candle. Two readings fixed in code rather than in the ADRs: a hit belongs to the era of its turning point, a false mark to the era of its mark; and the scoring period is scored as a series of its own, as the out-of-sample check is, so a January 2016 mark whose turning point lies in late December 2015 is a false mark.

## Definitions fixed in slice 3

Fixed in issue #12 before detector one's first run, with the same rule: changing one is a new decision.

| Definition | Value | Where |
| --- | --- | --- |
| Level | the price of every turning point confirmed so far, usable for tops and for bottoms alike, never expiring | `detectors.py` |
| Zone | within 1% of a level, measured on the latest candle's high for a top and its low for a bottom | `detectors.py` |
| Run | at least 3 consecutive higher highs (or lower lows) ending at the previous candle; a higher high is a candle whose high is above the previous candle's high | `detectors.py` |
| Detector one | a top on a candle in a zone whose high stays below the previous candle's after a run of higher highs; a bottom is the mirror on the lows; no mark outside a zone. When one candle fails both runs, the longer run wins and equal runs give no mark, since a candle gets at most one mark | `detectors.py` |
| Out-of-sample check | the whole history replayed, so the detector keeps its levels across the boundary; only candles, marks and turning points from the boundary on are kept and scored among themselves; one run per detector, each run logged | `out_of_sample.py` |

## Definitions fixed in slice 4

Fixed in issue #16 before detector two's first run, same rule again. Issue #16 also records the hindsight facts about the development period that led to them.

| Definition | Value | Where |
| --- | --- | --- |
| Level lifetime | a level is seen from the candle that confirms its turning point until 30 days (30 × 24 hours of calendar time, not candles) after the start of the turning point's own candle, inclusive; nothing renews or consumes it | `detectors.py` |
| Detector two | detector one's rule, zone, run and tie rule unchanged, with those levels | `detectors.py` |
| Give-up criterion | median give-up at most 1.0%, an absolute bar, replacing "lower than the floor's": the floor's 0.32% is unreachable by construction, since even a mark at the close of the extreme candle is a median 1.70% from the extreme over the development period; the floor's hits are coincidences from neighbouring swings | issue #16 |
| Levels in the chart data | every replay answers the levels the detector read, each with the first and the last candle that sees it, so the dashboard draws what the detector used | `replay.py` |

## The out-of-sample boundary

Development data is every stored candle, fifteen-minute or hourly, that starts before the boundary. Every development entry point, the three API routes, the batch replay, the re-scoring and the hourly check, reads through one function that clamps the window to the boundary, so no command can read past it by accident. `import` and `catch-up` still store newer candles; they are kept for the out-of-sample check below. The local store must hold candles from before the boundary for any of this to show anything: the quarterly archives only reach back to 2026, so the development period comes from the full archive.

## The out-of-sample check

```sh
uv run tradingbot out-of-sample one
```

The one command that reads past the boundary. It replays the whole stored history of the detector's timeframe through the detector, so the detector carries every level it has by the boundary, and scores only the candles from the boundary on, as a series of their own and without eras. It prints the score in the same shape as `replay`, writes the chart data (the whole run, the marks before the boundary unscored) to `out-of-sample-<detector>.json` next to the store (or to `--out`), and appends one line to `out-of-sample.log` in the working directory: when it ran, the detector, the period and the score. Run it from the repository root, like every other command, so that file is committed with the code and every run is on record. A detector that is already in the log is refused: the protocol in issue #12 gives each detector one out-of-sample run, and the command runs only after a detector has passed its success criterion over the development period. The API and the dashboard never read past the boundary.

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
  candles.py         Candle, Timeframe and resampling: 15m to 1h, 1h to 4h and 1d
  store.py           the SQLite store, one table per stored timeframe (15m, 1h)
  kraken.py          the OHLCVT archive reader and the REST endpoint client
  sync.py            archive import (dropped prints skipped) and catch-up
  development.py     the out-of-sample boundary and the only way to read development candles
  turning_points.py  turning points in hindsight, found one hourly candle at a time
  detectors.py       the Detector interface, Mark, Level, the floor detector, detector one and two
  scoring.py         tolerance B, the scoring period, the eras, and the score
  replay.py          replay: candles to a detector one at a time, hours built from 15-minute candles, then the score
  re_score.py        a recorded run replayed on its own candles and scored under the current definitions
  hourly_check.py    the hourly candles built from 15-minute ones against the stored hourly table
  out_of_sample.py   the one explicit check past the boundary, logged per run
  api.py             the FastAPI app with GET /candles, /turning-points and /replay
  cli.py             the tradingbot command: import, catch-up, serve, replay, re-score, check-hourly, out-of-sample
tests/               pytest suite
dashboard/           SvelteKit app: hindsight view and replay
docs/adr/            architecture decision records
GLOSSARY.md          the project's vocabulary
```
