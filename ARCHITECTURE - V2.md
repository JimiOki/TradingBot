# Trading Lab — Architecture

**Version:** 2.0
**Date:** 2026-04-03
**Status:** Active — supersedes the original `ARCHITECTURE.md`
**Informed by:** `docs/requirements.md`, `docs/build-plan.md`, codebase audit (2026-04-03)

---

## Table of Contents

1. [Vision and Goals](#1-vision-and-goals)
2. [Architectural Principles](#2-architectural-principles)
3. [System Overview — Component Diagram](#3-system-overview--component-diagram)
4. [Layer Responsibilities](#4-layer-responsibilities)
5. [Full Repository Layout](#5-full-repository-layout)
6. [Data Architecture](#6-data-architecture)
7. [Instrument Roadmap](#7-instrument-roadmap)
8. [Technology Stack](#8-technology-stack)
9. [Configuration Model](#9-configuration-model)
10. [Security and Secrets](#10-security-and-secrets)
11. [Testing Strategy](#11-testing-strategy)
12. [Phase Roadmap Summary](#12-phase-roadmap-summary)
13. [Anti-Patterns](#13-anti-patterns)
14. [Architecture Gaps Register](#14-architecture-gaps-register)

---

## 1. Vision and Goals

### What the system is

Trading Lab is a **local-first, discretionary algorithmic trading research and execution platform**. It is designed for a single operator running daily bar strategies on liquid commodities, indices, and forex instruments via IG spreadbetting (UK).

The system has three modes of operation:

- **Research mode (Phase 1):** Ingest historical data, compute rule-based signals, run backtests, and surface results through a Streamlit dashboard. No broker connectivity.
- **Paper trading mode (Phase 2):** Connect to an IG demo account. Present signals to the operator for approval. Submit approved orders to the demo account. Monitor positions.
- **Live trading mode (Phase 3):** Switch to the IG live account via a credential swap. Enforce pre-execution risk controls. Support a kill switch. No other code change is required.

### Core goals

- **Reproducible research.** Every backtest is fully described by an explicit configuration object. Running the same config against the same data on any date produces identical results.
- **Clean signal generation.** Strategy logic is pure: no I/O, no network calls, no broker coupling. Strategies consume normalised DataFrames and emit signal DataFrames.
- **Realistic backtesting.** The engine applies commissions, slippage, a one-bar execution lag, and supports long, flat, and short positions. No lookahead. No hidden assumptions.
- **Safe path to live trading.** Demo before live is mandatory. The execution environment is selected by a single credential change. Three independent guards prevent accidental live orders.
- **Human in the loop.** The system recommends; the operator decides. Every order requires explicit approval. There is no autonomous execution.

### What the system is NOT

- Not a fully automated trading bot.
- Not a high-frequency or intraday system. Primary timeframe is daily bars.
- Not a cloud-first platform. Everything runs on a local machine. Remote access is handled by Tailscale (iPhone dashboard access), not cloud deployment.
- Not a machine learning system. Signal generation is rule-based in all three phases. ML is an explicit out-of-scope concern.
- Not a portfolio optimisation tool. Position sizing is fixed-risk per trade, not mean-variance optimised.

---

## 2. Architectural Principles

These constraints apply to all phases. New code that contradicts a principle requires a documented exception.

**1. Research code and execution code are strictly separated.**
The `src/trading_lab/strategies/` and `src/trading_lab/backtesting/` packages have no imports from `src/trading_lab/execution/`. The dependency is one-directional: execution depends on signals; signals never depend on execution.

**2. Notebooks are for exploration only — never system-of-record code.**
All reusable logic lives in the `src/trading_lab/` package. A notebook may call package functions and inspect results. No notebook writes to `data/curated/`, generates the authoritative signal snapshot, or defines a strategy class.

**3. Data is treated as a product with explicit schemas, conventions, and lineage.**
Every curated Parquet file conforms to a defined schema. Every file carries its provenance (`symbol`, `source`, `adjusted` flag) in its columns, not inferred from its filename. Data consumers validate the schema before processing.

**4. Every workflow is reproducible from config alone.**
The ingest script reads instruments from `instruments.yaml`. The backtest engine reads all run parameters from `BacktestConfig`. The strategy reads all parameters from its YAML file. No workflow parameter is read from environment variables, global state, or hard-coded defaults inside business logic.

**5. The LLM is off the critical path.**
The LLM is called once per new signal, its output is cached to disk, and the dashboard reads from the cache. A missing `ANTHROPIC_API_KEY`, an API timeout, or an API failure all fall back to a stub explanation. Signal generation, backtesting, and order placement are entirely unaffected by LLM availability.

**6. Demo before live — identical API, single config change.**
The IG demo API and the IG live API are identical. The adapter selects the endpoint from `IG_ENVIRONMENT` in `.env`. Switching from demo to live is a credential update, not a code change. Running 30 days of stable paper trading on demo is a Phase 2 exit criterion.

**7. Human in the loop for all trading decisions.**
The signal approval workflow requires the operator to click Approve and then confirm the position size before any order is submitted. There is no pathway from signal generation to order placement that does not require two explicit human actions.

**8. No shared mutable state across layers.**
Layers communicate via DataFrames passed as arguments and Parquet files on disk. No layer modifies a shared in-memory object owned by another layer. The Streamlit session state is confined to the application layer.

---

## 3. System Overview — Component Diagram

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL SOURCES                                  │
│                                                                                │
│   yfinance           IG REST API        IG Streaming API    Anthropic Claude   │
│   (research data)    (orders, positions) (live candles)     (LLM explanations) │
│                                                                                │
│   News / Economic Calendar (context only — no automated feed in Phase 1-2)    │
└───────┬──────────────────┬─────────────────┬──────────────────┬───────────────┘
        │                  │                 │                  │
        ▼                  │                 │                  ▼
┌───────────────────┐      │                 │        ┌─────────────────────────┐
│   DATA LAYER      │      │                 │        │   LLM EXPLANATION LAYER  │
│                   │      │                 │        │                         │
│  yfinance_ingest  │      │                 │        │  explainer.py           │
│  transforms.py    │      │                 │        │  claude_client.py       │
│  models.py        │      │                 │        │  stub_client.py         │
│                   │      │                 │        │  base.py (LLMClient ABC)│
│  data/raw/        │      │                 │        │                         │
│  data/curated/    │      │                 │        │  data/signals/          │
└───────┬───────────┘      │                 │        │  explanations/          │
        │                  │                 │        └────────────┬────────────┘
        ▼                  │                 │                     │
┌───────────────────┐      │                 │                     │
│   FEATURES LAYER  │      │                 │                     │
│                   │      │                 │                     │
│  indicators.py    │      │                 │                     │
│  (sma, rsi, macd) │      │                 │                     │
└───────┬───────────┘      │                 │                     │
        │                  │                 │                     │
        ▼                  │                 │                     │
┌───────────────────┐      │                 │                     │
│   STRATEGY LAYER  │      │                 │                     │
│                   │      │                 │                     │
│  base.py          ├──────┼─────────────────┼─────────────────────┘
│  sma_cross.py     │      │                 │  (signal rows → LLM)
│  loader.py        │      │                 │
│  runner.py        │      │                 │
│                   │      │                 │
│  data/signals/    │      │                 │
└───────┬───────────┘      │                 │
        │                  │                 │
        ├──────────────┐   │                 │
        │              │   │                 │
        ▼              ▼   │                 ▼
┌──────────────┐  ┌────────┴──────────────────────────┐
│  BACKTESTING │  │   SIGNAL APPROVAL LAYER (Phase 2)  │
│  LAYER       │  │                                    │
│              │  │  signal_state.py (SignalStore)      │
│  engine.py   │  │  position_sizer.py                 │
│  metrics.py  │  │                                    │
│  models.py   │  │  data/journal/signals.parquet      │
│  reporter.py │  └──────────────────┬─────────────────┘
│              │                     │ (approved order)
│  data/       │                     ▼
│  backtests/  │  ┌──────────────────────────────────────┐
└──────┬───────┘  │   EXECUTION LAYER                    │
       │          │                                      │
       │          │  broker_base.py (BrokerAdapter ABC)  │
       │          │  ig.py (IgBrokerAdapter)             │
       │          │  ig_streaming.py (Phase 2)           │
       │          │  position_sizer.py                   │
       │          │  risk_checks.py (Phase 3)            │
       │          │  kill_switch.py (Phase 3)            │
       │          │                                      │
       │          │  data/live/                          │
       │          └──────────────────────────────────────┘
       │                     │
       └──────────┬──────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│   APPLICATION LAYER                                  │
│                                                      │
│   app/main.py (Streamlit entry point)                │
│   app/pages/dashboard.py   (signals, portfolio)      │
│   app/pages/charts.py      (price charts, overlays)  │
│   app/pages/backtests.py   (run + review backtests)  │
│   app/pages/settings.py    (instruments, params)     │
│   app/pages/journal.py     (trades + signals — P2)   │
└─────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│   CONFIG LAYER                                       │
│                                                      │
│   config/instruments.yaml                            │
│   config/strategies/sma_cross.yaml                   │
│   config/environments/local.yaml                     │
│   .env  (secrets only — never committed)             │
└─────────────────────────────────────────────────────┘
```

---

## 4. Layer Responsibilities

### 4.1 Data Layer — `src/trading_lab/data/`

**Purpose:** Fetch, normalise, validate, and persist market data.

**Owns:**
- Raw Parquet files in `data/raw/` — source-shaped, minimally transformed.
- Curated Parquet files in `data/curated/` — validated, schema-stable, UTC timestamps, `adjusted` flag.
- `MarketDataRequest` dataclass (the ingest request contract).
- The curated bar schema and its validation logic.
- Atomic write semantics: raw file is written before transformation; curated file is written to a temp path and renamed on success.

**Does NOT do:**
- Compute indicators or signals.
- Know anything about strategies, backtests, or the broker.
- Apply any business rules to data beyond schema conformance.

**Key modules:**
- `yfinance_ingest.py` — downloads, persists raw, calls normalisation, writes curated.
- `transforms.py` — `normalize_yfinance_daily()`, `validate_curated_dataframe()`.
- `models.py` — `MarketDataRequest` dataclass. Validates `interval` at construction (`"1d"` and `"1wk"` only).

---

### 4.2 Features Layer — `src/trading_lab/features/`

**Purpose:** Provide pure, side-effect-free indicator functions that strategies call.

**Owns:**
- SMA, RSI, and MACD computations.
- Input length validation (raises `ValueError` if the series is shorter than the minimum required length).

**Does NOT do:**
- Read or write any file.
- Know about strategies, instruments, or configurations.
- Modify the input Series in place.

**Key modules:**
- `indicators.py` — `sma(prices, window)`, `rsi(prices, period)`, `macd(prices, fast, slow, signal)`.

---

### 4.2a Context Layer — `src/trading_lab/context/`

**Purpose:** Fetches and caches market context data — economic calendar events and news headlines — that enriches signal explanations and dashboard warnings.

**Owns:**
- Economic calendar event fetching and caching.
- News headline fetching per instrument.
- Graceful degradation: fetch failures are non-blocking; the LLM call proceeds without context if fetches fail.

**Does NOT do:**
- Generate signals.
- Block the data refresh pipeline on fetch failure.
- Write to `data/curated/` or `data/signals/`.

**Key modules:**
- `economic_calendar.py` — fetches high-impact events from a free RSS source (e.g. Investing.com or ForexFactory RSS). Caches to `data/calendar/events_<date>.json`. Graceful degradation: if fetch fails, returns empty list and logs WARNING.
- `news.py` — fetches up to 5 recent headlines per instrument from yfinance news feed. Cached alongside signal data. If fetch fails, LLM proceeds without news context.

**Data directories:** `data/calendar/`, `data/news/`

**Note on architecture principle #5 (LLM off the critical path):** News fetch failures are logged at WARNING and the LLM call proceeds without news context. The data refresh script does not fail because of a news fetch failure. Calendar fetch failures are similarly non-blocking.

**Integration point:** Both are called from `scripts/ingest_market_data.py` after price data refresh, before signal generation. Results are passed to the LLM explainer as optional context.

---

### 4.2b Risk Layer — `src/trading_lab/risk/`

**Purpose:** Computes cross-instrument risk metrics. Does not generate signals. Does not place orders.

**Owns:**
- Pairwise correlation matrix computation across all instruments.
- `data/risk/correlation.parquet` — recomputed on each data refresh.

**Does NOT do:**
- Generate signals.
- Place or approve orders.
- Read live broker data directly.

**Key module:** `src/trading_lab/risk/correlation.py`

```python
def compute_pairwise_correlation(
    curated_data_dir: Path,
    instrument_list: list[str],
    window_days: int = 60,
) -> pd.DataFrame:
    """Returns a pairwise correlation matrix for the given instruments."""
```

**Data output:** `data/risk/correlation.parquet` — recomputed on each data refresh.

**Integration:** Called from `scripts/ingest_market_data.py` after price data refresh. Dashboard reads from `data/risk/correlation.parquet` to display correlation warnings.

---

### 4.3 Strategy Layer — `src/trading_lab/strategies/`

**Purpose:** Produce a signals DataFrame from a curated bars DataFrame.

**Owns:**
- The `Strategy` abstract base class and its signal contract enforcement.
- `SmaCrossStrategy` — the Phase 1 reference implementation.
- Strategy loading from YAML config.
- The portfolio-level signal runner.

**Does NOT do:**
- Read data from disk directly. The caller loads the curated DataFrame and passes it in.
- Call broker APIs.
- Perform file I/O of any kind inside `generate_signals`.
- Read environment variables or global state inside `generate_signals`.

**Signal contract:**

| Column | Type | Constraints |
|---|---|---|
| timestamp | datetime64[ns, UTC] | From input bars |
| open, high, low, close | float64 | From input bars |
| signal | int8 | Must be in {-1, 0, 1} |
| position_change | int8 | 1 on entry, -1 on exit/reversal, 0 otherwise |
| fast_sma, slow_sma | float64 | NaN during warmup period |
| rsi | float64 | Present when RSI filter enabled; NaN during warmup |
| stop_loss_level | float | ATR-based stop loss price level (NaN for flat signals) |
| take_profit_level | float | Risk/reward-derived take profit level (NaN for flat signals) |
| stop_distance | float | Absolute distance from entry to stop (NaN for flat signals) |
| atr_value | float | ATR(14) value at signal date |
| confidence_score | int | 0–100 score: base 50 + SMA gap bonus + RSI direction bonus |
| signal_strength_pct | float | SMA gap as percentage of close price |
| conflicting_indicators | bool | True when SMA and RSI point in opposite directions |
| high_volatility | bool | True when ATR(14) > 2× its 30-day rolling average |

**Key modules (updated):**
- `base.py` — `Strategy` ABC. The `generate_signals` wrapper validates the return contract: `signal` column must exist; values must be in `{-1, 0, 1}`.
- `sma_cross.py` — `SmaCrossStrategy`. Parameters: `fast_window`, `slow_window`, `rsi_period`, `rsi_overbought`, `rsi_oversold`, `rsi_filter_enabled`. `generate_signals()` must populate all signal contract fields including stop/target/quality fields.
- `quality.py` — pure functions for `confidence_score`, `signal_strength_pct`, `conflicting_indicators`, `high_volatility`.
- `loader.py` — `load_strategy(config_path)` reads a strategy YAML and returns a configured instance.
- `runner.py` — `run_signals_for_all_instruments(instruments, strategy)` returns a portfolio-level signal summary DataFrame and writes the snapshot to `data/signals/`.

**Ownership (extended):** Computes ATR-based stop loss and take profit levels for each non-flat signal using `features/indicators.py:atr()`. Assigns all signal quality fields.

---

### 4.3a Signal Approval Layer — `src/trading_lab/signals/` (Phase 2)

**Purpose:** Manages the lifecycle of signals from generation through operator approval to execution. Monitors open positions for exit conditions on each data refresh.

**Owns:**
- `SignalStore` — persists signal records to `data/journal/signals.parquet` with status tracking (`pending`, `approved`, `rejected`, `executed`).
- `SignalRecord` and `SignalStatus` dataclasses.
- `position_sizer.py` — `calculate_position_size(account_balance, risk_pct, entry_price, stop_loss_price)`.
- `exit_monitor.py` — evaluates all open positions against exit conditions and writes recommendations to `data/journal/exit_recommendations.parquet`.

**Does NOT do:**
- Place orders. Approved signals are handed to the Execution Layer.
- Generate signals. Signals originate from the Strategy Layer.

**Key modules:**
- `state.py` — `SignalStore`, `SignalRecord`, `SignalStatus`.
- `position_sizer.py` — pure sizing formula.
- `exit_monitor.py` — see below.

**New module: `exit_monitor.py`**

Purpose: Evaluates all open positions in `data/journal/trades.parquet` against five exit conditions on each data refresh. Produces `ExitRecommendation` records written to `data/journal/exit_recommendations.parquet`.

Exit conditions evaluated:
1. Stop loss hit — current price crosses `stop_loss_level`
2. Take profit hit — current price crosses `take_profit_level`
3. Opposite signal fired — new signal contradicts open position direction
4. Signal age exceeded — position open for more than configurable threshold (default 10 days)
5. RSI extreme — RSI > 80 for a long position, RSI < 20 for a short position

Key interface:
```python
@dataclass(frozen=True)
class ExitRecommendation:
    symbol: str
    exit_condition: str  # "stop_hit" | "target_hit" | "opposite_signal" | "signal_age" | "rsi_extreme"
    current_price: float
    stop_level: float
    target_level: float
    recommended_at: datetime

def evaluate_open_positions(
    trades_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    current_prices: dict[str, float],
    config: BacktestConfig,
) -> list[ExitRecommendation]:
    ...
```

---

### 4.4 LLM Layer — `src/trading_lab/llm/`

**Purpose:** Generate and cache plain-English explanations of non-neutral signals.

**Owns:**
- The `LLMClient` abstract base class.
- `ClaudeClient` — calls the Anthropic API using `ANTHROPIC_API_KEY` from `.env`.
- `StubLLMClient` — returns a fixed string; used when the API key is absent or in test environments.
- `ExplanationService` — implements cache-first lookup. Cache hit: return the stored `SignalExplanation`. Cache miss: call the LLM, write to cache, return result.
- The explanation prompt template.
- Cached explanations in `data/signals/explanations/`.

**Does NOT do:**
- Generate signals.
- Modify signal data.
- Block the backtesting or order placement workflows under any circumstance.
- Make API calls on cache hits.

**Key modules:**
- `base.py` — `LLMClient(ABC)` with `complete(prompt: str) -> str`.
- `claude_client.py` — `ClaudeClient`. Raises `LLMError` on failure; `LLMTimeoutError` on timeout. Falls back to stub if `ANTHROPIC_API_KEY` is absent.
- `stub_client.py` — `StubLLMClient`.
- `explainer.py` — `ExplanationService` and the `SignalExplanation` dataclass.

---

### 4.5 Backtesting Layer — `src/trading_lab/backtesting/`

**Purpose:** Run reproducible simulations and persist results.

**Owns:**
- The `BacktestConfig` dataclass (fully describes a run; construction fails if incomplete).
- The backtest engine: no-lookahead enforcement, long/flat/short support, cost model.
- Metrics computation: total return, CAGR, Sharpe ratio, max drawdown, win rate, profit factor.
- Trade log extraction: one row per round-trip trade.
- Result persistence: summary JSON + trades Parquet written atomically to `data/backtests/`.

**Does NOT do:**
- Read curated files directly. The caller loads the DataFrame and passes it in.
- Know about the broker or the live execution environment.
- Apply signals to the same bar on which they were generated (execution is one bar after signal).

**Key modules:**
- `engine.py` — `run_backtest(signals_df, config)`. Execution is assumed at the close of the bar following signal generation (next-bar close with slippage approximation). This is documented in the module docstring.
- `metrics.py` — `compute_metrics(equity_curve, trades, config) -> BacktestResult`. Metrics undefined by insufficient trades return `None`, not zero.
- `models.py` — `BacktestConfig` and `BacktestResult` dataclasses. `BacktestConfig` requires the following additional fields:
  - `mode: Literal["in_sample", "out_of_sample", "full"]`
  - `oos_ratio: float = 0.3` (used when mode is `"full"` to auto-split)
  - `parameters_locked: bool = False` (set to True after in_sample run; prevents re-tuning)
- `reporter.py` — `save_backtest_result(result, config, trade_log, output_dir)`.
- `validation.py` — implements in-sample / out-of-sample data splitting and strategy approval thresholds (see below).

**New module: `validation.py`**

Purpose: Implements in-sample / out-of-sample data splitting and strategy approval thresholds.

Key functions:
```python
def split_in_sample_out_of_sample(
    bars_df: pd.DataFrame,
    oos_ratio: float = 0.3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (in_sample_df, out_of_sample_df). Split is always chronological."""

def validate_oos_thresholds(
    result: BacktestResult,
    min_sharpe: float = 0.5,
    max_drawdown_pct: float = 25.0,
) -> ValidationResult:
    """Returns APPROVED or NOT_APPROVED with reason."""

def compute_performance_degradation(
    in_sample_result: BacktestResult,
    oos_result: BacktestResult,
) -> float:
    """Returns degradation as a percentage. >50% triggers overfitting warning."""
```

**Backtest artefact naming for IS/OOS runs:**
- In-sample artefacts: `<symbol>_<timeframe>_<strategy>_<timestamp>_in_sample_summary.json`
- Out-of-sample artefacts: `<symbol>_<timeframe>_<strategy>_<timestamp>_out_of_sample_summary.json`

---

### 4.6 Execution Layer — `src/trading_lab/execution/`

**Purpose:** Place and manage orders through the IG broker API.

**Owns:**
- The `BrokerAdapter` abstract base class.
- `IgBrokerAdapter` — authenticates, places orders, retrieves positions, closes positions.
- Session token management and refresh.
- The `IG_ENVIRONMENT` guard: raises `EnvironmentMismatchError` if the configured environment does not match the endpoint. This cannot be overridden at call time.
- Position sizing formula: `calculate_position_size(account_balance, risk_pct, entry_price, stop_loss_price)`.
- Pre-execution risk checks (Phase 3): daily loss limit, exposure cap, duplicate position guard, stop loss presence check.
- Kill switch (Phase 3): closes all open positions and sets the `halted` flag.
- Order audit log at `logs/orders.log` (all API requests and responses, credentials redacted).

**Does NOT do:**
- Generate signals.
- Run backtests.
- Make any broker API call without an explicit human approval upstream (in Phase 2 and Phase 3).

**Key modules:**
- `broker_base.py` — `BrokerAdapter(ABC)`.
- `ig.py` — `IgBrokerAdapter`.
- `ig_streaming.py` — Lightstreamer wrapper for live candles and account feed (Phase 2).
- `position_sizer.py` — pure sizing formula.
- `risk_checks.py` — `check_pre_submission(order, account_state, config)` (Phase 3).
- `kill_switch.py` — `activate()` (Phase 3).

---

### 4.7 Application Layer — `app/`

**Purpose:** Render the Streamlit dashboard. Orchestrate all other layers. Contain no business logic.

**Owns:**
- Multi-page Streamlit application.
- Reading from the data directory and calling package functions.
- Session state for UI controls (selected instrument, date range, in-flight request guards).
- The environment banner (DEMO / LIVE) rendered on all pages.

**Does NOT do:**
- Contain indicator calculations, signal generation logic, or backtest engine logic.
- Write to `data/curated/` or `data/signals/` except by calling the appropriate package function.
- Expose credential fields in any UI.

**Key modules:**
- `app/main.py` — Streamlit entry point.
- `app/pages/dashboard.py` — Signal table, portfolio summary panel, refresh button, LLM explanations.
- `app/pages/charts.py` — Candlestick chart, SMA overlay, RSI/MACD subplots, signal event markers.
- `app/pages/backtests.py` — Backtest form, results card, equity curve, trade log.
- `app/pages/settings.py` — Instrument list viewer/editor, strategy parameter viewer.
- `app/pages/journal.py` — Trades tab and Signals tab with approve/reject history (Phase 2).

---

### 4.8 Config Layer — `config/`

**Purpose:** Provide all non-secret runtime configuration as human-editable YAML files.

**Owns:**
- `instruments.yaml` — the single source of truth for which instruments the system processes.
- `strategies/<name>.yaml` — all strategy parameters.
- `environments/local.yaml` — paths, capital, risk settings, LLM model selection.

**Does NOT own:**
- Secrets. Credentials live exclusively in `.env`.

---

## 5. Full Repository Layout

This is the target structure for Phase 1 completion. Phase 2 and Phase 3 additions are annotated.

```text
trading-lab/
|
|-- app/
|   |-- main.py                    # Streamlit entry point
|   `-- pages/
|       |-- dashboard.py           # Signal table, portfolio summary, LLM explanations
|       |-- charts.py              # Interactive price chart, overlays
|       |-- backtests.py           # Backtest runner and results viewer
|       |-- settings.py            # Instrument and strategy config viewer
|       `-- journal.py             # Trade and signal history (Phase 2)
|
|-- config/
|   |-- instruments.yaml           # Watchlist: symbols, epics, sessions
|   |-- environments/
|   |   `-- local.yaml             # Paths, capital, risk, LLM config
|   `-- strategies/
|       `-- sma_cross.yaml         # SMA cross strategy parameters
|
|-- data/
|   |-- raw/                       # Source-shaped Parquet, one file per symbol/interval
|   |-- curated/                   # Validated schema-stable Parquet
|   |-- features/                  # Pre-computed indicator frames (optional cache)
|   |-- backtests/                 # Summary JSON + trades Parquet per backtest run
|   |-- signals/                   # Latest signal snapshot per instrument
|   |   `-- explanations/          # LLM explanation cache (JSON, one per signal event)
|   |-- journal/                   # Trade and signal records (Phase 2)
|   |   |-- signals.parquet        # Signal lifecycle records
|   |   `-- trades.parquet         # Executed trade records
|   `-- live/                      # IG Streaming candle data (Phase 2)
|
|-- docs/
|   |-- build-plan.md
|   |-- requirements.md
|   |-- glossary.md
|   `-- risk-review.md             # Pre-live checklist (Phase 3)
|
|-- logs/
|   |-- trading_lab.log            # Application log (rotating)
|   `-- orders.log                 # Order audit log (Phase 2)
|
|-- notebooks/                     # Exploration only — no system-of-record code
|
|-- scripts/
|   |-- ingest_market_data.py      # CLI: refresh all instruments in instruments.yaml
|   `-- sanity_check.py            # Environment and dependency validation
|
|-- src/
|   `-- trading_lab/
|       |-- __init__.py
|       |-- paths.py               # Single source of truth for data directory paths
|       |-- exceptions.py          # All custom exceptions
|       |-- logging_config.py      # setup_logging() — called by all entry points
|       |-- config/
|       |   `-- loader.py          # load_instruments(), load_strategy_config()
|       |-- data/
|       |   |-- models.py          # MarketDataRequest dataclass
|       |   |-- transforms.py      # normalize_yfinance_daily(), validate_curated_dataframe()
|       |   `-- yfinance_ingest.py # ingest_yfinance_daily()
|       |-- features/
|       |   `-- indicators.py      # sma(), rsi(), macd()
|       |-- strategies/
|       |   |-- base.py            # Strategy ABC with signal contract enforcement
|       |   |-- sma_cross.py       # SmaCrossStrategy
|       |   |-- loader.py          # load_strategy(config_path)
|       |   `-- runner.py          # run_signals_for_all_instruments()
|       |-- llm/
|       |   |-- base.py            # LLMClient ABC
|       |   |-- claude_client.py   # ClaudeClient
|       |   |-- stub_client.py     # StubLLMClient
|       |   `-- explainer.py       # ExplanationService, SignalExplanation
|       |-- backtesting/
|       |   |-- engine.py          # run_backtest()
|       |   |-- metrics.py         # compute_metrics()
|       |   |-- models.py          # BacktestConfig, BacktestResult
|       |   `-- reporter.py        # save_backtest_result()
|       |-- signals/
|       |   `-- state.py           # SignalStore, SignalRecord, SignalStatus (Phase 2)
|       `-- execution/
|           |-- broker_base.py     # BrokerAdapter ABC
|           |-- ig.py              # IgBrokerAdapter
|           |-- ig_streaming.py    # Lightstreamer wrapper (Phase 2)
|           |-- position_sizer.py  # calculate_position_size()
|           |-- risk_checks.py     # check_pre_submission() (Phase 3)
|           `-- kill_switch.py     # activate() (Phase 3)
|
|-- tests/
|   |-- conftest.py
|   |-- data/
|   |   |-- test_transforms.py
|   |   `-- test_models.py
|   |-- config/
|   |   `-- test_loader.py
|   |-- features/
|   |   `-- test_indicators.py
|   |-- strategies/
|   |   |-- test_base.py
|   |   `-- test_sma_cross.py
|   |-- backtesting/
|   |   |-- test_engine.py
|   |   `-- test_metrics.py
|   `-- llm/
|       `-- test_explainer.py
|
|-- .env                           # Secrets only — never committed
|-- .env.demo                      # Demo credential template
|-- .env.live                      # Live credential template
|-- .gitignore
|-- pyproject.toml
`-- ARCHITECTURE.md
```

---

## 6. Data Architecture

### Data flow — Phase 1 (Research)

```
config/instruments.yaml
    |
    +--> scripts/ingest_market_data.py
             |
             +--> yfinance API
                      |
                      +--> data/raw/<symbol>_<interval>_yfinance.parquet
                               (source-shaped, written before transformation)
                      |
                      +--> data/curated/<symbol>_<interval>_yfinance.parquet
                               (validated schema, UTC timestamps, adjusted flag)
                                    |
                                    +--> SmaCrossStrategy.generate_signals()
                                             |
                                             +--> data/signals/<symbol>_<date>.parquet
                                             |         (signal snapshot — persisted before
                                             |          the dashboard reads it)
                                             |
                                             +--> ExplanationService.get_or_generate()
                                             |         |
                                             |         +--> [cache hit]
                                             |         |    data/signals/explanations/
                                             |         |    <symbol>_<date>_<signal>.json
                                             |         |
                                             |         +--> [cache miss]
                                             |              Anthropic Claude API
                                             |              --> write cache --> return
                                             |
                                             +--> run_backtest(config)
                                                      |
                                                      +--> data/backtests/
                                                           <symbol>_<tf>_<strategy>_
                                                           <utc_ts>_summary.json
                                                           <symbol>_<tf>_<strategy>_
                                                           <utc_ts>_trades.parquet
                                    |
                                    +--> Streamlit dashboard
                                         (reads from data/signals/ — not in-memory state)
```

### Data flow — Phase 2 additions (Paper Trading)

```
data/signals/<symbol>_<date>.parquet
    |
    +--> SignalStore.add_signal()  [only on position_change != 0]
             |
             +--> data/journal/signals.parquet  (status: pending)
                      |
                      +--> [Operator: Approve in dashboard]
                               |
                               +--> position_sizer.calculate_position_size()
                                        |
                                        +--> [Operator: Confirm size]
                                                 |
                                                 +--> IgBrokerAdapter.place_order() [demo]
                                                          |
                                                          +--> logs/orders.log
                                                          +--> data/journal/trades.parquet

IG Streaming API
    |
    +--> data/live/<symbol>_1d_ig_streaming.parquet
             |
             +--> Dashboard: positions panel (unrealised P&L)
                      |
                      +--> [Position closed on IG platform]
                               |
                               +--> IgBrokerAdapter.get_closed_positions()
                                        +--> data/journal/trades.parquet (exit row)
```

### Directory conventions

| Directory | Contents | Written by | Read by |
|---|---|---|---|
| `data/raw/` | Source-shaped yfinance output | `yfinance_ingest.py` | Never modified after write |
| `data/curated/` | Validated OHLCV Parquet | `yfinance_ingest.py` | Strategies, backtesting engine |
| `data/features/` | Pre-computed indicator frames | Optional pipeline step | Strategies (optional) |
| `data/signals/` | Latest signal snapshots | `signals/runner.py` | Dashboard, ExplanationService |
| `data/signals/explanations/` | LLM explanation JSON cache | `ExplanationService` | Dashboard |
| `data/backtests/` | Summary JSON + trades Parquet | `backtesting/reporter.py` | Dashboard (backtests page) |
| `data/journal/` | Signal and trade lifecycle records | `SignalStore`, `IgBrokerAdapter` | Dashboard (journal page) |
| `data/journal/exit_recommendations.parquet` | Exit recommendations from `exit_monitor.py` | `exit_monitor.py` | Dashboard (journal page) |
| `data/live/` | IG Streaming candle data | `ig_streaming.py` | Dashboard (positions panel) |

### File naming standards

| File type | Pattern | Example |
|---|---|---|
| Raw bar data | `<symbol>_<interval>_<source>.parquet` | `GC=F_1d_yfinance.parquet` |
| Curated bar data | `<symbol>_<interval>_<source>.parquet` | `GC=F_1d_yfinance.parquet` |
| Signal snapshot | `<symbol>_<date>.parquet` | `GC=F_2026-04-03.parquet` |
| LLM explanation | `<symbol>_<date>_<signal>.json` | `GC=F_2026-04-03_1.json` |
| Backtest summary | `<symbol>_<tf>_<strategy>_<utc_ts>_summary.json` | `GC=F_1d_sma_cross_20260403T1200Z_summary.json` |
| Backtest trades | `<symbol>_<tf>_<strategy>_<utc_ts>_trades.parquet` | `GC=F_1d_sma_cross_20260403T1200Z_trades.parquet` |
| Live candles | `<symbol>_<interval>_ig_streaming.parquet` | `GC=F_1d_ig_streaming.parquet` |

### Curated bar schema

Every curated Parquet file must conform to this schema. Consumers validate before processing.

| Column | Type | Constraints |
|---|---|---|
| timestamp | datetime64[ns, UTC] | Non-null, UTC-aware, sorted ascending |
| open | float64 | > 0 |
| high | float64 | >= open |
| low | float64 | <= open |
| close | float64 | > 0, non-null |
| volume | float64 | >= 0 |
| symbol | str | Non-null; matches `MarketDataRequest.symbol` |
| source | str | Non-null; e.g. `"yfinance"` |
| adjusted | bool | Non-null; from `MarketDataRequest.adjusted` |

Timezone rule: timestamps are always stored as UTC-aware `datetime64[ns, UTC]`. Timezone conversion from exchange-local time to UTC is explicit in `transforms.py`, not delegated to pandas defaults.

### Backtest in-sample / out-of-sample convention

When a backtest is split for validation purposes:
- In-sample artefacts: `<symbol>_<timeframe>_<strategy>_<timestamp>_in_sample_summary.json`
- Out-of-sample artefacts: `<symbol>_<timeframe>_<strategy>_<timestamp>_out_of_sample_summary.json`

The split ratio is stored in `BacktestConfig.oos_ratio` (default `0.3` = last 30% of the date range is OOS) and also in the strategy YAML as `oos_ratio`. If no split is configured (`mode = "full"` with no auto-split), a single summary file without the `_in_sample`/`_out_of_sample` suffix is written. The `validation.py` module in the Backtesting Layer enforces chronological splitting and approval thresholds.

---

## 7. Instrument Roadmap

### Phase 1 — Commodities

| Symbol | Name | Asset Class | Session TZ |
|---|---|---|---|
| GC=F | Gold Futures | commodity | America/New_York |
| CL=F | Crude Oil WTI Futures | commodity | America/New_York |
| SI=F | Silver Futures | commodity | America/New_York |
| HG=F | Copper Futures | commodity | America/New_York |
| NG=F | Natural Gas Futures | commodity | America/New_York |

### Phase 2 — Add Indices

Major equity indices to be confirmed against IG epic availability. Examples: FTSE 100, S&P 500, DAX, Nasdaq 100. Asset class: `index`.

### Phase 3 — Add Forex

Major and minor FX pairs to be confirmed. Examples: EURUSD, GBPUSD, USDJPY. Asset class: `fx`.

### `instruments.yaml` schema

Each instrument entry must declare all of the following fields. The config loader validates every field at startup and raises `ConfigValidationError` identifying the instrument and missing field for any violation.

```yaml
instruments:
  - symbol: "GC=F"                   # yfinance ticker
    name: Gold Futures                # human-readable display name
    asset_class: commodity            # one of: commodity, equity, index, fx
    timeframe: 1d                     # one of: 1d, 1wk
    source: yfinance                  # data source for Phase 1
    session_timezone: America/New_York # IANA timezone; validated at load time
    adjusted_prices: true             # boolean; drives the adjusted column in curated data
    # ig_epic: CS.D.GOLD.CFD.IP       # required for Phase 2 — uncomment when available
```

`asset_class` must be one of `{commodity, equity, index, fx}`. Any other value causes a `ConfigValidationError` at startup. `session_timezone` must be a valid IANA identifier verified against `zoneinfo.available_timezones()`.

---

## 8. Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.11 | Minimum version. Uses `zoneinfo`, `dataclasses`, `match` statements. |
| DataFrame library | pandas | All DataFrames are `pd.DataFrame`. polars is explicitly excluded. |
| Research data | yfinance | Free, no auth, daily OHLCV. Phase 1 only. |
| Live data | IG Streaming API | Lightstreamer-based. Phase 2+. Replaces yfinance for execution timing. |
| Broker | IG REST API | Spreadbetting (UK). Supports long and short on all instruments. |
| LLM | Anthropic Claude API | Model configured in `local.yaml`. Default: `claude-opus-4-6`. |
| Dashboard | Streamlit | Multi-page app. Runs locally. Remote access via Tailscale. |
| Charts | Plotly | Interactive zoom/pan in Streamlit. Static matplotlib charts are not used. |
| Storage | Parquet / pyarrow | All persistent DataFrames. JSON for backtest summaries and LLM cache. |
| Config | YAML / python-dotenv | YAML for structured config; `.env` for secrets only. |
| Testing | pytest + pytest-cov | Test runner. Coverage reports configured in `pyproject.toml`. |
| Linting | Ruff | Replaces flake8 + isort. |
| Formatting | Black | Applied by CI and pre-commit. |
| Remote access | Tailscale | iPhone dashboard access. No cloud deployment or port forwarding. |

**Explicitly removed dependencies:**

| Package | Reason |
|---|---|
| backtrader | Replaced by the custom backtesting engine. Adding a second framework creates ambiguity about which is authoritative. |
| polars | Creates confusion about which DataFrame library the project uses. The answer is pandas. |
| scikit-learn | Implies ML capability that is explicitly out of scope for Phases 1–2. |

---

## 9. Configuration Model

### `config/instruments.yaml`

Single source of truth for the instrument watchlist. Adding an instrument here is sufficient for all workflows to include it — no code change required. See Section 7 for the full schema.

### `config/strategies/<name>.yaml`

All parameters for a strategy instance. The strategy loader reads this file and instantiates the strategy class. Every required parameter missing from this file raises `ConfigValidationError`.

Example for `sma_cross.yaml`:

```yaml
strategy: SmaCrossStrategy
params:
  fast_window: 20
  slow_window: 50
  rsi_period: 14
  rsi_overbought: 70
  rsi_oversold: 30
  rsi_filter_enabled: true
  atr_multiplier: 2.0        # ATR-based stop distance (Phase 2)
  rr_ratio: 2.0              # Minimum risk/reward to present signal to operator
  oos_ratio: 0.2             # Proportion of date range held back for OOS validation
  exit_threshold: 0          # signal value below which an open long is exited
```

### `config/environments/local.yaml`

Runtime behaviour, paths, capital assumptions, and LLM configuration. Not secrets.

```yaml
data:
  root: data/

capital:
  initial_cash: 100000.0

risk:
  risk_per_trade_pct: 1.0
  default_stop_pct: 0.02
  daily_loss_limit_pct: 3.0    # Phase 3
  max_exposure_pct: 25.0       # Phase 3
  max_open_positions: 5        # Phase 3

backtesting:
  commission_bps: 5.0
  slippage_bps: 2.0
  risk_free_rate: 0.0

llm:
  provider: claude             # or: stub
  model: claude-opus-4-6
  max_tokens: 500
  timeout_seconds: 30

ig:                            # Phase 2
  retry_attempts: 3
  retry_backoff_base: 2
  timeout_seconds: 30
```

### `.env` — secrets only

```dotenv
# IG credentials
IG_API_KEY=
IG_USERNAME=
IG_PASSWORD=
IG_ACCOUNT_ID=
IG_ENVIRONMENT=demo            # "demo" or "live"

# Anthropic
ANTHROPIC_API_KEY=
```

`.env` is never committed to git. Two template files are provided:

- `.env.demo` — populated with demo credentials; `IG_ENVIRONMENT=demo`.
- `.env.live` — populated with live credentials; `IG_ENVIRONMENT=live`.

**Demo vs live switch:** Copy the appropriate template to `.env`. No code change is required. The `IgBrokerAdapter` reads `IG_ENVIRONMENT` at initialisation and selects the correct endpoint. The dashboard banner reflects the active environment on every page.

---

## 10. Security and Secrets

### Rules

1. `.env` is listed in `.gitignore` and is never committed. This is enforced and not optional.
2. Separate `.env.demo` and `.env.live` template files hold credentials for each environment. Neither is committed with real credentials.
3. The Settings page in the Streamlit dashboard does not expose any credential fields.
4. The order audit log at `logs/orders.log` logs all IG API requests and responses with credentials redacted.

### Three-layer live order guard

Accidental live order placement is prevented by three independent mechanisms:

1. **Dashboard header banner.** All pages display a persistent banner: `DEMO ACCOUNT` (blue) when `IG_ENVIRONMENT=demo` and `LIVE ACCOUNT — REAL MONEY` (red) when `IG_ENVIRONMENT=live`. The operator sees this before any action.
2. **Separate credential files.** Demo and live credentials are stored in separate files (`.env.demo` and `.env.live`). Switching to live requires a deliberate file copy action, not a single field edit.
3. **Confirmation dialog.** Every order submission requires two explicit operator actions: clicking Approve on the signal row and then confirming the position size in a modal dialog. There is no single-click path to order placement.

Additionally, `IgBrokerAdapter.place_order()` raises `EnvironmentMismatchError` if the adapter's configured environment does not match the endpoint. This guard is not overridable at call time.

---

## 11. Testing Strategy

### Philosophy

Tests verify behaviour at the function level. There is no mocking of the data layer — tests that involve Parquet files use real Parquet files written to a temporary directory. This keeps tests honest about schema conformance and serialisation.

### Unit tests — pure functions

Target: all functions in the features, strategies, and backtesting layers.

- **Indicators:** SMA warm-up count, RSI bounds `[0, 100]`, MACD column presence, short-series rejection.
- **Strategy signal contract:** missing `signal` column raises, values outside `{-1, 0, 1}` raise, warmup bars are zero, crossover bars are exact.
- **RSI filter:** overbought suppresses buy signal, oversold suppresses sell signal, disabled filter allows both.
- **Backtest engine:** no-lookahead assertion (signal on bar N, position on bar N+1), short position profits on falling market, zero-cost run equals market return, higher turnover incurs higher total cost.
- **Metrics:** Sharpe ratio and max drawdown verified against hand-calculated reference values, undefined metrics return `None` not zero.
- **LLM layer:** cache hit does not call the LLM, cache miss calls and writes, stub returns fixed string, missing API key falls back to stub.

### Integration tests

- **Data ingest pipeline:** `ingest_yfinance_daily` writes raw and curated files; curated file passes schema validation; adjusted flag matches request.
- **Backtest end-to-end:** load curated Parquet, generate signals, run backtest, write results, verify summary JSON and trades Parquet on disk.

### Test configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--tb=short"
```

Coverage is reported with `pytest-cov`. The target is 100% coverage of critical paths: signal generation pipeline, backtest engine core loop, cost application, no-lookahead enforcement, position sizing formula, OOS validation thresholds. 80% overall line coverage target. Coverage is measured by pytest-cov and reported on each test run.

---

## 12. Phase Roadmap Summary

### Phase 1 — Research Platform

**What gets built:** Data ingestion pipeline, curated bar schema, features layer (SMA, RSI, MACD), `SmaCrossStrategy` with RSI filter, backtest engine (long/flat/short, cost model, no-lookahead), LLM explanation service with caching, Streamlit dashboard (Dashboard, Charts, Backtests, Settings pages), structured logging.

**Exit criteria:** All Phase 1 tests pass. All five commodity instruments ingest successfully. Dashboard renders signal data from local Parquet files. One backtest run produces summary JSON and trades Parquet. LLM explanation renders for at least one non-neutral signal.

**Broker connectivity:** None. The execution layer exists as a stub only.

---

### Phase 2 — IG Demo Integration

**What gets built:** `IgBrokerAdapter` with session management, signal state management (`SignalStore`, `SignalRecord`, `SignalStatus`), position sizer, signal approval workflow in the dashboard (Approve/Reject buttons, confirmation modal, position size override), IG Streaming adapter for live candles, positions monitoring panel, trade journal page, push notifications (iPhone via Tailscale), indices added to instrument list.

**Exit criteria:** 30 days of stable paper trading on the IG demo account with no critical defects. All Phase 2 tests pass. Order audit log reviewed. Kill switch tested on demo.

**Live capital at risk:** None. Demo account only.

**Notifications (Phase 2):** `src/trading_lab/notifications/`
- `notifier.py` — abstract `Notifier` base class with `send(title, body)` method.
- `ntfy_notifier.py` — concrete implementation using ntfy.sh (free, no account required).
- `pushover_notifier.py` — alternative implementation using Pushover.
- Configuration in `config/environments/local.yaml`: `notifications.enabled`, `notifications.provider`, `notifications.topic`.
- Triggered by: new signal fired, CLOSE recommendation generated.

---

### Phase 3 — IG Live

**What gets built:** Pre-execution risk checks (daily loss limit, exposure cap, duplicate position guard, stop loss enforcement), kill switch (closes all positions within 60 seconds, sets `halted` flag), live credential switch documentation and checklist, forex instruments added, actual-vs-backtest performance comparison.

**Exit criteria:** `docs/risk-review.md` completed and signed off. Kill switch exercised on demo. First live session: one instrument, minimum position size. Full watchlist expansion after two weeks of stable live operation.

**Notes:** The transition from demo to live is a credential swap in `.env`. No code change is required.

---

## 13. Anti-Patterns

The following patterns are explicitly rejected. Code reviews should treat any instance as a blocking defect.

**Live trading logic in notebooks.** Notebooks are for exploration. A notebook that calls `IgBrokerAdapter.place_order()` is a defect, not a workflow.

**Strategy code coupled to a data vendor.** A strategy must not import `yfinance` or reference vendor-specific column names. Strategies consume the normalised curated schema only. Switching from yfinance to IG historical data must not require changes to any strategy.

**Hidden timezone or adjustment assumptions.** Every timestamp is UTC-aware. The `adjusted` flag is explicit in the curated schema. Any code that silently assumes a timezone or silently strips the adjusted flag is wrong.

**Signals generated and consumed in the same notebook session.** Signals are written to `data/signals/` before the dashboard reads them. In-memory signal generation with in-memory dashboard rendering hides failures and prevents reproducibility.

**LLM on the critical path.** Any code path where an LLM timeout or API error prevents signal generation, backtest execution, or order placement is a defect. The LLM enriches the dashboard; it never gates it.

**backtrader or polars in the codebase.** `backtrader` has been removed. The custom engine is authoritative. `polars` creates DataFrame library ambiguity; the project uses pandas exclusively.

**Shared mutable state across layers.** Layers communicate via function arguments and Parquet files on disk. A global variable or a class-level mutable attribute shared between the strategy layer and the execution layer is a defect.

**Premature cloud complexity.** The platform runs locally. Before introducing any cloud storage, cloud compute, or cloud deployment, the local workflow must be demonstrably stable and the operational need must be documented. Tailscale handles remote access without cloud infrastructure.

**Hardcoded magic numbers in business logic.** Annualisation constants (`252`, `52`), data quality thresholds (`5%` null close limit), and risk parameters must be named constants or config values, not inline literals. A search-replace must not be required to change a threshold.

**Partial result writes.** Backtest summaries, trade journals, and curated files are written atomically: to a temp file first, then renamed. A failed run must not leave a partial or truncated file that downstream code treats as valid.

---

## 14. Architecture Gaps Register

A living register of known gaps and their resolution status. Update this section as gaps are closed.

| ID | Gap | Status | Resolution |
|---|---|---|---|
| GAP-001 | BacktestConfig missing symbol/timeframe/date range | Open | Add fields before Phase 1 backtest work |
| GAP-002 | No tests/ directory | Open | Create in first Phase 1 step |
| GAP-003 | Signal contract not validated in base class | Open | Add post-call validation to Strategy ABC |
| GAP-004 | Engine clips signal=-1 to 0 | Open | Fix before any short-side backtest |
| GAP-005 | adjusted flag absent from curated Parquet | Open | Fix in transforms.py |
| GAP-006 | backtrader in dependencies | Open | Remove from pyproject.toml |
| GAP-007 | instruments.yaml contains SPY not commodities | Open | Replace with Phase 1 instruments |
| GAP-008 | No structured logging | Open | Add to all scripts and ingest pipeline |
| GAP-009 | polars and scikit-learn in dependencies | Open | Remove from pyproject.toml |
| GAP-010 | IG epic mapping missing from instruments.yaml | Phase 2 prereq | Add before Phase 2 begins |
| GAP-011 | Signal persistence not implemented | Open | Implement data/signals/ write in Phase 1 |
