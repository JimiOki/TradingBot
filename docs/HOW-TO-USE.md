# Trading Lab — How To Use

A practical guide to running the trading-lab system, from first setup to generating signals.

---

## Table of Contents

1. [First-Time Setup](#1-first-time-setup)
2. [Project Structure](#2-project-structure)
3. [Configuration](#3-configuration)
4. [Running the Sanity Check](#4-running-the-sanity-check)
5. [Ingesting Market Data](#5-ingesting-market-data)
6. [Generating Signals](#6-generating-signals)
7. [Running a Backtest](#7-running-a-backtest)
8. [Using the Indicators](#8-using-the-indicators)
9. [Running Tests](#9-running-tests)
10. [Adding a New Instrument](#10-adding-a-new-instrument)
11. [Accessing from iPhone](#11-accessing-from-iphone)
12. [Common Errors](#12-common-errors)

---

## 1. First-Time Setup

### Prerequisites

- Python 3.11
- Git
- VS Code (recommended)

### Clone and activate

```bash
# Clone the repo
git clone <repo-url>
cd trading-lab

# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (WSL / bash)
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -e .
```

### Set up environment variables

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```
# IG Credentials (demo)
IG_API_KEY=your_api_key_here
IG_USERNAME=your_username_here
IG_PASSWORD=your_password_here
IG_ACCOUNT_ID=your_account_id_here
IG_ENVIRONMENT=demo

# Anthropic Claude API (for signal explanations)
GOOGLE_API_KEY=your_key_here
```

> `.env` is excluded from Git. Never commit it.

---

## 2. Project Structure

```
trading-lab/
├── config/
│   ├── instruments.yaml          ← which instruments to trade
│   ├── environments/
│   │   └── local.yaml            ← capital, risk settings, LLM config
│   └── strategies/
│       └── sma_cross.yaml        ← strategy parameters
├── data/
│   ├── raw/                      ← source data as downloaded
│   ├── curated/                  ← normalised, validated data
│   ├── signals/                  ← generated trading signals
│   │   └── explanations/         ← LLM explanations (cached)
│   ├── backtests/                ← backtest results and trade logs
│   ├── journal/                  ← trade journal (Phase 2)
│   └── risk/                     ← correlation matrices
├── src/trading_lab/
│   ├── data/                     ← ingestion and normalisation
│   ├── features/                 ← indicators (SMA, RSI, MACD, ATR)
│   ├── strategies/               ← signal generation logic
│   ├── backtesting/              ← simulation engine and metrics
│   ├── execution/                ← IG broker adapter (Phase 2)
│   └── paths.py                  ← all file paths defined here
├── scripts/
│   └── sanity_check.py           ← verify environment is working
├── tests/                        ← pytest test suite
├── docs/                         ← documentation
└── app/                          ← Streamlit dashboard (Phase 1 build)
```

---

## 3. Configuration

### Instruments (`config/instruments.yaml`)

Defines which instruments the system tracks. Current Phase 1 instruments:

| Symbol | Name | Asset Class |
|---|---|---|
| `GC=F` | Gold | Commodity |
| `CL=F` | Crude Oil (WTI) | Commodity |
| `SI=F` | Silver | Commodity |
| `HG=F` | Copper | Commodity |
| `NG=F` | Natural Gas | Commodity |

To add an instrument, see [Adding a New Instrument](#10-adding-a-new-instrument).

### Strategy (`config/strategies/sma_cross.yaml`)

```yaml
strategy: sma_cross
params:
  fast_window: 20    # Fast SMA period (days)
  slow_window: 50    # Slow SMA period (days)
backtest:
  initial_cash: 100000
  commission_bps: 5
  slippage_bps: 2
```

Adjust `fast_window` and `slow_window` to tune the strategy. Smaller fast window = more signals, more noise.

### Capital & Risk (`config/environments/local.yaml`)

```yaml
capital:
  initial_cash: 100000          # Starting capital £
  risk_per_trade_pct: 1.0       # % of capital risked per trade
  max_open_positions: 3         # Maximum simultaneous positions
  daily_loss_limit_pct: 3.0     # Daily loss limit before warnings
```

---

## 4. Running the Sanity Check

Verifies that your environment is set up correctly:

```bash
python scripts/sanity_check.py
```

Expected output:

```
Downloaded rows: 126
Columns: ['open', 'high', 'low', 'close', 'volume', 'symbol', 'source', 'adjusted']
Raw saved to: data/raw/SPY_1d_yfinance.parquet
Curated saved to: data/curated/SPY_1d_yfinance.parquet
```

If you see `ModuleNotFoundError`, your virtual environment is not activated.

---

## 5. Ingesting Market Data

Downloads daily OHLCV data for all instruments in `instruments.yaml` and saves to Parquet.

```bash
python scripts/ingest_market_data.py
```

This will:
1. Read all instruments from `config/instruments.yaml`
2. Download daily bars from yfinance for each
3. Normalise to the project schema (UTC timestamps, standard columns)
4. Save raw data to `data/raw/<symbol>_1d_yfinance.parquet`
5. Save curated data to `data/curated/<symbol>_1d_yfinance.parquet`

### From Python

```python
from trading_lab.data.models import MarketDataRequest
from trading_lab.data.yfinance_ingest import ingest_yfinance_daily

request = MarketDataRequest(
    symbol="GC=F",
    period="1y",       # yfinance period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y
    interval="1d",
    adjusted=False,    # Commodities do not use adjusted prices
)

raw_file, curated_file, df = ingest_yfinance_daily(request)
print(df.tail())
```

---

## 6. Generating Signals

Runs the SMA crossover strategy against curated data and produces a signal for each instrument.

### From Python

```python
import pandas as pd
from trading_lab.strategies.sma_cross import SmaCrossStrategy

# Load curated data
df = pd.read_parquet("data/curated/GC=F_1d_yfinance.parquet")

# Run strategy
strategy = SmaCrossStrategy(fast_window=20, slow_window=50)
signals = strategy.generate_signals(df)

# View latest signal
print(signals[["close", "fast_sma", "slow_sma", "signal"]].tail(10))
```

### Signal values

| Value | Meaning |
|---|---|
| `1` | Long signal — price trend suggests buying |
| `-1` | Short signal — price trend suggests selling |
| `0` | Flat — no clear signal, do nothing |

---

## 7. Running a Backtest

Simulates the strategy against historical data with costs applied.

```python
from trading_lab.backtesting.engine import run_backtest
from trading_lab.backtesting.models import BacktestConfig

config = BacktestConfig(
    symbol="GC=F",
    strategy_name="sma_cross",
    timeframe="1d",
    initial_cash=100_000,
    commission_bps=5,
    slippage_bps=2,
    strategy_params={"fast_window": 20, "slow_window": 50},
)

result = run_backtest(signals_df=signals, config=config)

print(f"Final equity: £{result.final_equity:,.2f}")
print(f"Total return: {result.total_return_pct:.1f}%")
```

### What the backtest does

- Lags signals by one bar (bar N signal → bar N+1 position) to prevent lookahead
- Applies commission and slippage on every position change
- Supports long, flat, and short positions
- Returns an equity curve you can inspect or plot

---

## 8. Using the Indicators

All indicator functions are pure — they take a pandas Series and return a pandas Series.

```python
from trading_lab.features.indicators import sma, rsi, atr, macd

import pandas as pd
df = pd.read_parquet("data/curated/GC=F_1d_yfinance.parquet")

# Moving averages
fast = sma(df["close"], window=20)
slow = sma(df["close"], window=50)

# RSI
rsi_values = rsi(df["close"], window=14)

# ATR (volatility)
atr_values = atr(df["high"], df["low"], df["close"], window=14)

# MACD
macd_df = macd(df["close"])  # returns DataFrame with macd_line, signal_line, histogram
```

---

## 9. Running Tests

```bash
# Run all tests with coverage
pytest

# Run a specific test file
pytest tests/test_indicators.py

# Run without coverage (faster)
pytest --no-cov

# Verbose output
pytest -v
```

Coverage report is printed after each run. Target is 80% overall, 100% on critical paths.

---

## 10. Adding a New Instrument

1. Open `config/instruments.yaml`
2. Add a new entry following the existing format:

```yaml
  - symbol: "ES=F"
    name: S&P 500 Futures
    asset_class: index
    timeframe: 1d
    source: yfinance
    session_timezone: America/New_York
    session_open: "09:30"
    session_close: "16:00"
    adjusted_prices: false
    ig_epic: null  # TODO: populate before Phase 2
```

3. Run the ingest script to download data for the new instrument:

```bash
python scripts/ingest_market_data.py
```

---

## 11. Accessing from iPhone

When the Streamlit dashboard is built (Phase 1), you can access it from your iPhone using Tailscale.

### Setup (one time)

1. Install [Tailscale](https://tailscale.com) on your Windows PC
2. Install Tailscale on your iPhone from the App Store
3. Sign in with the same account on both devices
4. Your PC will get a stable Tailscale IP (e.g. `100.x.x.x`)

### Running the dashboard

```bash
streamlit run app/main.py --server.address 0.0.0.0
```

Then open `http://100.x.x.x:8501` in Safari on your iPhone.

> The dashboard is not yet built — this will be available after Phase 1 implementation is complete.

---

## 12. Common Errors

### `ModuleNotFoundError: No module named 'trading_lab'`

Your virtual environment is not activated, or the package is not installed.

```bash
source .venv/bin/activate   # or .\.venv\Scripts\Activate.ps1 on Windows
pip install -e .
```

### `ModuleNotFoundError: No module named 'pandas'`

Same cause — wrong environment.

### `ImportError: Unable to find a usable engine` (Parquet)

pyarrow is missing.

```bash
pip install pyarrow
```

### `yfinance` returns empty data

The ticker symbol may be wrong, or the market may have been closed for the requested period. Try a shorter period first:

```python
request = MarketDataRequest(symbol="GC=F", period="1mo", interval="1d")
```

### `ValueError: signal column contains values outside {-1, 0, 1}`

The strategy returned an unexpected signal value. Check that your strategy's `generate_signals()` method only emits `-1`, `0`, or `1`.

### `.env` credentials not loading

Make sure the `.env` file is in the project root and `python-dotenv` is installed:

```python
from dotenv import load_dotenv
load_dotenv()
```
