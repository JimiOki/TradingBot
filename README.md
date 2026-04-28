# Trading Lab

A Python-based trading signal dashboard, LLM decision engine, and execution pipeline for commodities and indices. Ingests daily OHLCV data via yfinance, runs 6 technical strategies with consensus voting, enriches signals with news articles and IG client sentiment, then hands everything to an LLM that acts as the primary decision maker — outputting GO/NO_GO/UNCERTAIN with full trade parameters. Signals and LLM analysis are presented in a Streamlit dashboard, and approved trades can be executed as spreadbets on IG.

Tracked instruments (11): Gold, Crude Oil (WTI), Silver, Copper, Natural Gas, FTSE 100, S&P 500, NASDAQ 100, DAX 40, Nikkei 225, Dow Jones.

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

- **11 instruments**: 5 commodities (Gold, Crude Oil, Silver, Copper, Natural Gas) + 6 indices (FTSE 100, S&P 500, NASDAQ 100, DAX 40, Nikkei 225, Dow Jones)
- **6 strategies**: SMA crossover, MACD crossover, Bollinger Band breakout, Bollinger Band reversion, Donchian Channel, RSI mean reversion
- **Multi-strategy consensus**: all 6 strategies vote per instrument; a >50% majority determines the primary signal direction
- **LLM decision engine**: the LLM is the primary decision maker — it receives technical signals (per-strategy votes), news articles (with full body text), and IG client sentiment as evidence, then outputs GO/NO_GO/UNCERTAIN with direction (LONG/SHORT), entry level, stop loss, take profit, and risk percentage
- **LLM providers**: Gemini (default), Claude, OpenAI, DeepSeek, or stub fallback
- **News**: fetched from yfinance with full article body text via httpx + BeautifulSoup
- **IG client sentiment**: fetched from the IG live API as a contrarian/confirmation signal
- **Execution**: spreadbet order placement on IG via REST API (demo account for testing, live for real trading)
- **Dashboard**: Streamlit app showing signals, LLM analysis, IG sentiment, news, charts, and backtests

---

## Architecture

```
yfinance (OHLCV) + yfinance (news) + IG API (sentiment)
   |
   v
scripts/ingest_market_data.py  -->  data/curated/  (Parquet OHLCV)
                                          |
                                          v
scripts/run_signals.py --multi -->  data/signals/  (snapshot + news/explanation/decision cache)
                                          |
                                          v
                                  streamlit run app/main.py  (dashboard)
                                          |
                                          v
scripts/execute_trades.py       -->  IG REST API  (spreadbet orders)
```

Core library (`src/trading_lab/`) is split into focused sub-packages:

| Package | Responsibility |
|---------|---------------|
| `data/` | yfinance ingest, OHLCV transforms, news fetcher (headlines + article bodies), IG sentiment fetcher |
| `features/` | Technical indicators (SMA, RSI, MACD, ATR, Bollinger, Donchian) |
| `strategies/` | Strategy base class, loader, and 6 strategy implementations |
| `backtesting/` | Engine (no-lookahead), metrics, IS/OOS validation, reporter |
| `llm/` | LLM client ABC, Gemini/Claude/OpenAI/DeepSeek clients, stub client, prompts, explainer, decision service, factory |
| `execution/` | Broker base class, IG REST API adapter (order placement, sentiment, positions) |
| `context/` | Session checker, economic calendar fetcher, MarketContext aggregator |
| `config/` | YAML loaders for instruments and environments |

---

## Prerequisites

- Python 3.11+ (developed on 3.14.3)
- On Windows: use WSL2. The project lives at `/mnt/c/Dev/trading-lab` inside WSL.
- `GOOGLE_API_KEY` for Gemini LLM (default provider) — or `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` for alternatives. Without any key the app falls back to a stub client that returns placeholder text.
- IG Live credentials for sentiment data fetching (optional but recommended)
- IG Demo credentials for trade execution

---

## Installation

```bash
git clone <repo-url> trading-lab
cd trading-lab

python -m venv .venv
source .venv/bin/activate        # Windows WSL2: same command

pip install -e .

cp .env.example .env             # then edit .env with your credentials
```

---

## Configuration

### `config/instruments.yaml`

