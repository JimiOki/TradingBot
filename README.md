# Trading Lab

A Python-based trading signal dashboard and backtesting framework for commodity futures. Ingests daily OHLCV data via yfinance, generates SMA crossover signals with an RSI filter, validates strategies through in-sample/out-of-sample backtesting, and presents signals with optional LLM explanations in a Streamlit dashboard. Designed for paper trading research; Phase 2 targets IG Demo account execution.

Tracked instruments: GC=F (Gold), CL=F (Crude Oil), SI=F (Silver), HG=F (Copper), NG=F (Natural Gas).

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [How to Use It](#how-to-use-it)
- [Project Structure](#project-structure)
- [Development](#development)
- [Phase Status](#phase-status)

---

## Overview

- **5 instruments**: Gold (GC=F), Crude Oil (CL=F), Silver (SI=F), Copper (HG=F), Natural Gas (NG=F)
- **Strategy**: SMA crossover (20/50) with RSI filter and ATR-based stop/take-profit levels
- **Backtesting**: In-sample / out-of-sample split with overfitting detection and performance degradation scoring
- **LLM layer**: Optional signal explanations and go/no-go decisions via Anthropic Claude; falls back to a stub if no API key is present
- **Market context**: Session status awareness, economic calendar integration
- **Dashboard**: 4-page Streamlit app — live signals, charts, backtests, settings

---

## Architecture

```
yfinance
   |
   v
scripts/ingest_market_data.py  -->  data/curated/  (Parquet OHLCV)
                                          |
                                          v
scripts/run_signals.py         -->  data/signals/  (signal JSON + LLM cache)
                                          |
                                          v
                                  streamlit run app/main.py
```

Core library (`src/trading_lab/`) is split into focused sub-packages:

| Package | Responsibility |
|---------|---------------|
| `data/` | yfinance ingest, OHLCV transforms, schema validation |
| `indicators/` | SMA, RSI, MACD, ATR |
| `strategies/` | Strategy loader + SMA crossover implementation |
| `backtesting/` | Engine (no-lookahead), metrics, IS/OOS validation |
| `llm/` | LLM client ABC, Claude client, stub client, prompts, explainer, decision service |
| `context/` | Session checker, economic calendar fetcher, MarketContext aggregator |
| `config/` | YAML loaders for instruments and environments |

---

## Prerequisites

- Python 3.12 or higher (developed on 3.14.3)
- On Windows: use WSL2. The project lives at `/mnt/c/Dev/trading-lab` inside WSL.
- `ANTHROPIC_API_KEY` — **optional**. Enables LLM signal explanations. Without it the app uses a stub that returns placeholder text.
- Phase 2 only: IG credentials (`IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, `IG_ACCOUNT_ID`) for IG Demo paper trading.

---

## Installation

```bash
git clone <repo-url> trading-lab
cd trading-lab

python -m venv .venv
source .venv/bin/activate        # Windows WSL2: same command

pip install -e ".[dev]"

cp .env.example .env             # then edit .env with your credentials
```

The `pip install -e ".[dev]"` installs the `trading_lab` package in editable mode plus all dev dependencies (pytest, ruff, mypy, etc.).

---

## Configuration

### `config/instruments.yaml`

Defines the 5 tracked instruments. Each entry specifies:
- `symbol` — yfinance ticker
- `name` — human-readable label
- `asset_class` — e.g. `commodity`
- `currency` — e.g. `USD`
- `session` — market open/close times (UTC) used for the session badge in the dashboard
- `pip_value` — used in position size calculations

To add an instrument, append a new entry following the same schema and re-run the ingest script.

### `config/environments/local.yaml`

Runtime settings for local use:

```yaml
llm:
  provider: claude
  model: claude-opus-4-6

trading:
  capital: 100000        # GBP
  risk_per_trade_pct: 1.0
```

### `config/strategies/sma_cross.yaml`

Strategy parameters:

```yaml
fast_window: 20
slow_window: 50
rsi_period: 14
rsi_overbought: 70
rsi_oversold: 30
commission_bps: 5
slippage_bps: 2
```

### `.env`

Secrets — **never commit this file**:

```
ANTHROPIC_API_KEY=sk-ant-...      # optional — LLM explanations
IG_API_KEY=...                    # Phase 2: IG Demo account
IG_USERNAME=...
IG_PASSWORD=...
IG_ACCOUNT_ID=...
```

---

## How to Use It

### Step 1 — Ingest market data

```bash
python scripts/ingest_market_data.py
```

Downloads daily OHLCV bars for all configured instruments via yfinance and writes Parquet files to `data/curated/`. Each file is named `<symbol_lower>_1d_yfinance.parquet`.

Run this once to get started, then daily before generating signals. You can schedule it with cron:

```cron
0 22 * * 1-5  /path/to/.venv/bin/python /mnt/c/Dev/trading-lab/scripts/ingest_market_data.py
```

### Step 2 — Generate signals

```bash
python scripts/run_signals.py
```

Loads curated data for each instrument, applies the configured strategy, and writes JSON signal files to `data/signals/`. Each file contains:

- `signal` — `1` (Buy), `-1` (Sell), or `0` (Neutral)
- `confidence` — score between 0 and 1
- `stop_price` and `tp_price` — ATR-based levels
- `timestamp` — when the signal was generated

### Step 3 — Sanity check (optional but recommended after first setup)

```bash
python scripts/sanity_check.py
```

Validates that data files are present and fresh, signals exist for all instruments, and key invariants hold (no future leakage, correct column types). Useful after first setup or when debugging unexpected dashboard behaviour.

### Step 4 — Launch the dashboard

```bash
streamlit run app/main.py
```

Opens at `http://localhost:8501`. Four pages:

#### Dashboard

The main signals overview. For each instrument you see:

- Current signal (Buy / Sell / Neutral) with a confidence badge
- Session status badge (Open / Closed) based on current UTC time
- LLM explanation of the signal (requires `ANTHROPIC_API_KEY`; shows stub text otherwise)
- LLM go/no-go recommendation (GO / NO\_GO / UNCERTAIN) with rationale
- Position sizing calculator — enter your account capital and the ATR stop distance to get recommended units and GBP risk
- Correlation warnings — if two or more instruments have the same directional signal and their 60-bar price correlation exceeds 0.7, a warning is shown above the table

#### Charts

Interactive candlestick chart with SMA overlays (fast and slow) and an RSI panel below. Select any instrument and date range from the sidebar.

#### Backtests

Two tabs:

**Strategy Validation** — run an in-sample backtest first to lock parameters, then an out-of-sample backtest to check real-world performance. The page shows:
- Approval badge: APPROVED FOR PAPER TRADING / NOT APPROVED with reason
- Performance degradation percentage (IS Sharpe vs OOS Sharpe)
- Overfitting warning if degradation exceeds 50%
- Equity curve with green IS region and orange OOS region shaded

**Compare Instruments** — run the same strategy across multiple instruments simultaneously. Results are ranked by Sharpe ratio and the best performer is highlighted. Each instrument's equity curve is available in an expandable panel.

#### Settings

View the current instrument and strategy configuration.

### Typical daily workflow

1. Run `ingest_market_data.py` (or let the cron job handle it after market close)
2. Run `run_signals.py`
3. Open the dashboard at `http://localhost:8501`
4. Check the Dashboard page for today's signals and any correlation warnings
5. For any signal you plan to act on, read the LLM explanation and go/no-go recommendation
6. Use the position sizing calculator to determine trade size (enter your account capital and the ATR stop distance shown for the instrument)
7. Before entering, confirm no correlation warning exists with another open position

### Data exploration notebook

```bash
jupyter lab notebooks/02_data_exploration.ipynb
```

The notebook covers the full pipeline interactively:

1. Raw data inspection and cleaning
2. Indicator calculation (SMA, RSI, MACD, ATR)
3. Strategy signal generation
4. IS/OOS backtesting with metrics
5. Performance degradation analysis
6. News headlines via yfinance
7. LLM signal explanation
8. LLM go/no-go decision

Useful for parameter research and understanding how signals are constructed before using the dashboard.

---

## Project Structure

```
trading-lab/
├── app/
│   ├── main.py                        # Streamlit entry point (4 pages)
│   └── pages/
│       ├── dashboard.py               # Live signals, session, LLM, position sizing
│       ├── charts.py                  # Candlestick + indicator charts
│       ├── backtests.py               # IS/OOS validation + instrument comparison
│       └── settings.py               # Config viewer
├── config/
│   ├── instruments.yaml               # 5 commodity futures
│   ├── environments/
│   │   └── local.yaml                 # LLM model, capital, risk %
│   └── strategies/
│       └── sma_cross.yaml             # SMA/RSI/ATR parameters
├── data/                              # generated, gitignored
│   ├── curated/                       # Parquet OHLCV files
│   └── signals/                       # signal JSON + LLM explanation/decision cache
├── notebooks/
│   ├── 01_strategy_dev.ipynb
│   └── 02_data_exploration.ipynb
├── scripts/
│   ├── ingest_market_data.py          # Download + write curated Parquet
│   ├── run_signals.py                 # Generate signal JSON files
│   └── sanity_check.py               # Validate data freshness and invariants
├── src/
│   └── trading_lab/
│       ├── backtesting/
│       │   ├── engine.py              # No-lookahead backtest engine
│       │   ├── metrics.py             # Sharpe, CAGR, drawdown, win rate
│       │   ├── models.py              # BacktestConfig, BacktestResult
│       │   └── validation.py         # IS/OOS split, threshold checks, degradation
│       ├── config/
│       │   └── loader.py             # YAML instrument and environment loaders
│       ├── context/
│       │   ├── calendar_fetcher.py   # Economic calendar with daily cache
│       │   ├── market_context.py     # MarketContext aggregator, persist/load
│       │   └── session_checker.py   # is_session_open() with overnight support
│       ├── data/
│       │   ├── schema.py             # OHLCV column validation
│       │   ├── transforms.py         # Dedup, sort, resample helpers
│       │   └── yfinance_ingest.py   # fetch_ohlcv(), fetch_news()
│       ├── indicators/
│       │   └── technical.py          # sma, rsi, macd, atr, sma_gap_pct
│       ├── llm/
│       │   ├── base.py               # LLMClient ABC
│       │   ├── claude_client.py      # ClaudeClient (Anthropic SDK)
│       │   ├── stub_client.py        # StubLLMClient (no API key needed)
│       │   ├── context.py            # SignalContext dataclass + builder
│       │   ├── prompts.py            # Prompt templates + builders
│       │   ├── explainer.py          # ExplanationService (cache-first)
│       │   └── decision.py           # DecisionService (cache-first, JSON parse)
│       ├── strategies/
│       │   ├── loader.py             # Load strategy from YAML
│       │   └── sma_cross.py         # SMAcrossStrategy
│       ├── exceptions.py             # LLMError, ConfigurationError, etc.
│       └── paths.py                  # Centralised path constants
└── tests/
    ├── test_indicators.py
    ├── test_strategy.py
    ├── test_engine.py
    ├── test_metrics.py
    ├── test_validation.py
    ├── test_llm.py
    ├── test_context.py
    └── test_dashboard_logic.py
```

---

## Development

### Running tests

```bash
# All tests
pytest

# With coverage gate (80% minimum)
pytest --cov=src/trading_lab --cov-fail-under=80

# Single file, verbose
pytest tests/test_strategy.py -v

# Fast smoke run (no coverage)
pytest -x -q
```

### Adding a new strategy

1. Create `config/strategies/<name>.yaml` with your parameters
2. Create `src/trading_lab/strategies/<name>.py` — implement a class with:
   ```python
   def generate_signals(self, bars: pd.DataFrame) -> pd.DataFrame:
       # Must return a DataFrame with columns:
       # signal (int: 1/-1/0), confidence (float 0-1),
       # stop_price (float), tp_price (float)
       ...
   ```
3. Register the class in `src/trading_lab/strategies/loader.py`
4. The Backtests page automatically picks up any new `*.yaml` file in `config/strategies/`

### Code quality

```bash
ruff check .          # linting
ruff format .         # formatting
mypy src/             # type checking
```

---

## Phase Status

### Phase 1 — Signal Dashboard (complete)

- Daily data ingestion via yfinance for 5 commodity futures
- SMA crossover strategy with RSI filter and ATR-based stops
- Backtesting engine with no-lookahead enforcement
- IS/OOS validation with overfitting detection and degradation scoring
- LLM signal explanations and go/no-go decisions (Claude or stub fallback)
- Market context: session status, economic calendar
- Streamlit dashboard: live signals, charts, IS/OOS backtests, instrument comparison
- Correlation warnings for co-directional positions
- Position sizing calculator

### Phase 2 — IG Demo Paper Trading (in progress)

- Automated order placement via IG REST API against an IG Demo account
- Trade journal with P&L tracking
- Risk management rules (daily loss limit, max open positions)
