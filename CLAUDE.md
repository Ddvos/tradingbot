# TradingBot — Claude Code Instructies

## Projectoverzicht

Dit is een crypto trading bot voor BTC perpetual futures op Kraken. Het systeem
bestaat uit een **backend** (Python) die data verwerkt, ML-modellen traint,
backtests draait, en live trading uitvoert, en een **frontend** (SvelteKit)
die als dashboard fungeert.

**Doel:** een leerproject voor financial ML waarbij we eerlijk en rigoureus
strategieën ontwikkelen, valideren, en eventueel live draaien met klein
kapitaal. Geen "auto-search until profitable" — bewuste, hypothese-gedreven
ontwikkeling met strikte validatie.

**Belangrijkste asset:** PF_XBTUSD op Kraken Futures, primair op 1H timeframe.

## Mentale modellen die we volgen

1. **Hypothese-gedreven, niet zoek-gedreven.** Elke strategie begint met een
   economische of gedragsmatige hypothese, niet met "probeer 1000 combinaties
   en pak de beste".

2. **Strikte data-scheiding.** Train/validation/test (chronologisch, nooit
   random). Holdout test wordt één keer per strategie gebruikt, daarna nooit
   meer aangeraakt voor diezelfde strategie.

3. **Walk-forward over single-split.** Time series rechtvaardigen rolling
   walk-forward validation met purging en embargo.

4. **Simpele modellen, doordachte features.** Liever 15-25 zorgvuldig gekozen
   features dan 200 willekeurige indicators.

5. **Conservatieve cost assumptions.** Fees, slippage, en funding rates altijd
   meenemen in backtests, eerder pessimistisch dan optimistisch.

6. **Eén live strategie tegelijk.** Multipele getrainde strategieën in
   bibliotheek, één expliciet gepromoot naar live trading.

## Architectuur

**Patroon:** lichte Hexagonal architecture voor de engine, VSA-stijl voor de
API, FSD voor de frontend. Pipes & Filters als mental model voor de runtime
flow (data → features → predictions → signals → risk → execution).

**Backend lagen:**

- `core/` — pure business logic, geen I/O, framework-agnostisch
- `api/` — FastAPI server, alleen vertaling van HTTP naar core-aanroepen
- `live/` — autonome runner voor live/paper trading
- `config/` — Pydantic configs, settings

**Belangrijke abstracties:**

- `MarketDataProvider` (port) — geïmplementeerd door `KrakenProvider` (live)
  en `ParquetProvider` (backtest)
- `OrderExecutor` (port) — geïmplementeerd door `KrakenExecutor` (live) en
  `SimulatedExecutor` (backtest)

Backtest en live draaien dezelfde strategie-code, alleen andere adapters.

## Tech stack

### Backend

- **Python 3.13** met `uv` als package manager
- **FastAPI** voor de API
- **Pydantic v2** voor configs en validation
- **Polars** voor data manipulation (niet Pandas)
- **DuckDB** voor ad-hoc SQL queries op Parquet
- **XGBoost** + scikit-learn voor ML
- **APScheduler** voor live job scheduling
- **SQLAlchemy 2.0** of **SQLModel** voor ORM (nog te beslissen)
- **Alembic** voor database migrations
- **pytest** voor tests
- **ruff** voor linting en formatting

### Storage

- **Parquet files** voor historische OHLCV, features, equity curves
- **PostgreSQL** voor live state: trades, positions, orders, strategy configs,
  backtest run metadata, model registry
- **Filesystem (.joblib)** voor getrainde model artefacten

### Frontend

- **SvelteKit** met **Svelte 5** (runes syntax)
- **Tailwind CSS**
- **lightweight-charts** (TradingView library) voor financial charts
- **shadcn-svelte** componenten waar relevant

## Folder structuur

```
tradingbot/
├── CLAUDE.md
├── README.md
├── backend/
│   ├── pyproject.toml
│   ├── .python-version
│   ├── .env.example
│   ├── src/tradingbot/
│   │   ├── api/
│   │   │   └── routes/
│   │   ├── core/
│   │   │   ├── data/         # Kraken fetcher, Parquet storage
│   │   │   ├── features/     # Technical indicators, labeling
│   │   │   ├── models/       # XGBoost trainer, walk-forward
│   │   │   ├── strategies/   # Strategy definitions
│   │   │   ├── backtest/     # Engine, costs, metrics
│   │   │   ├── risk/         # Position sizing, limits
│   │   │   └── execution/    # Order placement
│   │   ├── live/             # Live/paper runner
│   │   └── config/           # Pydantic settings
│   ├── tests/
│   ├── scripts/              # Standalone CLI tools
│   └── data/                 # Lokaal, niet in git
│       ├── raw/
│       ├── processed/
│       └── models/
├── frontend/
└── configs/                  # YAML strategy configs
    └── strategies/
```

## Strategie ontwikkelcyclus

```
1. Hypothese formuleren
2. Strategie configureren (YAML)
3. Trainen op development data met walk-forward
4. Resultaten analyseren (IC, Sharpe, drawdown, sanity checks)
5. Goed? → Holdout test (één keer!) → Paper trading → Klein live
   Niet goed? → Max 5 iteraties, anders nieuwe hypothese
```