Defines 11 tracked instruments. Each entry specifies:
- `symbol` — yfinance ticker (e.g. `GC=F`, `^FTSE`)
- `name` — human-readable label
- `asset_class` — `commodity` or `index`
- `session_timezone`, `session_open`, `session_close` — market hours
- `ig_epic` — IG instrument epic for spreadbet order placement (DFB = undated Daily Funded Bet)
- `ig_sentiment_id` — IG market identifier for client sentiment lookup

To add an instrument, append a new entry following the same schema and re-run the ingest script.

### `config/strategies/`

Six strategy YAML configs:
- `sma_cross.yaml` — SMA crossover (primary strategy for stop/target levels)
- `macd_cross.yaml` — MACD crossover
- `bollinger_breakout.yaml` — Bollinger Band breakout
- `bollinger_reversion.yaml` — Bollinger Band reversion
- `donchian.yaml` — Donchian Channel
- `rsi_reversion.yaml` — RSI mean reversion

### `config/environments/local.yaml`

Runtime settings for local use:

```yaml
environment: demo       # demo | live — controls IG adapter endpoint

capital:
  initial_cash: 100000
  risk_per_trade_pct: 1.0
  max_open_positions: 3
  daily_loss_limit_pct: 3.0

llm:
  provider: gemini
  model: gemini-2.5-flash
  max_tokens: 8192
  enabled: true
```

### `.env`

Secrets — **never commit this file**:

```
# LLM Provider (at least one required for analysis)
GOOGLE_API_KEY=...              # Gemini (default)
ANTHROPIC_API_KEY=...           # Claude (alternative)
OPENAI_API_KEY=...              # OpenAI (alternative)

# IG Live (market data: sentiment)
IG_LIVE_API_KEY=...
IG_LIVE_USERNAME=...
IG_LIVE_PASSWORD=...
IG_LIVE_ACCOUNT_ID=...

# IG Demo (trade execution)
IG_API_KEY=...
IG_USERNAME=...
IG_PASSWORD=...
IG_ACCOUNT_ID=...
IG_DEMO=true
```

---

## How to Use It

### Step 1 — Ingest market data

```bash
python scripts/ingest_market_data.py
python scripts/ingest_market_data.py --period 1y          # custom lookback
python scripts/ingest_market_data.py --symbol GC=F        # single instrument
```

Downloads daily OHLCV bars for all configured instruments via yfinance and writes Parquet files to `data/curated/`. Each file is named `<symbol_lower>_1d_yfinance.parquet`.

Run this once to get started, then daily before generating signals.

### Step 2 — Generate signals

```bash
python scripts/run_signals.py --multi
python scripts/run_signals.py --symbol GC=F               # single instrument
python scripts/run_signals.py --strategy config/strategies/sma_cross.yaml  # single strategy mode
```

The `--multi` flag (also the default when `--strategy` is not specified) runs all 6 strategies from `config/strategies/` with consensus voting. For each instrument:

1. Every strategy generates signals independently
2. A >50% majority vote determines the consensus direction (LONG/SHORT/FLAT)
3. Stop/target levels come from the primary strategy (sma_cross)
4. News articles are fetched from yfinance (with full body text via httpx + BeautifulSoup)
5. IG client sentiment is fetched from the live API
6. The LLM receives all evidence and outputs a structured decision: GO/NO_GO/UNCERTAIN with direction, entry level, stop loss, take profit, and risk percentage

Output: `data/signals/portfolio_snapshot.parquet` plus cached news, explanations, and decisions per instrument per date.

### Step 3 — Sanity check (optional)

```bash
python scripts/sanity_check.py
```

Validates that data files are present and fresh, signals exist for all instruments, and key invariants hold.

### Step 4 — Launch the dashboard

```bash
streamlit run app/main.py
```

Opens at `http://localhost:8501`. Four pages:

#### Dashboard

The main signals overview. Summary bar shows Buy/Sell/Neutral counts based on LLM decisions. For each instrument you see:

- Current price, indicators, stop/target levels, confidence, signal age
- IG Client Sentiment bar (where available from the live API)
- LLM Analysis panel: news articles, signal explanation, decision (GO/NO_GO/UNCERTAIN with direction and order parameters)
- Instruments sorted by LLM decision (GO first)

#### Charts

Interactive candlestick chart with SMA overlays (fast and slow) and an RSI panel below. Select any instrument and date range from the sidebar.

