# TradingBot

A bot that finds Bitcoin's turning points on a chart and, once it does that well, trades them with real money on Kraken. The vocabulary is in `GLOSSARY.md`; the decisions are in `docs/adr/`.

Slice 1 put the hourly history of Kraken spot `XBTUSD` in one SQLite file, resampled to 4-hour and daily candles, served by a small API and shown as candlesticks in a dashboard. Slice 2 added the harness that judges a detector before any detector exists: the true tops and bottoms of the history in hindsight, a replay that hands candles to a detector one hour at a time, the floor detector kept for reference, and the score. Slice 3 added detector one, the first candidate, pre-registered in issue #12 and judged by that harness, and the one explicit command that reads past the out-of-sample boundary. Slice 4 added detector two, the second iteration of the same family, pre-registered in issue #16: detector one's rule with levels that expire after 30 days, and the levels drawn on the replay chart. Family one closed on #16. Slice 5 changes the harness by ADR-0004 to ADR-0006 before family two runs: fifteen-minute candles next to the hourly ones, a replay that hands a detector fifteen-minute candles while the turning points stay hourly, tolerance B, a scoring period from 2016 split in three eras, three impossible prints dropped, and the three recorded runs re-scored under the new definitions (issue #19). Slice 6 adds detector three, the first iteration of family two, pre-registered in issue #20: on fifteen-minute candles, a mark on the first candle that stays short of the swing extreme once the swing has reached the reversal size, with the swing extreme drawn on the replay chart. Slice 7 changes the harness by ADR-0007 before family two's out-of-sample check: the false-mark bar is dropped, the score reports false marks per hit for the period and per era, and the four recorded runs are re-scored (issue #27). Slice 8 spends family two's one out-of-sample check on detector three, pre-registered in issue #28: the run's line is in `out-of-sample.log`, and its score and verdict are recorded on that issue. Slice 9 builds the strategy harness of ADR-0008 before any candidate strategy exists: a backtest that walks a strategy over detector three's recorded run with a notional account under two cost models, spot and the perpetual, the strategy score judged against buying and holding, and the flip, the reference strategy that acts on every mark, run once (issue #32). Slice 10 changes the harness by ADR-0009 before any detector of family three exists: a detector declares its family's reversal size and is scored against the turning points of that size, the out-of-sample boundary moves to 2025-01-01 so the third era is the whole of 2022 to 2024, the backtest runs a strategy on any detector's recorded run, and the out-of-sample check can walk the flip on a detector from the boundary and judge it by ADR-0009's bar (issue #38). Slice 11 adds paper trading (issue #39): a loop on live fifteen-minute candles from Kraken's spot endpoint that runs detector three and the flip, the reference and never a candidate, with a simulated account under the perpetual cost model, records Kraken Futures' mark price and real funding next to the model's numbers, survives a restart, and reconciles its fills with a backtest over the same candles. No order is placed and no key is needed.

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

Two more routes serve the harness over the development period: `GET /turning-points?timeframe=15m|1h|4h|1d` answers the turning points, always found on the hourly candles (on 15m they sit on the fifteen-minute candle that holds the extreme, on 4h and 1d on the candle that holds the hour), at a reversal size of 8% unless `&reversal=0.16` (a fraction strictly between 0 and 1) asks for another, and the answer names the size it used; and `GET /replay?detector=floor` replays the candles of the detector's timeframe through it and answers the reversal size of the detector's family, every candle it read, the turning points at that size, the levels and the swing extremes the detector read with their active spans, every mark with its outcome where the scoring period scored it, and the score over the scoring period, for the period and per era. With `&strategy=flip` it also walks that strategy over the replay and answers, under `backtest`, its fills and its score under both cost models (see "Backtest a strategy" below); without a strategy the answer is unchanged. All three routes stop at the out-of-sample boundary (see below).

## Start the dashboard

```sh
cd dashboard && npm run dev -- --open
```

One page, two modes. It reads from the API, so start that first.

**Hindsight** shows the whole development period as candlesticks with a 15m / 1h / 4h / 1d switch and the true turning points drawn as blue dots on their extremes.

**Replay** hands the candles of the detector's timeframe to the chosen detector (`floor`, `one` and `two` on hourly candles, `three` on fifteen-minute ones) one at a time, from the first stored candle on. Press *Play* to watch candles appear at the chosen speed, *Pause* to stop, *Step* to advance one candle, *Restart* to begin again from the start date, or from nothing without one. There is no way to step backwards. A mark appears on the candle it was placed on, as a grey arrow (down for a top, up for a bottom) while its outcome is still open, and turns green (hit, with its timing in hourly candles) or red (false mark) as soon as no later candle can change it; a mark before the scoring period stays light grey, unscored: two tolerances after the mark and once the earliest candle that can still become a turning point lies beyond the mark's tolerance. Turning points appear as they are confirmed. The levels the detector sees at the latest candle are drawn as orange lines, each from the candle that confirmed its turning point up to the latest candle, and a line disappears when its level expires; the floor reads no levels, so it draws none. Detector three reads no levels but a swing extreme per side, drawn as a purple line from the candle the detector first read it on up to the latest candle, for as long as it stands; the line moves when a new extreme replaces it, and a mark goes on the first candle that stays short of the line once the swing is the detector's reversal size. One line under the controls sums up the detector's score, with the reversal size of its family next to its name (turning points found at that size, false marks per hit, median give-up, and the 80% bar of ADR-0005 as pass or fail); the full table, the eras as columns and the whole period last with the same numbers the batch command prints, opens under "every number", every row label explaining its number on hover.