## ML aanpak (v1)

- **Model:** XGBoost classifier
- **Target:** triple-barrier labeling (López de Prado)
  - Upper barrier: entry + 2.0 × ATR
  - Lower barrier: entry − 1.5 × ATR
  - Time barrier: 6 bars
- **Features:** 15-25 stuks, multi-timeframe (4H trend + 1H anchor + 15M momentum)
  - Trend: MA slopes, EMA crosses
  - Momentum: RSI (1H, 4H), MACD histogram
  - Volatility: ATR (1H), Bollinger Band width, realized vol
  - Volume: volume vs MA, OBV trend
  - Market structure: distance from key levels
  - Funding: huidige funding rate, funding rate trend
  - Tijd: hour of day, day of week
- **Validation:** purged walk-forward, ~2 jaar rolling window
- **Metrics:** Sharpe, Deflated Sharpe, Information Coefficient (IC), max
  drawdown, win rate, profit factor, statistical significance via bootstrap

## Risk management

- **Position sizing:** ATR-based, 1% risk per trade van account balance
- **Stop loss:** 1.5 × ATR onder entry (long) of boven entry (short)
- **Take profit:** 3.0 × ATR (1:2 risk-reward), of triple-barrier exit
- **Tijd-exit:** sluit positie na 6 bars als geen TP/SL geraakt
- **Circuit breakers:** dagelijkse loss limiet, max consecutive losses
- **Eén positie tegelijk** voor v1

## Trading constraints

- **Exchange:** Kraken Futures
- **Symbol:** PF_XBTUSD (BTC perpetual)
- **Timeframe:** 1H (decisions), met 4H en 15M data als extra features
- **Order type:** limit orders waar mogelijk (maker fees), market als fallback
- **Fees assumptie:** 0.02% maker, 0.05% taker (Kraken Futures basis tier)
- **Slippage assumptie:** 0.05-0.10% per trade
- **Funding rate:** elke 4 uur, meenemen in backtest costs

## Development principes voor Claude Code

1. **Eén ding tegelijk, klein en compleet.** Bouw één bestand/feature
   helemaal af voordat je naar het volgende gaat. Geen 10 lege bestanden
   in één keer.

2. **Code moet self-explanatory zijn.** Liever expressieve naamgeving dan
   commentaar. Commentaar voor _waarom_, niet _wat_.

3. **Type hints overal.** Python 3.13 syntax: `list[int]`, `dict[str, float]`,
   `X | None` (geen `Optional[X]`).

4. **Pydantic voor data validation.** Geen ruwe dicts voor configs of API
   payloads.

5. **Polars over Pandas.** Tenzij er een hele goede reden is voor Pandas.

6. **Geen premature abstractions.** Een interface (Protocol of ABC) maken we
   alleen aan als we minstens 2 concrete implementaties hebben of weten dat
   die gaan komen (zoals MarketDataProvider).

7. **Tests bij elke feature.** Niet 100% coverage, wel happy path + 1-2
   edge cases per module.

8. **Conventional commits.** `feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
   `chore:`.

## Wat we NIET doen

- Geen "auto-search" of "auto-optimize until profitable" systemen
- Geen tick-level order book features in v1 (te complex voor retail)
- Geen RL in v1 (XGBoost eerst goed werkend krijgen)
- Geen deep learning (CNN/LSTM) in v1
- Geen tight stops op visible support levels (stop hunting risk)
- Geen leverage > 2x in v1 (eerst bewijzen dat strategie werkt)

## Live trading regels

- **Eerst paper trading** (minimaal 4 weken) voordat live geld
- **Live start met €100-500**, niet meer
- **Schalen alleen na bewijs** dat live = paper trading
- **Stop loss op systeem niveau:** als systeem 10% verliest, automatisch
  pauzeren en human review

## Status (per 21 mei 2026)

We zijn klaar met:

- Architectuur en aanpak definiëren
- Backend project init (`uv init --package`)
- Python 3.13 + uv 0.7.2 setup
- Folder structuur skeleton in `src/tradingbot/`

Volgende stappen:

1. Subfolders aanmaken in `src/tradingbot/` (api, core, live, config)
2. `.gitignore`, `.env.example` toevoegen
3. Eerste dependencies installeren (polars, pydantic, fastapi)
4. Kraken data fetcher bouwen
5. Parquet storage layer
6. Backtest engine met buy-and-hold baseline

## Externe referenties

- López de Prado: _Advances in Financial Machine Learning_ (concepten:
  triple-barrier, purged CV, deflated Sharpe)
- Stefan Jansen: _Machine Learning for Algorithmic Trading_ (praktische code)
- Rob Carver: _Systematic Trading_ (signal combinatie, speed limit concept)
- Kraken Futures API: https://docs.kraken.com/api/docs/futures-api/

## Bij twijfel

Als Claude Code in twijfel is over een keuze: stel een vraag in plaats van
gokken. Vooral bij:

- Architectuurbeslissingen die meerdere modules raken
- Externe library keuzes
- Database schema wijzigingen
- Risk management parameters
