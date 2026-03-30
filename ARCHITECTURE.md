# Trading Lab Architecture

## Goal

Build a local-first trading research environment that stays simple now but can evolve into a
repeatable research and execution platform.

The architecture should optimize for:

- reproducible data research
- explicit separation of concerns
- low-friction strategy iteration
- realistic backtest assumptions
- future broker integration without rewrites

## Architectural Principles

- Research code and production code are not the same thing. Notebooks can explore, but reusable
  logic belongs in the package.
- Data must be versionable by convention even if we are not using a full data catalog yet.
- Strategy logic should be pure and testable; broker calls and file IO stay at the edges.
- Backtests must consume normalized datasets and explicit run settings.
- Execution must be isolated from research so live trading risk does not leak into notebooks.

## Target Repository Layout

```text
trading-lab/
|-- config/
|   |-- instruments.yaml
|   |-- environments/
|   |   `-- local.yaml
|   `-- strategies/
|       `-- sma_cross.yaml
|-- data/
|   |-- raw/
|   |-- curated/
|   |-- features/
|   `-- backtests/
|-- notebooks/
|-- scripts/
|   |-- ingest_market_data.py
|   `-- sanity_check.py
|-- src/
|   `-- trading_lab/
|       |-- config.py
|       |-- paths.py
|       |-- data/
|       |   |-- models.py
|       |   |-- transforms.py
|       |   `-- yfinance_ingest.py
|       |-- strategies/
|       |   |-- base.py
|       |   `-- sma_cross.py
|       |-- backtesting/
|       |   |-- engine.py
|       |   `-- models.py
|       `-- execution/
|           |-- broker_base.py
|           `-- ig.py
`-- tests/
```

## Layer Responsibilities

### 1. Data Layer

Purpose: fetch, normalize, validate, and store market data.

Rules:

- `data/raw/` stores source-shaped datasets with minimal transformation.
- `data/curated/` stores normalized research-ready datasets.
- `data/features/` stores derived indicators and model features.
- Every dataset should carry metadata by convention: symbol, timeframe, timezone, adjusted flag,
  and source.

Initial source:

- `yfinance` for daily equities and ETF prototyping

Expected next sources:

- broker REST data
- premium historical feeds if strategy quality justifies them

### 2. Strategy Layer

Purpose: express trading decisions without embedding infrastructure concerns.

Rules:

- A strategy consumes bars or features and emits signals.
- A strategy does not read files directly.
- A strategy does not call broker APIs directly.
- Parameters live in config, not hard-coded notebooks.

Initial pattern:

- simple parameterized SMA cross strategy

### 3. Backtesting Layer

Purpose: run reproducible simulations from normalized data and explicit assumptions.

Rules:

- Backtests must declare capital, fee model, slippage model, symbol, timeframe, and date range.
- Results should be saved to `data/backtests/`.
- Output should include both summary metrics and event-level trades when possible.

Minimum realism requirements:

- commissions
- spread or slippage approximation
- no lookahead
- explicit timezone handling

### 4. Execution Layer

Purpose: place and manage live or paper orders through a broker adapter.

Rules:

- Execution depends on strategy outputs, never the other way around.
- Broker-specific details stay behind an interface.
- Start with paper trading semantics even if the first adapter is live-capable.

Initial target:

- IG adapter stub only, no live order placement until research and risk controls exist

## Configuration Model

Use YAML for human-edited configuration.

Split config into:

- environment config: local paths, defaults, runtime behavior
- instrument config: symbols, asset types, sessions, source preferences
- strategy config: parameter sets and backtest presets

## Data Standards

Use these conventions from the start:

- timezone: store timestamps in UTC
- prices: record whether series are adjusted or unadjusted
- file naming: `<symbol>_<timeframe>_<source>.parquet`
- schema: `timestamp, open, high, low, close, volume, symbol, source`

For daily `yfinance` data, we can curate into this normalized schema after download.

## Development Workflow

1. Ingest raw market data.
2. Curate and validate the dataset.
3. Run a strategy through the backtest engine.
4. Save metrics and trade logs.
5. Inspect results in notebooks only after artifacts exist.

That order matters. It keeps notebooks from becoming the system of record.

## Immediate Build Order

1. Establish package structure and shared path/config utilities.
2. Move market-data ingestion into reusable package code.
3. Normalize daily bar storage into `raw/` and `curated/`.
4. Implement one reference strategy and one reference backtest runner.
5. Add tests around data normalization and signal generation.
6. Add broker adapter interfaces after the research path is stable.

## What We Should Avoid Early

- mixing live execution code into notebooks
- coupling strategy code to `yfinance`
- storing only ad hoc CSV outputs with no schema rules
- adding ML before baseline rule-based strategies are measured properly
- cloud complexity before the local workflow is trustworthy