**Strategy** (none or `flip`) walks a strategy over the same replay. Its buys and sells are drawn as squares labelled `buy` and `sell` on the candle each order filled on, the candle after the mark that caused it, and one line plus a short table under the detector's say what the 500 USD became: the account under each cost model and holding Bitcoin instead at the end of every era and of the period, in USD and as a change, with the trades and their cost, and the bar of ADR-0008 read out as pass or fail; the account reads green where it kept up with holding and red where it did not. The full tables under both cost models open under "every number", the perpetual's first since the bar is judged under it; the status line counts the fills shown. The replay itself does not change: the strategy reads the same marks the chart draws. An account-versus-benchmark line is a later slice.

**From** picks a start date, a calendar day in UTC, shared by both modes and kept in the page address (`?from=2021-01-01`), so a reload or a bookmark keeps it; empty means the first stored candle. It moves where you start watching, never what a detector reads. In Hindsight the view runs from that day to the end of the development period. In Replay the detector still replays from the first stored candle (ADR-0005), so its marks, lines and score are those of the recorded run; the replay jumps to the first candle on or after the date, with everything up to that moment shown at once as it stood then, and plays on from there. The counts in the status line (turning points confirmed, marks placed, hits, false, pending, before the scoring period) count from the start date on; the score block does not change. Earlier candles stay loaded and can be reached by dragging the chart left.

The legend under the chart lists only what the mode and the detector can draw, and names the reversal size of the turning points shown, the detector's in Replay and the 8% the hindsight route keeps in Hindsight (a picker for another size is a later issue): in Hindsight the turning points alone; in Replay also the marks and their colours, the orange level lines when the detector reads levels (`one` and `two`), the purple swing-extreme line when it reads swing extremes (`three`), and the buy and sell squares only when a strategy is chosen. The dashboard reads this from the replay's answer, so a new detector gets the right legend without a dashboard change.

## Replay from the command line

```sh
uv run tradingbot replay floor
```