#### Backtests

Two tabs:

**Strategy Validation** — run an in-sample backtest first to lock parameters, then an out-of-sample backtest to check real-world performance. Shows approval badge, performance degradation percentage, overfitting warning, and equity curve.

**Compare Instruments** — run the same strategy across multiple instruments simultaneously, ranked by Sharpe ratio.

#### Settings

View the current instrument and strategy configuration.

### Step 5 — Execute trades

```bash
python scripts/execute_trades.py                          # dry run — prints actions only
python scripts/execute_trades.py --execute                # live — places orders on IG
python scripts/execute_trades.py --symbol GC=F            # single instrument, dry run
python scripts/execute_trades.py --symbol GC=F --execute  # single instrument, live
```

Reads the portfolio snapshot and LLM decision cache, then places spreadbet orders on IG for every instrument where the LLM said GO. Position size is calculated from the LLM's risk percentage and stop distance. Includes a staleness guard — refuses to trade if the snapshot is more than 2 calendar days old.

### Typical daily workflow

1. Run `python scripts/ingest_market_data.py` (or schedule via cron after market close)
2. Run `python scripts/run_signals.py --multi`
3. Open the dashboard at `http://localhost:8501`, review LLM decisions
4. Run `python scripts/execute_trades.py` (dry run first to review)
5. If satisfied, run `python scripts/execute_trades.py --execute` to place orders

### Data exploration notebook

```bash
jupyter lab notebooks/02_data_exploration.ipynb
```

Interactive walkthrough of the full pipeline: data inspection, indicator calculation, strategy signals, backtesting, news headlines, LLM explanation, and LLM decision.

---

## Project Structure

