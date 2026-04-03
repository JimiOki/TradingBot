# Trading Lab — Architecture and Build Plan

**Status:** Active
**Date:** 2026-04-03
**Author:** Solution Architect
**Informed by:** `docs/requirements.md`, codebase audit (2026-04-03)

---

## Table of Contents

1. [Current State Assessment](#1-current-state-assessment)
2. [Target Architecture](#2-target-architecture)
3. [LLM Integration Design](#3-llm-integration-design)
4. [Phase 1 Build Order](#4-phase-1-build-order)
5. [Phase 2 Build Order](#5-phase-2-build-order)
6. [Phase 3 Build Order](#6-phase-3-build-order)
7. [Interface Definitions](#7-interface-definitions)
8. [Configuration Design](#8-configuration-design)
9. [Testing Strategy](#9-testing-strategy)
10. [Risks and Mitigations](#10-risks-and-mitigations)

---

## 1. Current State Assessment

### What Exists

The codebase has a functional skeleton for data ingestion, signal generation, and backtesting. The module boundaries are correct and the directory structure maps cleanly to the intended architecture. The following components work:

- `data/yfinance_ingest.py` — downloads and persists raw and curated Parquet files for a given `MarketDataRequest`
- `data/transforms.py` — normalises yfinance output into a column-stable schema (missing `adjusted` column — see gaps)
- `strategies/sma_cross.py` — computes fast/slow SMA crossover and emits `signal` column with values `{-1, 0, 1}`
- `backtesting/engine.py` — runs a long/flat backtest over a signals DataFrame
- `execution/ig.py` — stub that raises `NotImplementedError`; correct placeholder
- `paths.py` — single source of truth for data directory layout

### Gaps That Must Be Fixed Before New Work Starts

These are not cosmetic. Each one will cause incorrect behaviour or blocked tests if left unresolved.

**GAP-001 — BacktestConfig is incomplete**
`BacktestConfig` has `initial_cash`, `commission_bps`, and `slippage_bps`. It is missing `symbol`, `timeframe`, `start_date`, `end_date`, `strategy_name`, and `strategy_params`. A backtest result written to disk today cannot be reproduced from the config alone. Fix this before writing a single new backtest.

**GAP-002 — No tests directory**
The repository has no `tests/` directory and no test runner configuration in `pyproject.toml`. This is the largest gap. All downstream work assumes tests exist. Create `tests/` and configure `pytest` as the first action in Phase 1.

**GAP-003 — Signal contract not enforced**
`Strategy.generate_signals` is an abstract method with no post-call validation. A subclass can return a DataFrame with no `signal` column, or with values outside `{-1, 0, 1}`, and nothing will catch it until a downstream caller crashes. The base class must validate its own return contract.

**GAP-004 — Engine clips signal=-1 to 0 (semantics mismatch)**
`engine.py` calls `.clip(lower=0)` on the signal column, silently converting short signals to flat. `SmaCrossStrategy` emits `-1` correctly. The engine must be updated to support long, flat, and short positions. IG spreadbetting supports shorts on all instruments; there is no reason to restrict the engine. This must be fixed before any backtest result involving a sell signal is taken seriously.

**GAP-005 — `adjusted` flag absent from curated Parquet**
`MarketDataRequest` carries `adjusted=True/False`. `normalize_yfinance_daily` does not write this to the curated output. Any strategy that reads a curated file has no way to verify whether prices are adjusted. Add `adjusted` as a boolean column to the curated schema.

**GAP-006 — `backtrader` installed but unused**
`pyproject.toml` lists `backtrader` as a dependency alongside the custom engine. Decision: **remove `backtrader`**. The custom engine is simpler, fully under project control, and has no hidden assumptions about data shape. Adding a second framework creates ambiguity about which is authoritative. Remove it.

**GAP-007 — No IG epic mapping in `instruments.yaml`**
The current `instruments.yaml` contains only SPY (wrong instrument for Phase 1) with no `ig_epic` field. This must be updated to the five Phase 1 commodities with epics added before Phase 2.

**GAP-008 — No structured logging**
Scripts produce no log output. A failed ingest run leaves no trace. Structured logging using Python's `logging` module must be added to all scripts and the ingest pipeline before Phase 1 is complete.

**GAP-009 — `instruments.yaml` contains wrong instruments**
Current watchlist is SPY (an ETF). Phase 1 instruments are GC=F (Gold), CL=F (Crude Oil), SI=F (Silver), HG=F (Copper), NG=F (Natural Gas). This must be corrected before any useful signal generation can occur.

**GAP-010 — `polars` and `scikit-learn` in dependencies without use**
`pyproject.toml` lists `polars` and `scikit-learn`. Neither is used. `polars` creates confusion about which DataFrame library the project uses (it is `pandas`). `scikit-learn` implies ML capability that is explicitly out of scope for Phase 1-2. Remove both.

---

## 2. Target Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        EXTERNAL SOURCES                         │
│   yfinance (research data)    IG REST/Streaming API (live)      │
└──────────────┬────────────────────────────┬────────────────────┘
               │                            │
               ▼                            ▼
┌──────────────────────────┐   ┌────────────────────────────────┐
│   DATA LAYER             │   │   EXECUTION LAYER              │
│                          │   │                                │
│  yfinance_ingest.py      │   │  ig.py (IgBrokerAdapter)       │
│  transforms.py           │   │  broker_base.py (ABC)          │
│  models.py (schemas)     │   │  ig_streaming.py (Phase 2)     │
│                          │   │                                │
│  data/raw/               │   │  data/live/  (Phase 2)         │
│  data/curated/           │   │                                │
└──────────────┬───────────┘   └────────────────────────────────┘
               │                            ▲
               ▼                            │ (order)
┌──────────────────────────┐                │
│   FEATURES LAYER          │   ┌───────────────────────────────┐
│                          │   │   SIGNAL APPROVAL LAYER        │
│  indicators.py           │   │   (Phase 2)                    │
│  (sma, rsi, macd)        │   │                                │
│                          │   │  signal_state.py               │
└──────────────┬───────────┘   │  position_sizer.py             │
               │               │  data/journal/signals.parquet  │
               ▼               └───────────────────────────────┘
┌──────────────────────────┐                ▲
│   STRATEGY LAYER         │                │
│                          │   ┌────────────┴──────────────────┐
│  base.py (Strategy ABC)  │   │   LLM EXPLANATION LAYER        │
│  sma_cross.py            ├──►│                                │
│  strategy_loader.py      │   │  explainer.py                  │
│                          │   │  llm_client.py (provider ABC)  │
└──────────────┬───────────┘   │  claude_client.py              │
               │               │  data/explanations/ (cache)    │
               ▼               └───────────────────────────────┘
┌──────────────────────────┐
│   BACKTESTING LAYER      │
│                          │
│  engine.py               │
│  models.py (BacktestConfig, BacktestResult)
│  metrics.py              │
│  reporter.py             │
│                          │
│  data/backtests/         │
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│   APPLICATION LAYER       │
│                          │
│  app/main.py (Streamlit) │
│  app/pages/dashboard.py  │
│  app/pages/charts.py     │
│  app/pages/backtests.py  │
│  app/pages/settings.py   │
│  app/pages/journal.py    │   ← Phase 2
│                          │
└──────────────────────────┘
               │
               ▼
┌──────────────────────────┐
│   CONFIG LAYER            │
│                          │
│  config/instruments.yaml │
│  config/strategies/*.yaml│
│  config/environments/*.yaml
│  .env (secrets only)     │
└──────────────────────────┘
```

### Module Boundaries

**Data layer** (`src/trading_lab/data/`) owns everything up to and including validated curated Parquet files. It knows nothing about strategies, backtests, or the broker.

**Features layer** (`src/trading_lab/features/`) provides pure indicator functions (SMA, RSI, MACD) that operate on `pd.Series`. No DataFrame I/O, no strategy logic. Strategies call these; the features layer does not call strategies.

**Strategy layer** (`src/trading_lab/strategies/`) owns signal generation. A strategy takes a curated bars DataFrame, calls feature functions, and returns an annotated signals DataFrame. Strategies are pure functions of data — no I/O, no external calls.

**Backtesting layer** (`src/trading_lab/backtesting/`) owns simulation, metrics, and result persistence. It takes signals DataFrames and `BacktestConfig` objects. It does not know about the broker.

**LLM layer** (`src/trading_lab/llm/`) owns explanation generation, caching, and provider abstraction. It reads signal rows and returns plain-English text. It does not write signals or trigger trades.

**Execution layer** (`src/trading_lab/execution/`) owns all broker communication. In Phase 1 this is a stub. In Phase 2 it authenticates and places paper orders. It knows nothing about signal generation.

**Application layer** (`app/`) owns the Streamlit dashboard. It orchestrates all other layers but contains no business logic itself. It reads from the data directory and calls package functions.

### Data Flow — Phase 1 (Research)

```
instruments.yaml
    → ingest script
        → yfinance API
            → data/raw/<symbol>_1d_yfinance.parquet   (source-faithful)
            → data/curated/<symbol>_1d_yfinance.parquet (validated schema)
                → SmaCrossStrategy.generate_signals()
                    → signals DataFrame (in memory)
                        → LLM explainer
                            → data/explanations/<symbol>_<date>.json (cached)
                        → backtest engine
                            → data/backtests/<symbol>_1d_sma_cross_<ts>_summary.json
                            → data/backtests/<symbol>_1d_sma_cross_<ts>_trades.parquet
                        → Streamlit dashboard (reads from disk)
```

### Data Flow — Phase 2 (Paper Trading)

```
(Phase 1 data flow, plus:)

signals DataFrame
    → signal state manager
        → data/journal/signals.parquet (pending signals persisted)
            → [User: Approve]
                → position sizer
                    → [User: Confirm with size]
                        → IgBrokerAdapter.place_order() [demo]
                            → data/journal/trades.parquet (entry recorded)

IG Streaming API
    → data/live/<symbol>_1d_ig_streaming.parquet
        → dashboard positions panel (unrealised P&L)
            → [Position closed on IG platform]
                → IgBrokerAdapter.get_closed_positions()
                    → data/journal/trades.parquet (exit recorded)
```

---

## 3. LLM Integration Design

### Where in the Call Chain

The LLM sits between signal generation and display. It is called once per new signal, its output is cached to disk, and the dashboard reads from the cache. The LLM is never in the critical path for data refresh, backtesting, or order placement.

```
signals DataFrame
    → [signal != 0 AND signal is new (position_change != 0)]
        → ExplanationService.get_or_generate(signal_row)
            → cache lookup: data/explanations/<symbol>_<date>_<signal>.json
                → [cache hit] return cached text
                → [cache miss] LLMClient.generate_explanation(prompt)
                    → write to cache
                    → return text
```

### Interface Design

**`LLMClient` (abstract base)**

```python
# src/trading_lab/llm/base.py
class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send a prompt and return the completion text."""
```

**`ClaudeClient` (concrete implementation)**

```python
# src/trading_lab/llm/claude_client.py
class ClaudeClient(LLMClient):
    def __init__(self, model: str = "claude-opus-4-6", max_tokens: int = 500):
        ...
    def complete(self, prompt: str) -> str:
        # Calls Anthropic API using ANTHROPIC_API_KEY from env
        ...
```

**`ExplanationService`**

```python
# src/trading_lab/llm/explainer.py
@dataclass(frozen=True)
class SignalExplanation:
    symbol: str
    signal_date: date
    signal: int              # 1 or -1
    explanation: str
    generated_at: datetime
    model: str
    cached: bool

class ExplanationService:
    def __init__(self, client: LLMClient, cache_dir: Path):
        ...
    def get_or_generate(self, signal_row: dict) -> SignalExplanation:
        """Return cached explanation or generate and cache a new one."""
```

### Prompt Design

The prompt is constructed from the signal row context. It is explicit about the instrument, the signal direction, and the indicator values that triggered it. The prompt is deterministic given the same inputs.

```
You are a quantitative trading analyst. Provide a concise explanation (3-4 sentences)
of the following trading signal for a human trader reviewing it on a dashboard.
Be factual and technical. Do not give investment advice or price predictions.

Instrument: {name} ({symbol})
Signal date: {date}
Signal: {"BUY (long)" if signal == 1 else "SELL (short)"}
Close price: {close}
Fast SMA ({fast_window}): {fast_sma:.2f}
Slow SMA ({slow_window}): {slow_sma:.2f}
RSI (14): {rsi:.1f}

Explain what technical conditions triggered this signal and what they indicate
about the current trend. Note any factors that would reduce or increase confidence
in this signal (e.g. RSI level, signal freshness, recent volatility).
```

### Caching Strategy

Cache location: `data/explanations/`
Cache filename: `{symbol}_{date}_{signal}.json` (e.g. `GC=F_2026-04-03_1.json`)
Cache format: JSON matching the `SignalExplanation` schema
Cache invalidation: never (signal explanations are historical facts; if the signal for a given date does not change, the explanation does not change)
Regeneration: if the cache file is manually deleted, the next dashboard load regenerates it

The cache key encodes symbol, date, and signal value. If a signal changes direction intraday (not expected on daily bars), the new direction generates a new cache entry without overwriting the old one.

### Provider Abstraction

The `LLMClient` ABC allows swapping providers. The active provider is selected at startup:

```yaml
# config/environments/local.yaml
llm:
  provider: claude          # or: openai, stub
  model: claude-opus-4-6
  max_tokens: 500
  timeout_seconds: 30
```

A `StubLLMClient` returns a fixed string for test environments without making API calls. This is the default when `ANTHROPIC_API_KEY` is absent.

---

## 4. Phase 1 Build Order

Phase 1 closes when all listed steps are complete, all named tests pass, and the Streamlit dashboard renders signal data for all five commodity instruments from local Parquet files.

### Step 0 — Fix Gaps Before Writing New Code (1-2 days)

These must be done in order because later steps depend on them.

**0.1 — Remove unused dependencies**
Remove `backtrader`, `polars`, and `scikit-learn` from `pyproject.toml`. Add `streamlit`, `plotly`, `anthropic`, `pytest`, `pytest-cov` to the appropriate dependency groups. Add `streamlit` to main deps; put `pytest`, `pytest-cov` under `[project.optional-dependencies]` as `dev`.

**0.2 — Create test infrastructure**
Create `tests/__init__.py`, `tests/conftest.py`, and `tests/data/`, `tests/strategies/`, `tests/backtesting/`, `tests/llm/` subdirectories. Add `pytest` configuration to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--tb=short"
```

**0.3 — Fix BacktestConfig**
Add `symbol: str`, `timeframe: str`, `start_date: date`, `end_date: date`, `strategy_name: str`, `strategy_params: dict` to `BacktestConfig`. Add `__post_init__` validation that `start_date < end_date`.

**0.4 — Fix backtest engine (short support)**
Remove `.clip(lower=0)` from `engine.py`. Replace `run_long_flat_backtest` with `run_backtest` that handles `position = signal.shift(1)` without clipping. The short side inverts returns: `gross_return = position * market_return` already handles this correctly once clipping is removed. Add module-level docstring stating: "Execution is assumed at the close of the bar following signal generation (next-bar close). This is an approximation; next-bar open is not available from yfinance daily OHLCV." Rename the function to `run_backtest` so callers know it is not long/flat-only.

**0.5 — Fix curated schema (adjusted flag)**
Add `adjusted: bool` column to `normalize_yfinance_daily`. Populate it from `MarketDataRequest.adjusted` (requires threading it through `ingest_yfinance_daily`). Update the curated schema validation to require this column.

**0.6 — Fix instruments.yaml**
Replace SPY with the five Phase 1 commodities. Add `name` and `asset_class` fields. Leave `ig_epic` as a comment placeholder (`# required for Phase 2`):

```yaml
instruments:
  - symbol: "GC=F"
    name: Gold Futures
    asset_class: commodity
    timeframe: 1d
    source: yfinance
    session_timezone: America/New_York
    adjusted_prices: true
    # ig_epic: CS.D.GOLD.CFD.IP   # required for Phase 2

  - symbol: "CL=F"
    name: Crude Oil WTI Futures
    asset_class: commodity
    timeframe: 1d
    source: yfinance
    session_timezone: America/New_York
    adjusted_prices: true

  - symbol: "SI=F"
    name: Silver Futures
    asset_class: commodity
    timeframe: 1d
    source: yfinance
    session_timezone: America/New_York
    adjusted_prices: true

  - symbol: "HG=F"
    name: Copper Futures
    asset_class: commodity
    timeframe: 1d
    source: yfinance
    session_timezone: America/New_York
    adjusted_prices: true

  - symbol: "NG=F"
    name: Natural Gas Futures
    asset_class: commodity
    timeframe: 1d
    source: yfinance
    session_timezone: America/New_York
    adjusted_prices: true
```

**0.7 — Add structured logging**
Create `src/trading_lab/logging_config.py` that configures a root logger with a `RotatingFileHandler` to `logs/trading_lab.log` and a `StreamHandler` to stdout. Both emit the format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`. All scripts call `setup_logging()` before doing anything else. Create `logs/` directory and add `logs/*.log` to `.gitignore`.

---

### Step 1 — Data Layer Hardening (2-3 days)

**1.1 — Config loader module**
Create `src/trading_lab/config/loader.py`. Implement `load_instruments()` that reads `instruments.yaml`, validates each entry against a defined schema (`symbol`, `name`, `asset_class`, `timeframe`, `source`, `session_timezone`, `adjusted_prices` all required), raises `ConfigValidationError` on any missing or invalid field. `asset_class` must be one of `{commodity, equity, index, fx}`. `timeframe` must be one of `{1d, 1wk}`. `session_timezone` must be a valid IANA identifier (use `zoneinfo.available_timezones()`).

**1.2 — Data validation in ingest**
Add `validate_curated_dataframe(df: pd.DataFrame)` to `data/transforms.py`. It checks: all required columns present, `timestamp` is UTC-aware, no null `close` values, no `close <= 0`. Called by `ingest_yfinance_daily` before writing the curated file. Add a `DataQualityError` custom exception in `src/trading_lab/exceptions.py`.

**1.3 — Ingest script**
Create `scripts/ingest_market_data.py`. Reads all instruments from `config/instruments.yaml`. For each instrument: calls `ingest_yfinance_daily`, logs success at INFO or failure at ERROR, continues on failure. Exits with code 1 if any instrument failed. Add `--symbol` flag to allow single-instrument refresh.

**1.4 — Multi-timeframe support**
Add interval validation to `MarketDataRequest.__post_init__`: permitted values are `{"1d", "1wk"}`. Any other value raises `ValueError` at construction time, not at download time.

**1.5 — Tests**
```
tests/data/test_transforms.py
  - test_normalize_produces_expected_columns
  - test_timestamp_is_utc_aware
  - test_null_close_raises
  - test_adjusted_column_matches_request
  - test_negative_close_is_rejected

tests/data/test_models.py
  - test_invalid_interval_raises_at_construction

tests/config/test_loader.py
  - test_load_instruments_happy_path
  - test_missing_field_raises_config_validation_error
  - test_invalid_asset_class_raises
  - test_invalid_timezone_raises
```

---

### Step 2 — Strategy Layer (2 days)

**2.1 — Features module**
Create `src/trading_lab/features/indicators.py`. Implement:
- `sma(prices: pd.Series, window: int) -> pd.Series`
- `rsi(prices: pd.Series, period: int = 14) -> pd.Series`
- `macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame` (columns: `macd_line`, `signal_line`, `histogram`)

Each function raises `ValueError` if the input series is shorter than the minimum required length. None modify the input in place.

**2.2 — Strategy base class validation**
Wrap the abstract `generate_signals` call in the base class. Add a `_validate_signals(df: pd.DataFrame)` method that checks: `signal` column exists, all values are in `{-1, 0, 1}`. Call it from a concrete `generate_signals` wrapper that subclasses override via `_compute_signals`. This enforces the contract at the boundary without requiring every subclass to repeat validation.

**2.3 — SmaCrossStrategy with RSI filter**
Update `SmaCrossStrategy` to call `indicators.sma` and `indicators.rsi` from the features module. Add constructor parameters: `rsi_period=14`, `rsi_overbought=70`, `rsi_oversold=30`, `rsi_filter_enabled=True`. When filter is enabled: suppress `signal=1` where RSI >= `rsi_overbought`; suppress `signal=-1` where RSI <= `rsi_oversold`. Use the features module, not inline rolling calculations.

**2.4 — Strategy loader**
Create `src/trading_lab/strategies/loader.py`. Implement `load_strategy(config_path: Path) -> Strategy` that reads a strategy YAML, identifies the strategy class by the `strategy` key, instantiates it with `params`, raises `ConfigValidationError` on missing required params.

**2.5 — Signal runner**
Create `src/trading_lab/signals/runner.py`. Implement `run_signals_for_all_instruments(instruments: list[dict], strategy: Strategy) -> pd.DataFrame` that returns a portfolio-level signal summary DataFrame with columns: `symbol`, `name`, `timestamp_of_last_bar`, `signal`, `close`, `fast_sma`, `slow_sma`, `rsi`, `status`. If a curated file is missing, that instrument appears with `signal=None` and `status="data_missing"`.

**2.6 — Tests**
```
tests/strategies/test_base.py
  - test_missing_signal_column_raises

tests/strategies/test_sma_cross.py
  - test_fast_window_gte_slow_raises
  - test_warmup_period_is_zero
  - test_crossover_detected_correctly (synthetic data, known crossover bar)
  - test_sell_signal_emitted_as_negative_one
  - test_rsi_filter_suppresses_overbought_buy
  - test_rsi_filter_suppresses_oversold_sell
  - test_rsi_filter_disabled_allows_overbought_buy

tests/features/test_indicators.py
  - test_sma_warmup_count
  - test_rsi_bounds
  - test_rsi_short_series_raises
  - test_macd_columns_present
```

---

### Step 3 — Backtesting Layer (2 days)

**3.1 — BacktestConfig finalised**
(Already done in Step 0.3.) Add `risk_free_rate: float = 0.0` to `BacktestConfig`. Add named constants to `engine.py`: `ANNUAL_TRADING_DAYS_DAILY = 252`, `ANNUAL_TRADING_DAYS_WEEKLY = 52`. Map them from `BacktestConfig.timeframe`.

**3.2 — Metrics module**
Create `src/trading_lab/backtesting/metrics.py`. Implement `compute_metrics(equity_curve: pd.Series, trades: pd.DataFrame, config: BacktestConfig) -> BacktestResult`. Returns a `BacktestResult` dataclass with: `total_return`, `cagr`, `sharpe_ratio`, `max_drawdown`, `max_drawdown_duration`, `win_rate`, `num_trades`, `avg_trade_return`, `profit_factor`. Any metric undefined by insufficient trades is `None`, not zero or NaN.

**3.3 — Trade log extraction**
The engine must extract a trade log from the position series: one row per round-trip trade with `entry_timestamp`, `exit_timestamp`, `entry_price`, `exit_price`, `direction`, `gross_return`, `cost`, `net_return`. Entry = `position_change != 0` when position becomes non-zero. Exit = `position_change != 0` when position becomes zero or reverses.

**3.4 — Result persistence**
Create `src/trading_lab/backtesting/reporter.py`. Implement `save_backtest_result(result: BacktestResult, config: BacktestConfig, trade_log: pd.DataFrame, output_dir: Path)`. Filename convention: `{symbol}_{timeframe}_{strategy_name}_{utc_ts}_summary.json` and `..._trades.parquet`. If a file with the same name exists, append `_1`, `_2`, etc. Write summary JSON only after all metrics compute successfully (write to a temp file, then rename).

**3.5 — Tests**
```
tests/backtesting/test_engine.py
  - test_no_lookahead (signal on bar 5, position on bar 6)
  - test_short_position_profits_on_falling_market
  - test_zero_cost_equals_market_return
  - test_higher_turnover_incurs_higher_cost

tests/backtesting/test_metrics.py
  - test_sharpe_against_hand_calculated_reference
  - test_max_drawdown_against_hand_calculated_reference
  - test_insufficient_trades_returns_none
  - test_daily_vs_weekly_annualisation_constant
```

---

### Step 4 — LLM Explanation Layer (1-2 days)

**4.1 — Custom exceptions**
Add `LLMError`, `LLMTimeoutError` to `src/trading_lab/exceptions.py`.

**4.2 — LLM module**
Create `src/trading_lab/llm/` with `__init__.py`, `base.py`, `claude_client.py`, `stub_client.py`, `explainer.py`. Implement per interface definitions in Section 7. `ClaudeClient` reads `ANTHROPIC_API_KEY` from environment via `python-dotenv`. Raises `LLMError` on API failure; raises `LLMTimeoutError` on timeout (configurable, default 30s). `StubLLMClient` returns a fixed string `"[Stub explanation — LLM not configured]"`.

**4.3 — Cache**
`ExplanationService` checks `data/explanations/<symbol>_<date>_<signal>.json` before calling the LLM. Cache hit: return cached `SignalExplanation` with `cached=True`. Cache miss: call LLM, write JSON, return with `cached=False`. The cache directory is created if absent.

**4.4 — Config-driven provider selection**
`local.yaml` `llm.provider` selects the client class. If `ANTHROPIC_API_KEY` is absent and provider is `claude`, fall back to `stub` and log a WARNING.

**4.5 — Tests**
```
tests/llm/test_explainer.py
  - test_cache_hit_does_not_call_llm
  - test_cache_miss_calls_llm_and_writes_cache
  - test_stub_client_returns_fixed_string
  - test_missing_api_key_falls_back_to_stub
```

---

### Step 5 — Streamlit Dashboard (3-5 days)

**5.1 — App structure**
Create `app/main.py` (entry point), `app/pages/dashboard.py`, `app/pages/charts.py`, `app/pages/backtests.py`, `app/pages/settings.py`. Use Streamlit's multi-page app convention (`pages/` directory).

**5.2 — Dashboard page**
Signal table showing all instruments with `Symbol`, `Name`, `Last Price`, `Change %`, `Signal` (coloured), `Fast SMA`, `Slow SMA`, `RSI`, `Last Updated`. Portfolio summary panel: counts of Buy/Sell/Neutral/Missing. Refresh button that calls `ingest_market_data` and recomputes signals. Last refresh timestamp in sidebar. Signals are recomputed on refresh only, not on every page load. LLM explanation shown below each non-neutral signal row.

**5.3 — Charts page**
Instrument dropdown (from `instruments.yaml`). Timeframe selector (Daily/Weekly). Date range selector (3m/6m/1y/2y/All). Interactive Plotly candlestick chart. SMA overlay with configurable windows. RSI and MACD in subplots. Signal event markers overlaid on price chart (triangles on entry bars).

**5.4 — Backtests page**
Form inputs for symbol, timeframe, date range, strategy, parameters. "Run Backtest" button. Results: metrics card, equity curve chart, trade log table. Previous results loadable from `data/backtests/`.

**5.5 — Settings page**
Display instruments from `instruments.yaml` and active strategy parameters. Allow edits written back to YAML. No credential fields exposed.

**5.6 — Graceful degradation**
Dashboard renders with `Data Missing` states when no curated files exist. No network calls on page load. Stale data warning if last bar is more than 2 trading days old.

---

### Step 6 — Phase 1 Close (1 day)

- Run full test suite; all tests pass
- Run `scripts/ingest_market_data.py` against all five commodity instruments; verify curated files on disk
- Open dashboard; verify signal table renders with real data
- Run one backtest from the UI; verify summary JSON and trades Parquet written to `data/backtests/`
- Verify LLM explanation renders for at least one non-neutral signal
- Record decision on execution price assumption (next-bar close) in `engine.py` docstring
- Record decision to remove `backtrader` in `docs/requirements.md` (GAP-007 resolved)

---

## 5. Phase 2 Build Order

Phase 2 starts only after all Phase 1 acceptance criteria pass. No Phase 2 code merges until Phase 1 is stable.

### Prerequisites

- All Phase 1 tests passing
- IG demo account credentials obtained and in `.env`
- IG epic codes identified for all five commodity instruments and added to `instruments.yaml`
- `IG_ENVIRONMENT` set to `demo` in `.env`

---

### Step 1 — IG API Authentication (2 days)

**1.1 — Environment config**
Add to `.env.example` (not `.env`): `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, `IG_ACCOUNT_ID`, `IG_ENVIRONMENT`. Add to `config/environments/local.yaml`: `ig.retry_attempts: 3`, `ig.retry_backoff_base: 2`, `ig.timeout_seconds: 30`.

**1.2 — IG adapter implementation**
Implement `IgBrokerAdapter` in `execution/ig.py`: `connect()`, `place_order()`, `get_positions()`, `close_position()`. Implement session token management and refresh. Add `IGAPIError`, `IGConnectionError`, `AuthenticationError`, `EnvironmentMismatchError` to `exceptions.py`. All API calls log request and response (credentials redacted) to `logs/orders.log` via a dedicated logger.

**1.3 — Environment isolation guard**
`IgBrokerAdapter` reads `IG_ENVIRONMENT` at init. `place_order` raises `EnvironmentMismatchError` if the adapter's environment does not match the endpoint being called. This cannot be overridden at call time.

**1.4 — Tests**
Use a `responses` or `httpretty` library to mock HTTP calls. Test authentication success/failure, retry behaviour, 429 rate limit handling, environment mismatch guard.

---

### Step 2 — Signal State Management (2 days)

**2.1 — Signal lifecycle model**
Create `src/trading_lab/signals/state.py`. Define `SignalStatus` enum: `pending`, `approved`, `rejected`, `expired`. Define `SignalRecord` dataclass matching the schema in Section 7. Implement `SignalStore` backed by `data/journal/signals.parquet`: `add_signal()`, `get_pending()`, `update_status()`, `expire_stale()` (moves signals older than `signal_expiry_hours` to `expired`).

**2.2 — Supersession logic**
When a new signal fires for an instrument that already has a `pending` signal, the existing pending signal transitions to `expired` before the new one is written.

**2.3 — Signal runner integration**
Update `signals/runner.py` to call `SignalStore.add_signal()` for any new signal where `position_change != 0`. Signals where `position_change == 0` (no change from prior bar) are not added as new pending signals.

---

### Step 3 — Position Sizer (1 day)

**3.1**
Create `src/trading_lab/execution/position_sizer.py`. Implement `calculate_position_size(account_balance, risk_pct, entry_price, stop_loss_price) -> int` (rounds down to nearest whole contract). `risk_pct` comes from `config/environments/local.yaml` `risk.risk_per_trade_pct`, defaulting to 1%. If the strategy does not emit a stop level, fall back to `entry_price * (1 - risk.default_stop_pct)`.

---

### Step 4 — Signal Approval and Order Placement (3 days)

**4.1 — Dashboard approval UI**
Add Approve and Reject buttons to signal rows with `status=pending`. Approve opens a confirmation modal (Plotly/Streamlit dialog) showing instrument, direction, price, suggested size, stop loss, risk/reward. User may override size. Confirm triggers `IgBrokerAdapter.place_order()`. Reject sets status to `rejected`. No double-submit: disable button while order is in flight using `st.session_state`.

**4.2 — Order submission**
On confirm: call `IgBrokerAdapter.place_order(OrderRequest(...))`. On IG success: update signal record to `approved`, store `deal_id`, write entry row to `data/journal/trades.parquet`. On IG failure: update signal to `rejected`, surface error message in dashboard.

**4.3 — Environment banner**
Persistent sidebar banner: `DEMO ACCOUNT` (blue) or `LIVE ACCOUNT — REAL MONEY` (red). Rendered on all pages.

---

### Step 5 — IG Streaming and Position Monitoring (2-3 days)

**5.1 — Streaming adapter**
Create `src/trading_lab/execution/ig_streaming.py` wrapping the IG Streaming API (Lightstreamer). Subscribe to OHLC candles for watchlist instruments. Write updates to `data/live/<symbol>_1d_ig_streaming.parquet`. Reconnection logic: up to 5 attempts with exponential backoff. After 5 failures: surface `CONNECTION LOST` alert in dashboard.

**5.2 — Positions panel**
Add positions panel to Dashboard page. Calls `IgBrokerAdapter.get_positions()` on each manual refresh. Shows: instrument, direction, size, open price, current price (from streaming if connected, else last bar), unrealised P&L, stop level. Cache last successful response; display staleness indicator on stale data.

**5.3 — Exit detection**
On each positions refresh, compare current open positions against positions cached from prior refresh. Positions that have disappeared are closed. Retrieve deal details from IG REST API and write exit row to `data/journal/trades.parquet`.

---

### Step 6 — Trade Journal and Signal History UI (1-2 days)

**6.1 — Journal page**
Create `app/pages/journal.py` with two tabs: Trades and Signals. Trades tab: filterable table + running P&L curve. Signals tab: filterable table + approve/reject rate summary metric.

**6.2 — Tests**
Test signal lifecycle transitions. Test that a second pending signal supersedes the first. Test that an expired signal cannot be approved. Test position sizer formula against hand-calculated reference.

---

### Step 7 — Phase 2 Close

- 30 days of paper trading on demo account with no critical defects
- All Phase 2 tests pass
- Order audit log (`logs/orders.log`) reviewed for completeness
- Kill switch tested on demo account (close all demo positions with one action)
- `docs/risk-review.md` created and signed off

---

## 6. Phase 3 Build Order

Phase 3 starts only after `docs/risk-review.md` is completed and signed off.

### Step 1 — Risk Controls (2 days)

**1.1 — Pre-submission risk check**
Create `src/trading_lab/execution/risk_checks.py`. Implement `check_pre_submission(order, account_state, config) -> RiskCheckResult`. Checks run in order: daily loss limit, total exposure cap, per-instrument duplicate position, stop loss presence. Each failed check returns a descriptive reason. `IgBrokerAdapter.place_order()` calls this before making the API call; a failed check raises `RiskCheckError`.

**1.2 — Risk config**
Add to `config/environments/local.yaml`:
```yaml
risk:
  daily_loss_limit_pct: 3.0
  max_exposure_pct: 25.0
  max_open_positions: 5
  risk_per_trade_pct: 1.0
  default_stop_pct: 0.02
```
All values validated at startup. `daily_loss_limit_pct > 50` is rejected as unsafe.

---

### Step 2 — Kill Switch (1 day)

**2.1**
Create `src/trading_lab/execution/kill_switch.py`. `activate()` iterates all open positions, calls `close_position()` for each, logs each closure to `logs/orders.log`. Sets application-level `halted` flag in `st.session_state` that prevents `place_order()` from being called. Cleared only by restarting the application.

**2.2 — Dashboard UI**
Kill Switch button visible on all pages when `IG_ENVIRONMENT=live`. Opens confirmation modal. After activation, displays countdown and per-position closure status. All Approve buttons disabled while `halted=True`.

---

### Step 3 — Credential Switch to Live (0.5 days)

The adapter already uses `IG_ENVIRONMENT` to select the endpoint. The only action required is updating `.env` to `IG_ENVIRONMENT=live` and providing live credentials. Test that the startup sequence logs a WARNING at the first line when live. Test that the environment banner renders in red.

---

### Step 4 — Indices Expansion (1 day)

Add index instruments to `instruments.yaml` with `asset_class: index` and their IG epics. Signal table groups instruments by `asset_class`. No code changes required if the data layer and strategy layer are correctly built.

---

### Step 5 — Actual vs Backtest Comparison (1-2 days)

Implement `src/trading_lab/reporting/performance_comparison.py`. For instruments with at least 5 completed live trades: compute actual win rate, average return, Sharpe vs the corresponding backtest result. Display in a new Journal page tab. Highlight divergences > 20%.

---

### Step 6 — Phase 3 Close

- Pre-live checklist in `docs/risk-review.md` completed
- Kill switch exercised on demo account
- First live session: 1 instrument only, minimum position size
- Incremental expansion to full watchlist after 2 weeks of stable operation

---

## 7. Interface Definitions

### Curated Bar Schema

Every curated Parquet file must conform to this schema. Any consumer that reads a curated file must validate against it.

| Column | Type | Constraints |
|---|---|---|
| timestamp | datetime64[ns, UTC] | Non-null, UTC-aware, sorted ascending |
| open | float64 | > 0 |
| high | float64 | >= open |
| low | float64 | <= open |
| close | float64 | > 0, non-null |
| volume | float64 | >= 0 |
| symbol | str | Non-null, matches MarketDataRequest.symbol |
| source | str | Non-null, e.g. "yfinance" |
| adjusted | bool | Non-null, from MarketDataRequest.adjusted |

### Signal Schema

The DataFrame returned by any `Strategy.generate_signals()` call.

| Column | Type | Constraints |
|---|---|---|
| timestamp | datetime64[ns, UTC] | From input bars |
| open | float64 | From input bars |
| high | float64 | From input bars |
| low | float64 | From input bars |
| close | float64 | From input bars |
| signal | int8 | Must be in {-1, 0, 1} |
| position_change | int8 | 1 on long entry, -1 on exit/short entry, 0 otherwise |
| fast_sma | float64 | Strategy-specific; NaN during warmup |
| slow_sma | float64 | Strategy-specific; NaN during warmup |
| rsi | float64 | Present when RSI filter enabled; NaN during warmup |

### BacktestConfig Schema

```python
@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    timeframe: str               # "1d" or "1wk"
    start_date: date
    end_date: date               # must be > start_date
    strategy_name: str
    strategy_params: dict
    initial_cash: float = 100_000.0
    commission_bps: float = 5.0
    slippage_bps: float = 2.0
    risk_free_rate: float = 0.0
```

### BacktestResult Schema

```python
@dataclass(frozen=True)
class BacktestResult:
    config: BacktestConfig
    total_return: float
    cagr: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    win_rate: float | None
    num_trades: int
    avg_trade_return: float | None
    profit_factor: float | None
    run_timestamp: datetime
```

### SignalRecord Schema (Phase 2)

```python
@dataclass
class SignalRecord:
    signal_id: str               # uuid4
    symbol: str
    timestamp_generated: datetime
    signal: int                  # 1 or -1
    close_at_generation: float
    fast_sma: float
    slow_sma: float
    rsi: float | None
    status: SignalStatus         # pending | approved | rejected | expired
    timestamp_actioned: datetime | None
    deal_id: str | None          # set on approval if IG confirms
```

### TradeRecord Schema (Phase 2)

```python
@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    direction: str               # "BUY" or "SELL"
    entry_timestamp: datetime
    entry_price: float
    exit_timestamp: datetime | None
    exit_price: float | None
    size: float
    gross_return: float | None
    cost: float | None
    net_return: float | None
    stop_level: float
    signal_id: str
    approved_by: str             # always "manual" in Phase 2-3
    notes: str | None
```

### SignalExplanation Schema (LLM layer)

```python
@dataclass(frozen=True)
class SignalExplanation:
    symbol: str
    signal_date: date
    signal: int
    explanation: str
    generated_at: datetime
    model: str
    cached: bool
```

### OrderRequest Schema

```python
@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    ig_epic: str                 # required from instruments.yaml
    side: str                    # "BUY" or "SELL"
    size: float
    stop_loss: float             # required; no order without a stop
    signal_id: str               # for audit trail linkage
```

---

## 8. Configuration Design

### What Goes in Which File

**`config/instruments.yaml`** — instrument registry and watchlist
Contains: `symbol`, `name`, `asset_class`, `timeframe`, `source`, `session_timezone`, `adjusted_prices`, `ig_epic` (Phase 2)
Does not contain: API keys, credentials, risk limits, strategy parameters

**`config/strategies/sma_cross.yaml`** — strategy parameters
Contains: `strategy` (class name), `params` (all constructor arguments), `backtest` (default `initial_cash`, `commission_bps`, `slippage_bps`)
Does not contain: date ranges (specified at backtest runtime), credentials

**`config/environments/local.yaml`** — operational configuration
Contains: `default_data_source`, `timezone`, data directory paths, `ig` retry/timeout settings, `llm` provider/model/timeout, `risk` parameters (Phase 2+), `signal_expiry_hours` (Phase 2)
Does not contain: API keys, passwords, account IDs

**`.env`** — secrets only
Contains: `ANTHROPIC_API_KEY`, `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, `IG_ACCOUNT_ID`, `IG_ENVIRONMENT`
Never committed to version control. `.env.example` contains the key names with empty values.

**`pyproject.toml`** — package metadata, dependencies, tool config
Contains: package deps, dev deps, `pytest`, `ruff`, `black` configuration
Does not contain: runtime config, secrets

### Environment Variable Naming Convention

All secrets use `UPPER_SNAKE_CASE` with a service prefix: `IG_`, `ANTHROPIC_`.
All config in YAML uses `lower_snake_case` with section nesting.
No config value is duplicated between `.env` and YAML.

---

## 9. Testing Strategy

### What to Test and at Which Layer

**Unit tests** (`tests/`) — pure functions, no I/O, no network
All indicator functions, strategy `generate_signals`, backtest metrics, config validation, LLM cache logic, position sizer formula, risk check logic, signal lifecycle transitions. Use synthetic DataFrames with known answers. Fast enough to run on every commit.

**Integration tests** (`tests/integration/`) — file I/O, no network
Ingest pipeline end-to-end using a fixture Parquet file (not live yfinance). Backtest result persistence (writes and reads files). Signal store persistence (Parquet append). Dashboard signal runner with mock filesystem. These are slower and tagged `@pytest.mark.integration`.

**No live network calls in the test suite.** yfinance calls are mocked using `unittest.mock.patch`. IG API calls are mocked with `responses`. Anthropic API calls use `StubLLMClient`.

**Manual acceptance testing** — human review, not automated
Dashboard rendering with real data. LLM explanation quality. IG demo order placement and position monitoring. Kill switch behaviour on demo account.

### What Not to Test

- Streamlit page rendering (integration testing Streamlit is painful and low-value; use manual review)
- yfinance API behaviour (external service; trust it works)
- IG API behaviour (mock it; test our adapter's response to API responses, not the API itself)

### Test Data Strategy

Keep synthetic test DataFrames in `tests/fixtures/`. These are small (50-100 rows), created programmatically in conftest.py, and have precisely known properties (e.g. a SMA crossover occurs on bar 35).

For integration tests that need realistic data, use a committed fixture file at `tests/fixtures/gc_1d_yfinance_sample.parquet` (100 rows of real Gold futures data). This file is small enough to commit and does not change.

### Coverage Target

Phase 1: 80% line coverage on `src/trading_lab/` excluding `app/` and `execution/ig.py` (the stub).
Phase 2: 80% coverage on execution adapters with mocked HTTP.

Do not chase 100% coverage. Focus on the calculation paths (metrics, indicators, engine) and the validation paths (config loader, schema validator, signal validator).

---

## 10. Risks and Mitigations

### Risk 1 — Backtest results are misleading (long/flat engine misrepresenting short signals)

**Current state:** The engine clips `signal=-1` to `0`. Any backtest run today silently ignores sell signals, making a SMA crossover strategy look like a simple buy-and-hold filter.
**Mitigation:** Fix the engine in Step 0 (before any new work). Add a test that verifies a short position on a falling market produces a positive return. Do not run or share any backtest result until this is fixed.

### Risk 2 — Curated data inconsistency across runs (adjusted flag not persisted)

**Current state:** The `adjusted` column is absent from curated files. Two curated files for the same symbol may contain different price series (adjusted vs unadjusted) with no way to detect this downstream.
**Mitigation:** Add `adjusted` to the curated schema in Step 0. Add schema validation that checks this column on read. Consider adding a file-level hash to backtest result metadata so any change to the source data is detectable.

### Risk 3 — LLM explanation cost and latency degrading dashboard UX

**Risk:** If the LLM is called synchronously on page load for all five instruments with non-neutral signals, the dashboard could be slow and expensive.
**Mitigation:** The cache-first design in Section 3 ensures LLM is called at most once per signal per day, not on every page load. The dashboard reads from the cache file. New explanations are generated asynchronously (or on a manual refresh action), not on every render. A `StubLLMClient` fallback ensures the dashboard works without an API key.

### Risk 4 — IG demo API differences from live causing false confidence

**Risk:** IG demo behaves slightly differently from live in edge cases (order rejection rules, position limits, margin calculations). Paper trading success on demo does not guarantee live success.
**Mitigation:** The 30-day demo trading requirement before Phase 3 is not just a timeline gate — it is intended to surface these discrepancies. Document any observed differences in `docs/risk-review.md`. Be specifically sceptical of demo results for stop loss triggering and margin-related order rejections.

### Risk 5 — Single Streamlit process blocking on data refresh

**Risk:** The Streamlit process runs in a single thread. A blocking `ingest_market_data` call during a dashboard refresh will freeze the UI for all users (though this is a single-user system, it will feel unresponsive).
**Mitigation:** Run the ingest as a subprocess via `subprocess.Popen` from the dashboard refresh button. Use `st.spinner` for feedback. Report completion via a status file written by the subprocess. This avoids making Streamlit multi-threaded.

### Risk 6 — Signal expiry clock drift causing unexpected pending signal loss

**Risk:** In Phase 2, signals expire after 24 hours. If the machine running the dashboard is not running continuously (likely, given this is a local-first system), a signal could expire during a period when the dashboard is not open.
**Mitigation:** The expiry check runs on startup, not on a background clock. Signals are marked expired based on their `timestamp_generated` relative to `datetime.utcnow()` at startup. This is correct behaviour — a 24-hour-old signal on a daily bar strategy is genuinely stale. Document this explicitly so the user is not surprised.

### Risk 7 — Parquet append semantics creating duplicate records in the journal

**Risk:** `data/journal/signals.parquet` and `data/journal/trades.parquet` are append-only. A crash mid-write or a code bug could write duplicate records.
**Mitigation:** Use `signal_id` (uuid4) and `trade_id` as primary keys. All reads deduplicate on these keys before aggregation. Writes use a temp-file-then-rename pattern to prevent partial writes. On startup, validate the journal by checking for duplicate IDs and logging a WARNING (not a failure) if any are found.

### Risk 8 — yfinance data quality for commodity futures (roll gaps, missing bars)

**Risk:** Commodity futures tickers in yfinance (e.g. `GC=F`) represent front-month continuous contracts. Roll dates create price discontinuities. Gaps around exchange holidays may cause unexpected NaN or missing bars.
**Mitigation:** The data validation in Step 1 (REQ-DATA-005) checks for gaps but does not fail on them — it logs a WARNING. Strategies use rolling calculations on close prices, so a single missing bar does not invalidate a signal. Document that commodity signals should be reviewed against known roll calendar dates before acting.

### Risk 9 — Accidental live order placement during development

**Risk:** In Phase 2+, a code path exercised during development could reach `IgBrokerAdapter.place_order()` with live credentials.
**Mitigation:** Three-layer guard: (1) `IG_ENVIRONMENT` enforced at adapter init; (2) the environment banner makes the current mode visually unambiguous; (3) no Phase 2 code is added to the `main` branch until Phase 1 is complete, and `IG_ENVIRONMENT=live` is only ever set intentionally. The test suite always uses a mocked adapter, never a live one.

### Risk 10 — Dashboard state management complexity as Phase 2 features accumulate

**Risk:** Streamlit's session state model is simple but becomes difficult to reason about when approval workflows, background polling, and position state all interact in the same session.
**Mitigation:** Isolate state. Signal state lives in `data/journal/signals.parquet` (disk), not in `st.session_state` (which is page-load-scoped). Position state is fetched from IG on refresh, cached to a file, displayed from that file. Session state is used only for transient UI state (modal open/closed, button disabled). This makes the dashboard stateless between refreshes and resilient to page reloads.

---

*End of Build Plan — v1.0*