Replays the whole development period through the named detector, so it carries its state into the scoring period, finds the turning points at the reversal size the detector declares for its family (8% for all four; the score's first line names it), scores the marks from 2016 on (for the period and per era) and writes the chart data (the same JSON the API answers for `/replay`) to `replay-<detector>.json` next to the store, or to `--out`. The chart data records the whole run, every candle the detector read and every mark it placed, with the marks before the scoring period unscored, so the run can be re-scored later (ADR-0004). The score is identical run to run. A recorded run is never replaced: the command refuses to overwrite an existing chart-data file, so pass `--out` for a fresh run. Four detectors exist: `floor`, the reference, `one`, the first candidate, and `two`, its second iteration, all on hourly candles, and `three`, the first iteration of family two, on fifteen-minute candles (the chart data of its run is four times the size of an hourly one). This is the floor's reference score, re-scored under the slice 7 definitions (ADR-0007) from the run recorded on issue #11 (every re-scoring is appended there too):

```
Re-scored floor under ADR-0007: 4463 marks, identical in number and time to the recorded run in data/replay-floor.json.
Replayed floor over 85857 candles from 2013-10-06T21:00:00Z to 2024-10-18T23:00:00Z, scored over the scoring period: 76881 candles from 2016-01-01T04:00:00Z to 2024-10-18T23:00:00Z.
  reversal size    8%
  turning points   798
  marks            3180
  hits             259  (hit rate 32.5%)
  false marks      2921  (false-mark rate 91.9%)
  false marks/hit  11.3 per hit
  median timing    +0.0 candles (on time)
  median give-up   3.80%
  2016-2018        360 turning points, 1331 marks, 140 hits (hit rate 38.9%), 1191 false marks (false-mark rate 89.5%), 8.5 per hit, median timing +0.0 candles (on time), median give-up 3.59%
  2019-2021        315 turning points, 1212 marks, 101 hits (hit rate 32.1%), 1111 false marks (false-mark rate 91.7%), 11.0 per hit, median timing +0.0 candles (on time), median give-up 4.09%
  2022-2024        123 turning points, 637 marks, 18 hits (hit rate 14.6%), 619 false marks (false-mark rate 97.2%), 34.4 per hit, median timing +0.0 candles (on time), median give-up 3.43%
```

The floor sets no bar (ADR-0005): the hit-rate bar is absolute, and false marks per hit carry no bar (ADR-0007). Detector one's, detector two's and detector three's scores are not in this file on purpose: issues #12, #16 and #20 pre-register their success criteria, and each one's single development run, its verdict and its re-scorings are recorded as comments there.

## Re-score a recorded run

```sh
uv run tradingbot re-score floor
```

ADR-0004 rules that a recorded run is re-scored, never re-run, when the harness changes. The command reads the recorded run's chart data (`replay-<detector>.json` next to the store, or `--recorded`), replays its own candles through the detector, never past the out-of-sample boundary, and refuses to report unless the marks are identical in number and time to the recorded ones. It then prints the score under the current definitions, named by the ADR that last changed them, for the scoring period and per era, in the same shape as `replay`. The three family-one files hold every candle their runs read, three dropped prints included, which is why the marks come out identical although the store no longer holds those prints; detector one's 2017 marks in the zones of the two spurious levels those prints made (3,484 and 4,000) stay in its recorded run and are scored with it.

## Backtest a strategy

```sh
uv run tradingbot backtest flip
uv run tradingbot backtest flip --detector floor
```

ADR-0008 fixes how a strategy is judged, and this command is the harness (issue #32); since slice 10 it runs on any detector (`--detector`, default `three`, so the documented command keeps working), because family three's bar is the flip on its marks (ADR-0009). It reads the detector's recorded run, `replay-<detector>.json` next to the store (or `--recorded`), replays the run's own candles through the detector as `re-score` does, and refuses to report unless the marks are identical in number and time to the recorded ones, or when the file records another detector's run; so every backtest runs on the one recorded run, whatever the store holds now and never on a detector that drifted. A detector that tracks no swing hands the strategy its marks with no swing extreme. The account starts flat with a notional 500 USD at the first candle of the scoring period. From that candle on, at the close of every fifteen-minute candle, the strategy is asked for its desired position, long or flat, given the candles so far, the marks so far each with the swing extreme it was measured against, the turning points confirmed so far and its own position; a change of desired position becomes a market order filled at the next candle's open. Marks before the scoring period are history the strategy may read, never acted on: the harness places an order only while the latest mark lies in the scoring period. Sizes are all in and not rounded to Kraken's minimum order size.

Two cost models are applied to every run, one account each, and both are reported. A fill is the next candle's open moved 0.05% against the bot (a buy at open × 1.0005, a sell at open × 0.9995) plus the model's fee on the fill's value: 0.80% a fill under spot, with no funding; 0.05% a fill under the perpetual, plus funding of 0.00125% of the position's value (Bitcoin held × the hourly close) at every hourly close while long, always a cost, 11% a year. Under both the position is 1x, the whole account at the fill. The benchmark is one account that buys Bitcoin at the first candle of the scoring period with one spot fill and holds; it is the same under both models. The account is valued at every fifteen-minute close, USD plus Bitcoin at the close; growth of a period is its value at the last close divided by its value at the close before the period began (the starting 500 USD for the first era and for the whole period); the worst drawdown is the largest fall from an earlier peak over the closes of the period, in percent of that peak, so an era's peak starts afresh at its first close and a fall from a peak late in the previous era shows only in the whole period's line. Under the perpetual a trade's result carries the funding paid while it was open, since the sale settles it.

The strategy score, for the scoring period and per era under each cost model: growth next to the benchmark's, the worst drawdown next to the benchmark's, the number of trades (round trips opened in the period), the fees and funding paid in USD, the share of fifteen-minute candles spent long, the result per trade after both fills as a percentage of the account's value at entry, mean and median, grouped by the outcome of the mark that opened the trade and the mark that closed it (`hit→hit`, `hit→false`, `false→hit`, `false→false`, opened on → closed on, with the count of each), and whether a 20% drawdown halt would have fired: the first close it would have, and the number of separate episodes, a new episode needing a new peak first. The halt is reported, never applied. The verdict reads the bar of ADR-0008: growth at least the benchmark's in every era under the perpetual cost model; the spot column carries no bar.

The chart data goes to `backtest-<detector>-<strategy>.json` next to the store, or to `--out`, and an existing file is never overwritten; the flip's recorded run on detector three keeps slice 9's name, `backtest-flip.json`, and the command refuses to replace it. The file holds the detector and the strategy, every fill (the mark that caused it, the order's side, the fill's candle, price, and the size, fee and account value after the fill under each cost model), the account's value at every hourly close under each cost model with the benchmark's at the same closes, both cost models' numbers, and the score. Re-score a recorded backtest with `uv run tradingbot re-score three --strategy flip`: it re-scores the recorded run as above, walks the strategy over it again, refuses unless the fills are identical in number and time to those in `backtest-<detector>-<strategy>.json` next to the store (`backtest-flip.json` for the flip on three, or `--recorded-backtest`), and prints both scores, the strategy's under the current cost models named by the ADR that last fixed them.

One strategy exists: `flip`, the reference of ADR-0008, which is never a candidate and sets no bar: flat at the start, long on a bottom mark when flat, flat on a top mark when long, a mark of the kind the position already answers does nothing, nothing else. It gives the raw price of acting on every mark in money, the number every strategy family one iteration starts from. This is its reference score, from the one run recorded on issue #32 on 22 October 2026:

```
Backtested flip on three over 319495 candles from 2013-10-06T21:30:00Z to 2024-10-18T23:45:00Z, the account from 2016-01-01T04:15:00Z: 303109 candles, 868 fills.
  under the spot cost model
    growth           ×0.00174  (benchmark ×156)
    worst drawdown   99.8%  (benchmark 84.0%)
    trades           434
    fees             422.15 USD
    funding          0.00 USD
    time long        36.8%
    hit→hit          21 trades, mean +3.70%, median +3.27%
    hit→false        85 trades, mean +2.69%, median +3.54%
    false→hit        54 trades, mean -3.60%, median -2.15%
    false→false      274 trades, mean -1.15%, median +0.02%
    20% halt         first 2016-06-22T22:30:00Z, 1 episode
    2016-2018        growth ×0.0399 (benchmark ×8.43), worst drawdown 96.6% (benchmark 84.0%), 195 trades, fees 391.57 USD, funding 0.00 USD, long 27.4%, hit→hit 12 (+5.11%), hit→false 37 (+2.87%), false→hit 26 (-4.02%), false→false 120 (-1.55%), 20% halt first 2016-06-22T22:30:00Z, 1 episode
    2019-2021        growth ×0.203 (benchmark ×12.5), worst drawdown 83.2% (benchmark 71.1%), 175 trades, fees 28.79 USD, funding 0.00 USD, long 43.2%, hit→hit 9 (+1.81%), hit→false 39 (+1.88%), false→hit 21 (-1.94%), false→false 106 (-0.49%), 20% halt first 2019-07-14T16:15:00Z, 1 episode
    2022-2024        growth ×0.215 (benchmark ×1.48), worst drawdown 81.0% (benchmark 67.5%), 64 trades, fees 1.78 USD, funding 0.00 USD, long 39.6%, hit→hit 0, hit→false 9 (+5.43%), false→hit 7 (-7.05%), false→false 48 (-1.59%), 20% halt first 2022-01-21T21:45:00Z, 1 episode
  under the perpetual cost model
    growth           ×0.82  (benchmark ×156)
    worst drawdown   60.9%  (benchmark 84.0%)
    trades           434
    fees             198.42 USD
    funding          169.99 USD
    time long        36.8%
    hit→hit          21 trades, mean +4.45%, median +4.05%
    hit→false        85 trades, mean +3.42%, median +4.32%
    false→hit        54 trades, mean -2.97%, median -1.45%
    false→false      274 trades, mean -0.49%, median +0.67%
    20% halt         first 2016-06-23T01:30:00Z, 4 episodes
    2016-2018        growth ×0.676 (benchmark ×8.43), worst drawdown 59.3% (benchmark 84.0%), 195 trades, fees 68.54 USD, funding 33.84 USD, long 27.4%, hit→hit 12 (+5.88%), hit→false 37 (+3.62%), false→hit 26 (-3.37%), false→false 120 (-0.85%), 20% halt first 2016-06-23T01:30:00Z, 1 episode
    2019-2021        growth ×2.43 (benchmark ×12.5), worst drawdown 54.9% (benchmark 71.1%), 175 trades, fees 97.32 USD, funding 74.40 USD, long 43.2%, hit→hit 9 (+2.55%), hit→false 39 (+2.61%), false→hit 21 (-1.30%), false→false 106 (+0.17%), 20% halt first 2019-07-28T22:00:00Z, 4 episodes
    2022-2024        growth ×0.501 (benchmark ×1.48), worst drawdown 56.5% (benchmark 67.5%), 64 trades, fees 32.57 USD, funding 61.75 USD, long 39.6%, hit→hit 0, hit→false 9 (+6.18%), false→hit 7 (-6.49%), false→false 48 (-1.06%), 20% halt first 2022-01-21T21:45:00Z, 1 episode
  bar (ADR-0008)     growth at least the benchmark's in every era under the perpetual cost model: fail (2016-2018 ×0.676 vs ×8.43, 2019-2021 ×2.43 vs ×12.5, 2022-2024 ×0.501 vs ×1.48)
```

The flip passes or fails nothing: the bar is absolute and the flip only prices it. For a detector of family three that same bar line is the detector's own verdict: its development run is a replay plus the flip on it (ADR-0009). Candidate strategies are pre-registered in their own issues, as detectors are, and each one's single development run, its verdict and its re-scorings are recorded there.

## Paper trading

```sh
uv run tradingbot paper --detector three --strategy flip
uv run tradingbot paper report --detector three --strategy flip
```

Both flags default to `three` and `flip`, so `uv run tradingbot paper` is the same loop. ADR-0009 starts paper trading before any detector of family three exists, so the cost model of ADR-0008 meets the market first. Detector three and the flip run in it as the reference: never a candidate, no bar. Only a detector already in `out-of-sample.log` may run, which today is detector three; a detector of family three joins after its own check. Run it from the repository root, like the out-of-sample check, since that is where the log is read.

`paper` runs until you stop it with Ctrl-C. It catches up the fifteen-minute store from Kraken's spot endpoint as `catch-up --timeframe 15m` does, then consumes every candle once, 15 seconds after it closes: the candle goes to detector three and to the flip in the backtest's order, and a change of position becomes an order filled at the next candle's open, moved 0.05% against the bot, plus the 0.05% fee. Funding is the model's 0.00125% of the position's value at every hourly close while long. The account is a notional 500 USD, flat at the loop's first step, the first candle to close after the loop first started; holding buys 500 USD of Bitcoin at that candle's open with one spot fill. The loop prints one line per step and one per fill. Next to the model it records what Kraken Futures says, from its public endpoints and with no key: the mark price of `PF_XBTUSD` when an order is placed and at every hourly close, kept as the basis over spot, and Kraken's own funding rate for every hour, filled in as Kraken publishes it. A reading that fails stays empty, is never invented, and the step completes without it; a failing candle source is tried again 15 seconds later.

The record lives in four tables of the store's SQLite file, `paper_steps`, `paper_orders`, `paper_fills` and `paper_hours`, keyed by detector and strategy so two loops never mix, and every row is written once. A restart replays the whole store to rebuild the detector's and the flip's state, consumes the candles that closed while the loop was stopped, and never records a fill twice; it refuses to continue when the stored candles no longer produce the recorded fills. A stop longer than the endpoint's reach of 7.5 days is refused with the instruction to import the quarterly archive first. On the first start a hole before the loop's first step is only warned about, since it lies in the detector's history: the quarterly archive for October 2026 does not exist yet, so a store that ends on 30 September starts with the first half of October missing, and the reconciliation replays the same store, hole included.

`paper report` reads the record back:

| Line | What it says |
| --- | --- |
| first line | the steps consumed, from the first to the last, the fills, and the share of closes spent long |
| `account` | the account's value at the last close under the perpetual cost model, in USD and as growth on 500 USD |
| `holding` | the benchmark's value at the same close, bought at the first step's open with one spot fill |
| `fills` | every fill: side, size, the model's price (the open moved 0.05%), fee, account after it, and the mark price read when the order was placed with the basis over the close it was placed on |
| `basis at fills` | the basis at the fills, perpetual mark price over spot in percent: how many were read and the three quartiles |
| `basis at hours` | the same at every hourly close the loop lived through |
| `funding` | the model's funding against Kraken's real rate on the same position, summed over the hours long with a rate published; hours long whose rate is not published yet are counted apart; one line per month follows |
| `reconciliation` | a backtest of the same detector and strategy over the stored candles, the account from the loop's first step: the fills it makes, and how many of the loop's differ in time, side or price, or exist on one side only; expected zero |

## Check the hourly candles built from the fifteen-minute ones

```sh
uv run tradingbot check-hourly
```

A fifteen-minute replay finds its turning points on hourly candles it builds from the fifteen-minute stream (ADR-0006). This command builds them the same way from the stored fifteen-minute candles and compares them with the stored hourly table over the scoring period: hours only in one table, hours whose candles differ, and turning points found on one series and not the other. On the full archive, imported on 20 October 2026 and read to the boundary of 2025-01-01, every count is zero: 78,657 hours and 807 turning points on both sides (76,881 and 798 before the boundary moved in slice 10).

## Definitions fixed in slice 2

These were fixed in issue #11 before any detector was built. Changing any of them is a new decision, recorded in an ADR before any run (ADR-0004); slice 5 changed the tolerance, added the scoring period and the eras, and made the floor a reference that sets no bar. The numbers live as constants in the modules named below.

| Definition | Value | Where |
| --- | --- | --- |
| Turning point | hindsight, on hourly candles, reversal size 8% (since slice 10 the size the detector's family declares, 8% for families one and two; the hindsight route keeps 8%); the extreme is the candle high for a top and the candle low for a bottom, the reversal is measured to a later candle's low or high; tops and bottoms alternate | `turning_points.py`, `detectors.py` |
| Mark | placed only on the latest candle, at its close | `detectors.py` |
| Tolerance | a mark is a hit when a turning point of its kind lies within 24 candles before or after it and the mark's close is within 2% of the extreme; one hit per turning point, the nearest mark in candles; the rest are false marks | `scoring.py` |
| Score | hit rate, false-mark rate, false marks per hit (added by ADR-0007 in slice 7, reported without a bar), median timing in candles (negative early, positive late), median give-up in percent, plus the raw counts | `scoring.py` |
| Floor detector | top on the first close 3% below the highest high since the last bottom mark, bottom on the first close 3% above the lowest low since the last top mark | `detectors.py` |
| Out-of-sample boundary | `2024-10-19T00:00:00Z` until slice 10; `2025-01-01T00:00:00Z` since (ADR-0009) | `development.py` |

Distances in candles count candles of the hourly series, so a missing hour neither widens nor narrows a tolerance.

## Definitions fixed in slice 5

Decided on 20 October 2026 and recorded in ADR-0004, ADR-0005 and ADR-0006 before any detector of family two runs (issue #19). The harness changes only this way: by an ADR written before any run, justified by hindsight facts about candles and turning points alone, and every recorded run is re-scored under the new definitions.

| Definition | Value | Where |
| --- | --- | --- |
| Timeframe `15m` | fifteen-minute candles, stored next to the hourly ones in `candles_15m`; 4h and 1d stay resampled from hourly | `candles.py`, `store.py` |
| Tolerance B | a hit lies within 24 hourly candles of a turning point of its kind, and its close is within 2% of the extreme or no further than the extreme hourly candle's own close (ADR-0005) | `scoring.py` |
| Scoring period | from `2016-01-01T00:00:00Z` (Unix 1451606400) to the boundary, since slice 10 the end of 2024 (ADR-0009: the two and a half months added were read once, in #28's aggregate out-of-sample score, and that caveat stands); replays still start at the first stored candle | `scoring.py`, `development.py` |
| Eras | 2016 to 2018, 2019 to 2021, 2022 to 2024, the third whole since slice 10; every score is printed for the period and per era | `scoring.py` |
| Bars | hit rate at least 80% in every era, the only bar since ADR-0007 (slice 7); false marks per hit reported, with no bar (slice 6 was judged under the earlier bar of at most one per hit); no give-up bar | issue #20, ADR-0007 |
| Dropped prints | the hourly candles at Unix 1383807600, 1384056000 and 1384236000 (2013-11-07 07:00, 2013-11-10 04:00, 2013-11-12 06:00 UTC) and every 15-minute candle inside those hours; skipped at import, deleted once from the existing store | `sync.py` |
| A 15-minute mark | placed at the 15-minute close; scored by the hour it falls in; timing in hourly candles; give-up from the 15-minute close; at most one mark per 15-minute candle | `scoring.py`, `replay.py` |
| Hourly candles in a 15-minute replay | built from the 15-minute stream when the hour completes (the candle ending at the hour, the first candle of a later hour, or the last candle of the series), fed to the turning-point finder, and compared with the stored hourly table over the scoring period | `replay.py`, `hourly_check.py` |

A turning point confirmed by the hour a fifteen-minute candle completes is visible to the detector on that candle. Two readings fixed in code rather than in the ADRs: a hit belongs to the era of its turning point, a false mark to the era of its mark; and the scoring period is scored as a series of its own, as the out-of-sample check is, so a January 2016 mark whose turning point lies in late December 2015 is a false mark.

## Definitions fixed in slice 6

Fixed in issue #20 before detector three's first run, with the same rule: changing one is a new iteration, never an adjusted rerun. Issue #20 also records the hindsight tables over the scoring period that led to the rule, and the scripts behind them.

| Definition | Value | Where |
| --- | --- | --- |
| Swing low | the lowest fifteen-minute low at or after the start of the hour holding the last confirmed top; before any top is confirmed there is no swing low and no top mark | `detectors.py` |
| Swing extreme | the highest fifteen-minute high at or after the swing low's candle, that candle included | `detectors.py` |
| Armed | a new swing extreme arms a top mark, and so does a new swing low, since the extreme restarts at that candle's high; a mark disarms its side until the next new extreme; a newly confirmed top recomputes the swing low and the extreme from that top's hour and arms | `detectors.py` |
| Detector three | a top mark on an armed candle whose high is below the swing extreme while the extreme is at least 8% above the swing low (`extreme >= swing low × 1.08`), placed at that candle's close; bottoms are the mirror (`extreme <= swing high × 0.92`); when one candle qualifies for both, the side whose swing is larger in percent wins and equal swings give no mark, the other side keeping its arming; at most one mark per candle; no depth, no levels, no run, no volume | `detectors.py` |
| Timing of knowledge | a turning point confirmed by an hourly candle is known from the fifteen-minute candle that completes that hour, on that same candle | `replay.py` |
| Swing extremes in the chart data | every replay answers the swing extremes the detector read, each with the candle holding it, the first candle the detector read it on and the last one that read it, so the dashboard draws what the detector used | `replay.py` |

## Definitions fixed in slice 9

Decided on 20 October 2026 and recorded in ADR-0008 before any strategy ran, on facts that involve no strategy (issue #32). The cost models and the bar are harness definitions under ADR-0004: they change only by ADR, and every recorded backtest is then re-scored and the numbers appended to its issue.

| Definition | Value | Where |
| --- | --- | --- |
| Account | a notional 500 USD, flat at the first candle of the scoring period; the strategy is asked at every fifteen-minute close from then on; all in at every fill, 1x, no rounding to a minimum order size | `backtest.py` |
| Fill | a market order sent at the close the strategy changed its mind on, filled at the next candle's open moved 0.05% against the bot, plus the model's fee on the fill's value | `backtest.py` |
| Spot cost model | 0.80% a fill, no funding | `backtest.py` |
| Perpetual cost model | 0.05% a fill, and funding of 0.00125% of the position's value at every hourly close while long (11% a year), drawn from the USD side | `backtest.py` |
| Benchmark | one account that buys Bitcoin at the first candle of the scoring period with one spot fill and holds; the same under both cost models | `backtest.py` |
| Growth | the value at the period's last close over the value at the close before the period began; the starting 500 USD for the first era and for the whole period | `backtest.py` |
| Worst drawdown | the largest fall from an earlier peak over the closes of the period, in percent of that peak; the peak starts afresh at each period's first close | `backtest.py` |
| Drawdown halt | a 20% fall from the peak; the first close it would fire at and the number of episodes are reported, a new episode needing a new peak; never applied | `backtest.py` |
| Trade | one round trip; its result is the account's value after the exit fill less its value after the entry fill, in percent of the latter, funding paid while open included; it belongs to the era its entry filled in and to the group of the outcomes of the marks that opened and closed it | `backtest.py` |
| Bar | growth at least the benchmark's in every era under the perpetual cost model; the spot column is reported, no bar | `backtest.py` |
| What a strategy reads | the candles so far, the marks so far each with the swing extreme it was measured against, the turning points confirmed so far, and its own position; never a mark's outcome; a change of position is placed only while the latest mark lies in the scoring period | `strategies.py`, `backtest.py` |
| Flip | the reference: long on a bottom mark when flat, flat on a top mark when long, nothing else; never a candidate | `strategies.py` |

## Definitions fixed in slice 10

Decided on 22 October 2026 and recorded in ADR-0009 before the budget look and before any detector of family three exists (issue #38). No detector is added and no pre-registered run happens in this slice.

| Definition | Value | Where |
| --- | --- | --- |
| Reversal size | a property of a detector, declared in code next to its name and timeframe; `floor`, `one`, `two` and `three` declare 8%; a constant, never read from the market or a setting | `detectors.py` |
| Turning points of a replay | found at the detector's reversal size; the hindsight route keeps 8% unless asked for another size | `replay.py`, `api.py` |
| Out-of-sample boundary | `2025-01-01T00:00:00Z` (Unix 1735689600); the development period, the scoring period and every development read end with `2024-12-31T23:45:00Z` | `development.py` |
| Eras | unchanged: 2016 to 2018, 2019 to 2021, 2022 to 2024, the third now whole | `scoring.py` |
| Family three's bar | the flip on the detector grows at least as much as the benchmark in every era under the perpetual cost model; the detector's own score is reported, no part of it a bar | `backtest.py` |
| The check | the flip on the detector from the boundary to the newest stored fifteen-minute candle, the account starting flat with 500 USD at the boundary's first candle, judged over the period as one: growth at least the benchmark's under the perpetual cost model, the benchmark buying at the period's first candle with one spot fill | `out_of_sample.py`, `backtest.py` |

The four recorded runs stay at 8% and are not re-scored, since nothing in their definitions changed: `re-score floor`, `one`, `two` and `three` print the numbers recorded under ADR-0007, with the reversal size as a new first line, and `re-score three --strategy flip` the fills and score recorded on #32.

## Definitions fixed in slice 11

Fixed in issue #39 before the loop's first step. The live numbers of ADR-0008, hosting, alerts, the account size and the halt, stay parked for the paper-trading grilling.

| Definition | Value | Where |
| --- | --- | --- |
| Candle source | Kraken's public spot OHLC endpoint, interval 15, as `catch-up` reads it; a candle is consumed only once it is complete and stored | `paper.py`, `sync.py` |
| Step | once per fifteen-minute candle, after it closes: store it, hand the candles so far, the marks so far and the turning points so far to the detector and the strategy in the backtest's order, and if the desired position changed, record an order to fill at the next candle's open | `paper.py`, `replay.py`, `backtest.py` |
| Fill | the next candle's open moved 0.05% against the bot, plus the 0.05% fee, as the perpetual cost model; recorded when that candle arrives | `backtest.py` |
| Funding | 0.00125% of the position's value at every hourly close while long, as the model; Kraken Futures' relative rate for the same hour recorded next to it | `paper.py`, `kraken_futures.py` |
| Basis | at every order and every hourly close: the mark price of `PF_XBTUSD` over the spot close, in percent, from the public Futures ticker; missing when the endpoint fails, never invented | `paper.py`, `kraken_futures.py` |
| Account | a notional 500 USD, flat at the loop's first step; valued at every fifteen-minute close like the backtest's | `paper.py`, `backtest.py` |
| Restart | the loop rebuilds the detector's and the strategy's state by replaying the whole store, then continues from the last stored candle; a fill already recorded is never recorded twice | `paper.py` |
| Gap | a stop longer than the endpoint's reach, 7.5 days, is refused with the instruction to import the quarterly archive first | `paper.py` |

Three readings fixed in code rather than in the issue. The basis at a fill is read when its order is placed, at the close of the mark's candle, since that is when a live order would reach the exchange; the fill itself comes at the next open. Kraken publishes a funding rate per hour, stamped with the hour it starts; the rate charged at an hourly close is the one stamped with the hour that starts there. A loop's first start with a hole older than the reach warns rather than refuses, as above.

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

Development data is every stored candle, fifteen-minute or hourly, that starts before the boundary, `2025-01-01T00:00:00Z` since slice 10 (ADR-0009; `2024-10-19T00:00:00Z` before it), so the development period ends with the candle at `2024-12-31T23:45:00Z`. Every development entry point, the three API routes, the batch replay, the re-scoring and the hourly check, reads through one function that clamps the window to the boundary, so no command can read past it by accident. Nothing from the boundary on grades anything: it is no era, no score, no look and no chart, and it is read for the first time by family three's check. `import` and `catch-up` still store newer candles; they are kept for the out-of-sample check below. The local store must hold candles from before the boundary for any of this to show anything: the quarterly archives only reach back to 2026, so the development period comes from the full archive.

## The out-of-sample check

```sh
uv run tradingbot out-of-sample one
uv run tradingbot out-of-sample <detector> --strategy flip
```

The one command that reads past the boundary. It replays the whole stored history of the detector's timeframe through the detector, so the detector carries every level it has by the boundary, and scores only the candles from the boundary on, as a series of their own and without eras. It prints the score in the same shape as `replay`, writes the chart data (the whole run, the marks before the boundary unscored) to `out-of-sample-<detector>.json` next to the store (or to `--out`), and appends one line to `out-of-sample.log` in the working directory: when it ran, the detector, the period and the score. Run it from the repository root, like every other command, so that file is committed with the code and every run is on record. A detector that is already in the log is refused: the protocol in issue #12 gives each detector one out-of-sample run, and the command runs only after a detector has passed its success criterion over the development period. Detector three had its run on 20 October 2026 (slice 8, issue #28, which pre-registers the criterion and records the score and the verdict): `out-of-sample.log` holds that line, so the command refuses `three` from now on, in both forms, and family two's one check is spent. The API and the dashboard never read past the boundary.

With `--strategy flip` the command is family three's check (ADR-0009): after scoring the detector from the boundary on as above, it walks the flip over the replay from the boundary, the account starting flat with 500 USD at the boundary's first candle and the benchmark buying there with one spot fill, and judges it over the period as one, with no eras: growth at least the benchmark's under the perpetual cost model, read out on the `bar (ADR-0009)` line. It prints the detector's score and the strategy's in the shapes of `replay` and `backtest`, writes the backtest's chart data to `out-of-sample-<detector>-<strategy>.json` next to the replay's, and the one log line holds both scores and the verdict, tab-separated after the detector's score. A pass there says the detector behaved as predicted on data nobody read, not statistical proof.

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
  kraken_futures.py  the public Kraken Futures ticker and funding history: no key, no order route
  sync.py            archive import (dropped prints skipped) and catch-up
  development.py     the out-of-sample boundary and the only way to read development candles
  turning_points.py  turning points in hindsight, found one hourly candle at a time
  detectors.py       the Detector interface, Mark, Level, SwingExtreme, the floor detector, detectors one, two and three
  scoring.py         tolerance B, the scoring period, the eras, and the score
  replay.py          replay: candles to a detector one at a time, hours built from 15-minute candles, then the score
  re_score.py        a recorded run (and a recorded backtest on it) replayed on its own candles and scored under the current definitions
  hourly_check.py    the hourly candles built from 15-minute ones against the stored hourly table
  out_of_sample.py   the one explicit check past the boundary, logged per run, with the flip for a detector of family three
  strategies.py      the Strategy interface, what a strategy reads, and the flip
  paper.py           the paper-trading loop, its record in the store's file, and the report with the reconciliation
  backtest.py        the strategy backtest, walked one candle at a time: the account, the two cost models, the benchmark, the strategy score and the bar, per era or over a period as one
  api.py             the FastAPI app with GET /candles, /turning-points (with an optional reversal size) and /replay (with an optional strategy)
  cli.py             the tradingbot command: import, catch-up, serve, replay, re-score, check-hourly, out-of-sample (with --strategy), backtest (with --detector), paper and paper report
tests/               pytest suite
dashboard/           SvelteKit app: hindsight view and replay
docs/adr/            architecture decision records
GLOSSARY.md          the project's vocabulary
```