```
trading-lab/
├── app/
│   ├── main.py                        # Streamlit entry point (4 pages)
│   └── pages/
│       ├── dashboard.py               # Signals, LLM analysis, IG sentiment, news
│       ├── charts.py                  # Candlestick + indicator charts
│       ├── backtests.py               # IS/OOS validation + instrument comparison
│       └── settings.py                # Config viewer
├── config/
│   ├── instruments.yaml               # 11 instruments (5 commodities + 6 indices)
│   ├── environments/
│   │   └── local.yaml                 # LLM model, capital, risk %, IG environment
│   └── strategies/
│       ├── sma_cross.yaml             # SMA crossover (primary)
│       ├── macd_cross.yaml            # MACD crossover
│       ├── bollinger_breakout.yaml    # Bollinger Band breakout
│       ├── bollinger_reversion.yaml   # Bollinger Band reversion
│       ├── donchian.yaml              # Donchian Channel
│       └── rsi_reversion.yaml         # RSI mean reversion
├── data/                              # generated, gitignored
│   ├── curated/                       # Parquet OHLCV files
│   └── signals/                       # snapshot + news/explanation/decision cache
│       ├── portfolio_snapshot.parquet
│       ├── explanations/              # LLM explanation JSON per instrument per date
│       ├── decisions/                 # LLM decision JSON per instrument per date
│       └── news/                      # News articles JSON per instrument per date
├── notebooks/
│   ├── 01_data_check.ipynb
│   └── 02_data_exploration.ipynb
├── scripts/
│   ├── ingest_market_data.py          # Download + write curated Parquet
│   ├── run_signals.py                 # Multi-strategy consensus + LLM decisions
│   ├── sanity_check.py                # Validate data freshness and invariants
│   └── execute_trades.py             # Dry-run / live spreadbet order placement
├── src/
│   └── trading_lab/
│       ├── backtesting/
│       │   ├── engine.py              # No-lookahead backtest engine
│       │   ├── metrics.py             # Sharpe, CAGR, drawdown, win rate
│       │   ├── models.py              # BacktestConfig, BacktestResult
│       │   ├── reporter.py            # Backtest report formatting
│       │   └── validation.py          # IS/OOS split, threshold checks, degradation
│       ├── config/
│       │   └── loader.py              # YAML instrument and environment loaders
│       ├── context/
│       │   ├── calendar_fetcher.py    # Economic calendar with daily cache
│       │   ├── market_context.py      # MarketContext aggregator, persist/load
│       │   └── session_checker.py     # is_session_open() with overnight support
│       ├── data/
│       │   ├── models.py              # MarketDataRequest dataclass
│       │   ├── transforms.py          # Dedup, sort, resample helpers
│       │   ├── yfinance_ingest.py     # fetch_ohlcv(), fetch_news()
│       │   ├── news_fetcher.py        # yfinance news + httpx article body scraping
│       │   └── ig_sentiment_fetcher.py # IG client sentiment via live API
│       ├── execution/
│       │   ├── broker_base.py         # BrokerAdapter ABC, OrderRequest dataclass
│       │   └── ig.py                  # IgBrokerAdapter (auth, orders, sentiment, positions)
│       ├── features/
│       │   └── indicators.py          # SMA, RSI, MACD, ATR, Bollinger, Donchian
│       ├── llm/
│       │   ├── base.py                # LLMClient ABC
│       │   ├── gemini_client.py       # GeminiClient (google-genai SDK)
│       │   ├── claude_client.py       # ClaudeClient (Anthropic SDK)
│       │   ├── openai_client.py       # OpenAIClient (OpenAI SDK)
│       │   ├── deepseek_client.py     # DeepSeekClient
│       │   ├── stub_client.py         # StubLLMClient (no API key needed)
│       │   ├── factory.py             # Provider factory (gemini/claude/openai/deepseek/stub)
│       │   ├── context.py             # SignalContext dataclass + builder
│       │   ├── prompts.py             # Prompt templates + builders
│       │   ├── explainer.py           # ExplanationService (cache-first)
│       │   └── decision.py            # DecisionService (cache-first), LLMDecision dataclass
│       ├── strategies/
│       │   ├── base.py                # Strategy ABC
│       │   ├── loader.py              # Load strategy from YAML
│       │   ├── quality.py             # Signal quality scoring
│       │   ├── sma_cross.py           # SMA crossover strategy
│       │   ├── macd_cross.py          # MACD crossover strategy
│       │   ├── bollinger.py           # Bollinger Band breakout + reversion
│       │   ├── donchian.py            # Donchian Channel strategy
│       │   └── rsi_reversion.py       # RSI mean reversion strategy
│       ├── audit.py                   # Audit event logging
│       ├── exceptions.py              # LLMError, ConfigurationError, etc.
│       ├── logging_config.py          # Structured logging setup
│       └── paths.py                   # Centralised path constants
└── tests/
    ├── conftest.py
    ├── test_audit.py
    ├── test_charts_logic.py
    ├── test_config_loader.py
    ├── test_context.py
    ├── test_dashboard_logic.py
    ├── test_engine.py
    ├── test_indicators.py
    ├── test_llm.py
    ├── test_loader.py
    ├── test_metrics.py
    ├── test_strategy.py
    ├── test_transforms.py
    └── test_validation.py
```

---

## Development

### Running tests

```bash
# All tests with coverage (80% minimum gate)
pytest

# Single file, verbose
pytest tests/test_strategy.py -v

# Fast smoke run (no coverage)
pytest -x -q --no-cov
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
4. The strategy will automatically be picked up by `run_signals.py --multi` and the Backtests page

### Code quality

```bash
ruff check .          # linting
ruff format .         # formatting
```

---

## Phase Status

### Phase 1 — Signal Dashboard (complete)

- Daily data ingestion via yfinance for 11 instruments (5 commodities + 6 indices)
- 6 technical strategies with multi-strategy consensus voting
- Backtesting engine with no-lookahead enforcement
- IS/OOS validation with overfitting detection and degradation scoring
- Streamlit dashboard: live signals, charts, IS/OOS backtests, instrument comparison

### Phase 2 — LLM Decision Engine + Trade Execution (complete)

- LLM as primary decision maker with structured GO/NO_GO/UNCERTAIN output
- 5 LLM providers supported: Gemini (default), Claude, OpenAI, DeepSeek, stub fallback
- News integration: yfinance headlines with full article body text (httpx + BeautifulSoup)
- IG client sentiment fetched from live API as contrarian/confirmation signal
- Signal explanations and decisions cached per instrument per date
- Spreadbet order execution pipeline on IG via REST API (dry-run and live modes)
- Position sizing from LLM risk percentage and stop distance

Note: spreadbet execution requires IG DFB (Daily Funded Bet) instruments. Demo accounts may only support CFD instruments for some markets.
