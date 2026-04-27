# Trading Lab — Requirements

**Document status:** Active
**Supersedes:** `docs/requirements-phase1.md`
**Date:** 2026-03-31
**Author:** Requirements Analyst

---

## Table of Contents

1. [Scope and Phase Structure](#1-scope-and-phase-structure)
2. [Confirmed Design Decisions](#2-confirmed-design-decisions)
3. [Phase 1 — Core Research and Signal Generation](#3-phase-1--core-research-and-signal-generation)
   - 3.1 [Data Ingestion and Normalisation](#31-data-ingestion-and-normalisation)
   - 3.2 [Signal Generation](#32-signal-generation)
   - 3.3 [Backtesting and Evaluation](#33-backtesting-and-evaluation)
   - 3.4 [Watchlist Management](#34-watchlist-management)
   - 3.5 [Streamlit Dashboard — Phase 1](#35-streamlit-dashboard--phase-1)
   - 3.6 [Non-Functional Requirements](#36-non-functional-requirements)
   - 3.7 [LLM Signal Explanation](#37-llm-signal-explanation)
   - 3.8 [Stop Loss and Take Profit Recommendations](#38-stop-loss-and-take-profit-recommendations)
   - 3.9 [Exit Signal Recommendations](#39-exit-signal-recommendations)
   - 3.10 [Signal Quality and Intelligence](#310-signal-quality-and-intelligence)
   - 3.11 [Risk Management](#311-risk-management)
   - 3.12 [Market Context](#312-market-context)
   - 3.13 [Strategy Validation](#313-strategy-validation)
4. [Phase 2 — IG Demo Account, Paper Trading, Indices, Signal Approval Workflow](#4-phase-2--ig-demo-account-paper-trading-indices-signal-approval-workflow)
   - 4.1 [IG API Integration](#41-ig-api-integration)
   - 4.2 [Signal Approval Workflow](#42-signal-approval-workflow)
   - 4.3 [Paper Trade Execution and Position Tracking](#43-paper-trade-execution-and-position-tracking)
   - 4.4 [Trade Journal and Signal History](#44-trade-journal-and-signal-history)
   - 4.5 [Streamlit Dashboard — Phase 2 Additions](#45-streamlit-dashboard--phase-2-additions)
   - 4.6 [Non-Functional Requirements — Phase 2](#46-non-functional-requirements--phase-2)
5. [Phase 3 — IG Live Account, Forex, Live Risk Controls](#5-phase-3--ig-live-account-forex-live-risk-controls)
   - 5.1 [Live Order Placement](#51-live-order-placement)
   - 5.2 [Live Position and Account Monitoring](#52-live-position-and-account-monitoring)
   - 5.3 [Risk Controls for Live Capital](#53-risk-controls-for-live-capital)
   - 5.4 [Forex Expansion](#54-forex-expansion)
   - 5.5 [Streamlit Dashboard — Phase 3 Additions](#55-streamlit-dashboard--phase-3-additions)
   - 5.6 [Non-Functional Requirements — Phase 3](#56-non-functional-requirements--phase-3)
6. [Phase 4 — Automated Execution (stub)](#6-phase-4--automated-execution-stub)
   - 6.1 [Automated Pipeline](#61-automated-pipeline)
   - 6.2 [Guardrails](#62-guardrails)
   - 6.3 [Notifications and Audit Trail](#63-notifications-and-audit-trail)
   - 6.4 [Demo Validation Gate](#64-demo-validation-gate)
7. [Discretionary Workflow — End to End](#7-discretionary-workflow--end-to-end)
8. [Gaps and Contradictions](#8-gaps-and-contradictions)
9. [Assumptions Register](#9-assumptions-register)
10. [Open Questions](#10-open-questions)
11. [Dependency Map](#11-dependency-map)

---

## 1. Scope and Phase Structure

### Phase 1 — Core Research (no broker connectivity, no execution)

In scope:
- Fetching and persisting market data via yfinance
- Normalising raw data into the project bar schema
- Generating rule-based signals (SMA crossover with RSI filter)
- Running backtests on normalised historical data with explicit cost assumptions
- Reporting backtest performance metrics
- Managing a watchlist via YAML configuration
- Streamlit dashboard: signal table, price charts with indicator overlays, portfolio summary, data refresh trigger
- Persisting computed signals to disk so the dashboard reads the latest results from files, not in-memory state

Out of scope:
- Any broker API integration beyond the existing execution stub
- Live order placement in any form (paper or live)
- Position-state-dependent risk controls that require open positions or trade journal state
- Machine learning or statistical models
- Portfolio optimisation or mean-variance allocation
- Cloud storage or deployment
- Real-time streaming data
- Trade journal (requires position state — deferred to Phase 2)
- Signal history persistence and vs-actual tracking (deferred to Phase 2)
- Instrument correlation analysis (deferred — depends on having a clean multi-instrument dataset first)
- Exposure summary with deployed capital (requires execution layer — deferred to Phase 2)

### Phase 2 — IG Demo Account (paper trading, indices, signal approval, no live capital at risk)

In scope:
- Authenticating to IG demo account via REST API
- Submitting paper orders to IG demo account in response to user-approved signals
- Monitoring open demo positions via IG Streaming API
- Signal approval workflow in the Streamlit dashboard (approve/reject buttons)
- Trade journal persisted to disk
- Signal history persistence (what was recommended vs what happened)
- Exposure summary (demo account positions)
- Live market data via IG Streaming API replacing yfinance for execution timing
- Adding indices instruments to the watchlist and signal pipeline

Out of scope:
- Any action against the IG live account
- Automated execution without user approval
- Forex instruments (Phase 3)

### Phase 3 — IG Live Account (real capital, forex, live risk controls)

In scope:
- Switching from demo to live IG credentials via a single config/env change
- Enforcing pre-execution risk controls (position limits, daily loss limit, exposure cap)
- Adding forex instruments to the watchlist and signal pipeline
- Actual vs backtest performance tracking
- Kill switch to halt all activity within 60 seconds

Out of scope:
- New asset classes beyond forex
- Fully automated execution without user approval — deferred to Phase 4

---

## 2. Confirmed Design Decisions

The following decisions are fixed constraints for all phases. Requirements must not contradict them.

| Decision | Detail |
|---|---|
| Trading style | Discretionary. System recommends; user approves every trade before execution. |
| Broker | IG spreadbetting (UK). Supports long and short on all instruments. |
| Demo account | Identical API to live. Single credential swap to switch environments. Demo is mandatory before live. |
| Phase 1 instruments | Gold (GC=F), Oil (CL=F), Silver (SI=F), Copper (HG=F), Natural Gas (NG=F) — all commodities. |
| Phase 2 instruments | Add indices. |
| Phase 3 instruments | Add forex. |
| Timeframe | Daily bars primary, weekly bars secondary. |
| Holding period | Days to weeks. |
| Signal approach | Rule-based: SMA crossover + RSI filter. ML is a later-phase concern. |
| Research data source | yfinance (daily OHLCV, free, no auth). |
| Live data source | IG Streaming API (real-time candles, bid/ask, account feed). |
| Application type | Streamlit dashboard, Python, browser-based, runs locally. |
| Storage | Parquet files on local disk. |
| Short selling | IG spreadbetting supports shorts. The backtest engine must support short-side simulation from Phase 1 even though the Phase 1 engine starts long/flat. Short execution requires Phase 3. |
| LLM provider | Configurable. Default: Gemini 2.0 Flash (free tier via Google AI Studio, ~1,500 req/day). Supported values for `llm.provider` in `config/environments/local.yaml`: `gemini`, `deepseek`, `openai`, `claude`. Single provider selected per run; no runtime fallback chain between providers. |

---

## 3. Phase 1 — Core Research and Signal Generation

### 3.1 Data Ingestion and Normalisation

#### Objective

Fetch market data from yfinance, persist it in raw and curated form, and guarantee the curated dataset conforms to a fixed schema before any downstream component consumes it.

---

#### REQ-DATA-001 — Raw persistence

**Requirement:** The ingestion pipeline must write the source-shaped yfinance payload to `data/raw/<symbol>_<interval>_<source>.parquet` before any transformation is applied.

**Acceptance criteria:**
- The raw file exists on disk after a successful ingest run.
- The raw file is not modified by the normalisation step.
- A second ingest run for the same symbol and interval overwrites the existing raw file and logs the overwrite at INFO level.
- The raw file write is atomic: if the download fails, the existing raw file is not truncated or removed.

**Assumption A-001:** Overwrite-on-refresh is acceptable. Versioned raw file history is not required in Phase 1.

---

#### REQ-DATA-002 — Curated schema

**Requirement:** The curated dataset for any instrument must conform to the schema `timestamp, open, high, low, close, volume, symbol, source, adjusted`, where `timestamp` is a timezone-aware UTC datetime.

**Acceptance criteria:**
- A schema validation function raises a descriptive error if any required column is absent, naming the missing column.
- `timestamp` values are UTC-aware `datetime64[ns, UTC]`; a unit test asserts this dtype explicitly.
- `symbol` and `source` columns are populated from the ingest request parameters, not inferred from filenames.
- No rows with a null `close` price are written to the curated file.
- The `adjusted` column is a boolean populated from `MarketDataRequest.adjusted`, not hardcoded.

---

#### REQ-DATA-003 — Adjusted vs unadjusted flag

**Requirement:** Every curated file must carry a boolean `adjusted` column indicating whether prices are split- and dividend-adjusted.

**Acceptance criteria:**
- The `adjusted` column exists in the curated Parquet schema (see REQ-DATA-002).
- The flag is set from `MarketDataRequest.adjusted`.
- A strategy that declares it requires adjusted prices raises an error if passed a curated DataFrame where `adjusted` is `False`.
- For Phase 1 all ingest requests use `adjusted=True`; any attempt to write `adjusted=False` data must log a warning.

**Assumption A-002:** All Phase 1 data is fetched adjusted. Unadjusted prices have no Phase 1 use case. This is a schema invariant for now, enforced via the warning above rather than a hard constraint to allow future flexibility.

---

#### REQ-DATA-004 — Scheduled daily refresh

**Requirement:** A script `scripts/ingest_market_data.py` must exist that, when run with no arguments, refreshes market data for all instruments listed in `config/instruments.yaml`.

**Acceptance criteria:**
- Running the script with no arguments processes every instrument in the YAML in sequence.
- If yfinance returns no data for a symbol, the script logs the failure with the symbol name at ERROR level and continues processing remaining symbols — it does not abort.
- The script exit code is non-zero if any symbol failed to ingest.
- The script does not delete an existing curated file before confirming the new download is non-empty.
- Running the script twice for the same symbol and date produces a curated file identical to a single run (idempotency).

**Assumption A-003:** The schedule trigger (cron, Task Scheduler, manual) is outside this requirement's scope. The script must be triggerable from the command line.

---

#### REQ-DATA-005 — Data validation on ingest

**Requirement:** The normalisation step must detect and reject data quality problems before writing the curated file.

**Acceptance criteria:**
- Rows where `close <= 0` are logged as anomalies at WARN level and excluded from the curated output.
- If more than 5% of rows in a downloaded payload have a null `close` value, the ingest raises a `DataQualityError` rather than writing a partially populated curated file. (The 5% threshold is a named constant, not a magic number, so it can be tuned without a search-replace.)
- If the downloaded date range does not overlap with the requested period by at least one bar, the ingest raises a `DataQualityError` with the requested and received ranges in the message.
- Timezone conversion from exchange-local time to UTC is explicit in the transform code, not delegated to pandas defaults.
- A gap in the date range (e.g. missing trading days beyond known market holidays) does not cause the ingest to fail; it logs a WARNING identifying the gap start and end dates.

**Assumption A-004:** The 5% null threshold is a starting point. It should be confirmed by an operator before going to Phase 2.

---

#### REQ-DATA-006 — Multi-timeframe ingestion

**Requirement:** The ingestion layer must support both daily (`1d`) and weekly (`1wk`) intervals for the same symbol, stored as separate files.

**Acceptance criteria:**
- `MarketDataRequest` accepts `interval` values of at least `"1d"` and `"1wk"`.
- Daily and weekly curated files for the same symbol are stored under distinct filenames following the pattern `<symbol>_<interval>_<source>.parquet`.
- A weekly bar dataset for the same symbol and period contains fewer rows than its daily equivalent; a test asserts this relationship.
- Passing an unsupported interval value causes `MarketDataRequest` construction to fail with a `ValueError`, not at download time.

---

#### REQ-DATA-007 — Instrument registry

**Requirement:** `config/instruments.yaml` is the single source of truth for which instruments the system ingests and analyses.

**Acceptance criteria:**
- Adding an instrument to `instruments.yaml` is sufficient for the daily refresh script to include it; no code change is required.
- Each instrument entry must declare: `symbol`, `name`, `asset_class`, `timeframe`, `source`, `session_timezone`, `adjusted_prices`.
- `asset_class` must be one of: `commodity`, `equity`, `index`, `fx`. The config loader raises a `ConfigValidationError` at startup for any other value.
- `session_timezone` is validated as a legal IANA timezone identifier at load time.
- `timeframe` must be one of the intervals permitted by REQ-DATA-006.
- The config loader raises a `ConfigValidationError` identifying the instrument and missing field if any required field is absent.
- Instruments not in `instruments.yaml` cannot be ingested by the refresh script.

**Phase 1 initial instrument list:**

| symbol | name | asset_class |
|---|---|---|
| GC=F | Gold Futures | commodity |
| CL=F | Crude Oil WTI Futures | commodity |
| SI=F | Silver Futures | commodity |
| HG=F | Copper Futures | commodity |
| NG=F | Natural Gas Futures | commodity |

---

### 3.2 Signal Generation

> All requirements in this section assume discretionary mode: the system outputs recommendations; the user decides. No execution path is included in Phase 1.

#### Objective

Allow rule-based strategies to consume normalised bar data and emit a signal column that the backtesting engine and human reviewer can consume without knowledge of the strategy's internals.

---

#### REQ-SIG-001 — Strategy interface contract

**Requirement:** Every strategy must implement the `Strategy` abstract base class, accepting a bars `DataFrame` and returning a signals `DataFrame` with at least a `signal` column added.

**Acceptance criteria:**
- A strategy that does not return a `signal` column causes a `ValueError` before any backtest or display code consumes it. Validation occurs in the base class `generate_signals` wrapper, not in each subclass.
- The `signal` column contains only integer values from `{-1, 0, 1}`. Any other value causes a `SignalValidationError`.
- A strategy does not perform file I/O, network calls, or broker API calls. A unit test confirms that `generate_signals` can be called with a static in-memory DataFrame and zero external dependencies.
- Strategy parameters are accepted at construction time and never read from global state or environment variables inside `generate_signals`.

---

#### REQ-SIG-002 — Strategy parameterisation via YAML

**Requirement:** Strategy parameters must be loadable from a YAML file in `config/strategies/`, with no parameter values hardcoded in strategy classes that contradict the config.

**Acceptance criteria:**
- A loader function reads a strategy YAML file and returns a fully constructed strategy instance with all parameters applied.
- If a required parameter is absent from the YAML file, the loader raises a `ConfigValidationError` identifying the missing field and the strategy name.
- The same strategy class instantiated with two different YAML files produces different signals for the same input data; a test asserts this.
- Default values in constructors are permitted only as fallbacks when no config is provided, not as operational defaults.

---

#### REQ-SIG-003 — SMA crossover strategy (reference implementation)

**Requirement:** `SmaCrossStrategy` must be fully implemented as the reference strategy and must be exercisable end-to-end from a curated Parquet file to a signals DataFrame.

**Acceptance criteria:**
- `SmaCrossStrategy` accepts `fast_window` and `slow_window` as constructor parameters.
- Constructing an instance where `fast_window >= slow_window` raises a `ValueError`.
- Signals are not emitted for the first `slow_window - 1` bars (warm-up period); those rows carry `signal = 0`.
- A buy signal (`signal = 1`) appears on the first bar where `fast_sma` crosses above `slow_sma`.
- A sell signal (`signal = -1`) appears on the first bar where `fast_sma` crosses below `slow_sma`.
- All of the above are verified by unit tests with a synthetic bar dataset where crossover bars are precisely known.

---

#### REQ-SIG-004 — RSI filter

**Requirement:** `SmaCrossStrategy` must support an optional RSI filter that suppresses buy signals when RSI is above an overbought threshold and suppresses sell signals when RSI is below an oversold threshold.

**Acceptance criteria:**
- The strategy accepts `rsi_period`, `rsi_overbought`, and `rsi_oversold` as constructor parameters.
- When `rsi_filter_enabled=True`, a crossover buy signal is set to `0` if the RSI at that bar is at or above `rsi_overbought`.
- When `rsi_filter_enabled=True`, a crossover sell signal is set to `0` if the RSI at that bar is at or below `rsi_oversold`.
- When `rsi_filter_enabled=False`, signals are emitted purely on the crossover condition with no RSI check.
- Default values are: `rsi_period=14`, `rsi_overbought=70`, `rsi_oversold=30`.
- A unit test verifies that a buy signal is suppressed when RSI is 72 and `rsi_overbought=70` with the filter enabled.
- A unit test verifies the same crossover event is not suppressed when the filter is disabled.

---

#### REQ-SIG-005 — Signal output metadata

**Requirement:** The signals DataFrame returned by any strategy must carry enough context for a human reviewer to understand what generated the signal without reading strategy source code.

**Acceptance criteria:**
- The signals DataFrame contains at minimum: `timestamp`, `close`, `signal`.
- For `SmaCrossStrategy`, the columns `fast_sma`, `slow_sma`, and `rsi` (when filter is enabled) are retained in the output.
- A `position_change` column is present: `1` on entry (signal transitions from 0 or -1 to 1), `-1` on exit (signal transitions from 1 to 0 or -1), `0` on all other bars.

---

#### REQ-SIG-006 — Indicator computation (SMA, RSI, MACD)

**Requirement:** The features layer must provide standalone indicator functions for SMA, RSI, and MACD that operate on a price series and return a named Series or DataFrame.

**Acceptance criteria:**
- Each function accepts a `pd.Series` of close prices and a set of period parameters.
- Each function raises a `ValueError` if the input series is shorter than the minimum required length for the given parameters.
- Indicator functions do not modify the input series in place.
- SMA with `window=20` on a 100-bar series produces exactly 81 non-null values (and 19 null warm-up values); a test asserts this.
- RSI with `period=14` produces values in the range `[0, 100]` for all non-null outputs; a test asserts this bound.
- MACD output includes `macd_line`, `signal_line`, and `histogram` columns, not only the MACD line.
- All three functions are covered by unit tests using synthetic price data.

---

#### REQ-SIG-007 - Phase 1 signal persistence

**Requirement:** Every computed Phase 1 signal must be written to a persisted snapshot on disk before the dashboard reads it.

**Acceptance criteria:**
- The latest Phase 1 signal snapshot is written to a stable file path under `data/signals/`.
- The Dashboard page reads the signal table from that persisted snapshot instead of recomputing signals on page load.
- A refresh run overwrites the previous snapshot only after the new signals have been computed successfully.
- The persisted snapshot contains the latest per-instrument signal summary and indicator context needed by the dashboard.

---

### 3.3 Backtesting and Evaluation

#### Objective

Run reproducible simulations of strategy performance on historical curated data, with explicit cost assumptions, no lookahead bias, and a defined set of output metrics saved to disk.

---

#### REQ-BT-001 — Backtest configuration contract

**Requirement:** Every backtest run must be fully described by an explicit configuration object. No backtest parameter may be inferred from runtime state or environment variables.

**Acceptance criteria:**
- `BacktestConfig` must declare: `symbol`, `timeframe`, `start_date`, `end_date`, `initial_cash`, `commission_bps`, `slippage_bps`, `strategy_name`, `strategy_params`.
- Running the same `BacktestConfig` against the same curated dataset on two separate runs produces bit-identical equity curve output.
- A backtest cannot be initiated without a fully populated config; partial configs raise a `ConfigValidationError` at construction time.
- `start_date` must be earlier than `end_date`; construction fails with a `ValueError` otherwise.

**Gap (from Phase 1 existing code):** The current `BacktestConfig` model contains only `initial_cash`, `commission_bps`, and `slippage_bps`. It is missing `symbol`, `timeframe`, `strategy_name`, `strategy_params`, and date range fields. These must be added before this requirement can pass.

---

#### REQ-BT-002 — No-lookahead enforcement

**Requirement:** The backtest engine must not allow a signal generated on bar N to affect the same bar's result. The conceptual execution point is the open of bar N+1, but Phase 1 approximates fills at the next bar close because yfinance daily OHLC data does not provide execution-quality next-bar open fills. A configurable slippage buffer must be applied to that approximation.

**Acceptance criteria:**
- The engine shifts the signal column by one bar before applying it to price series.
- A unit test constructs a synthetic signal series where a signal fires on bar 5 and confirms no position change occurs before bar 6.
- The Phase 1 execution approximation is documented in a module-level docstring in `engine.py` as next-bar close with slippage.
- The slippage buffer is configurable and is applied on every position change.
- The note about next-bar open remains in the documentation as the conceptual execution target for later execution layers.

---

#### REQ-BT-003 — Cost model

**Requirement:** Every backtest must apply a configurable cost deduction on each position change.

**Acceptance criteria:**
- Cost per trade is `(commission_bps + slippage_bps) / 10000` multiplied by the position size.
- A zero-cost backtest (both bps set to 0) produces gross returns equal to market returns for a fully-invested long position across the same period; a test asserts this.
- A test confirms that a strategy producing 100 trades incurs higher total cost than the same strategy producing 10 trades on the same starting equity.
- Cost model does not separately account for bid-ask spread in Phase 1; this simplification is recorded as a named constant comment in the engine.

---

#### REQ-BT-004 — Long, flat, and short support

**Requirement:** The Phase 1 backtest engine must support long positions (`signal=1`), flat (`signal=0`), and short positions (`signal=-1`). IG spreadbetting supports shorts on all instruments; the engine must reflect this.

**Acceptance criteria:**
- `signal=1` produces a long position that benefits from price increases.
- `signal=-1` produces a short position that benefits from price decreases.
- `signal=0` holds cash with no market exposure.
- A test verifies that a strategy with all-short signals on a falling market produces a positive return.
- A test verifies that a strategy with all-short signals on a rising market produces a negative return.
- The engine docstring states explicitly that short positions are supported via IG spreadbetting and does not characterise the engine as "long/flat only".

**Note:** This supersedes the long/flat-only constraint in the previous `requirements-phase1.md` document. That restriction was appropriate as a placeholder before the broker was confirmed. IG spreadbetting supports shorts; the engine must too.

---

#### REQ-BT-005 — Performance metrics

**Requirement:** The backtest reporting module must compute a defined set of performance metrics from an equity curve and trade log.

**Acceptance criteria — the following metrics must be computed and returned:**
- Total return (percentage from initial cash to final equity)
- Annualised return (CAGR; annualisation constant determined from `BacktestConfig.timeframe`: 252 for daily, 52 for weekly)
- Annualised Sharpe ratio (risk-free rate from config, defaulting to 0%; annualised using the same constant as CAGR)
- Maximum drawdown (percentage peak-to-trough on the equity curve)
- Maximum drawdown duration (number of bars from peak to recovery, or to end of series if unrecovered)
- Win rate (percentage of closed trades with positive net return after costs)
- Number of trades (round-trip entries and exits counted as one trade; a long entry and subsequent exit = 1 trade)
- Average trade return (mean net return per closed trade after costs)
- Profit factor (gross profit / gross loss; `None` if no losing trades exist)

**Acceptance criteria — computation rules:**
- Sharpe ratio uses daily (or weekly) net returns after costs, not gross returns.
- If fewer than two closed trades exist, win rate, average trade return, and profit factor are returned as `None`, not zero.
- All metrics are computed deterministically from the equity curve DataFrame.
- A unit test verifies Sharpe ratio and max drawdown against a hand-calculated reference equity curve.

---

#### REQ-BT-006 — Backtest result persistence

**Requirement:** Every completed backtest run must save a summary metrics file and a bar-level trade log to `data/backtests/`.

**Acceptance criteria:**
- The summary file is JSON containing all metrics from REQ-BT-005 plus the full `BacktestConfig` as a nested object.
- The trade log is a Parquet file containing at minimum: `timestamp`, `open`, `high`, `low`, `close`, `signal`, `position`, `cost`, `net_return`, `equity`.
- Output filenames encode symbol, timeframe, strategy name, and a UTC run timestamp, e.g. `GC=F_1d_sma_cross_20260331T1200Z_summary.json`.
- If a file with the same name already exists, the run appends a numeric suffix (e.g. `_1`, `_2`) rather than silently overwriting. This behaviour is documented in the engine.
- A backtest that raises an exception mid-run does not write a partial summary file. The summary file is written only after all metrics are computed successfully.

---

#### REQ-BT-007 — Date range filtering

**Requirement:** The backtest engine must accept and enforce explicit start and end dates from `BacktestConfig`.

**Acceptance criteria:**
- Bars outside `[start_date, end_date]` are excluded before the engine runs.
- If the curated dataset within the specified range contains fewer bars than `slow_window * 2`, the backtest raises a `BacktestError` with the bar count and the minimum required.
- The start and end dates used in the run are recorded in the summary output.

---

#### REQ-BT-008 — Annualisation constant by timeframe

**Requirement:** The backtesting engine must select the correct annualisation constant based on the `timeframe` field in `BacktestConfig`.

**Acceptance criteria:**
- `timeframe="1d"` uses 252 trading days per year.
- `timeframe="1wk"` uses 52 weeks per year.
- An unsupported timeframe value raises a `BacktestError` at initialisation, not during metric calculation.
- The constants are defined as named module-level variables (e.g. `ANNUAL_TRADING_DAYS = 252`), not magic numbers inline.

---

### 3.4 Watchlist Management

#### Objective

Allow the user to define a set of instruments of interest that drives data ingestion, signal generation, and chart rendering without code changes.

---

#### REQ-WATCH-001 — YAML-driven instrument list

**Requirement:** `config/instruments.yaml` is the watchlist. Adding or removing an instrument from this file is the only action required to include or exclude it from all Phase 1 workflows.

**Acceptance criteria:**
- The refresh script, signal runner, and dashboard all read from `instruments.yaml`; none maintain their own hardcoded symbol lists.
- Removing an instrument from `instruments.yaml` does not delete its existing data files; it only excludes it from future runs.
- A validation step at startup checks all required fields and raises a `ConfigValidationError` identifying the offending instrument if any required field is missing.

---

#### REQ-WATCH-002 — Portfolio-level signal view

**Requirement:** A function must exist that, given the full instrument list and a target strategy, returns a consolidated signal summary across all instruments by reading the latest persisted signal snapshot from disk.

**Acceptance criteria:**
- The output is a DataFrame with one row per instrument containing at minimum: `symbol`, `name`, `timestamp_of_last_bar`, `signal`, `close`, `fast_sma`, `slow_sma`, `rsi`.
- If a curated data file is absent for an instrument, that instrument appears in the output with `signal=None` and `status="data_missing"`, not as a missing row.
- The function does not trigger a data refresh or recompute signals; it operates on whatever persisted signal snapshot is currently on disk.
- A unit test verifies the `data_missing` behaviour using a mock filesystem.

---

### 3.5 Streamlit Dashboard — Phase 1

#### Objective

Provide a locally-run browser dashboard that surfaces signal recommendations, price charts, backtest summaries, and portfolio state for a human operator reviewing trading opportunities daily.

---

#### REQ-UI-001 — Dashboard layout and navigation

**Requirement:** The Streamlit dashboard must provide navigation between at minimum the following named pages: Dashboard (signal overview), Charts, Backtests, and Settings.

**Acceptance criteria:**
- Each page is reachable from a sidebar or top-level navigation element without modifying source code.
- Navigating between pages does not reset session state on the current page (e.g. a chart selection persists when returning to Charts from Backtests).
- The dashboard displays the date and time of the most recent data refresh in the sidebar on all pages.

---

#### REQ-UI-002 — Signal table (Dashboard page)

**Requirement:** The Dashboard page must display a signal summary table showing the current signal state for all instruments in the watchlist.

**Acceptance criteria:**
- The table contains one row per instrument with the columns: `Symbol`, `Name`, `Last Price`, `Change %` (from prior close), `Signal` (Buy / Sell / Neutral), `Fast SMA`, `Slow SMA`, `RSI`, `Last Updated`.
- `Signal` is displayed with a colour indicator: green for Buy, red for Sell, grey for Neutral.
- Rows where data is missing (no curated file on disk) display a status of `Data Missing` in the Signal column, not an error or blank cell.
- The table is sortable by `Signal` and `Symbol` columns.
- The table reflects the most recently persisted signals snapshot from disk; it does not recompute signals on each page load. A manual refresh button triggers recomputation and writes a new snapshot.

---

#### REQ-UI-003 — Data refresh trigger

**Requirement:** The dashboard must provide a button that triggers a data refresh for all instruments in the watchlist.

**Acceptance criteria:**
- Clicking the refresh button runs the equivalent of `scripts/ingest_market_data.py` for all instruments.
- The dashboard displays a progress indicator during refresh.
- On completion, the dashboard displays a summary: number of instruments successfully refreshed and number that failed, with the failing symbol names.
- If a refresh is already in progress, the button is disabled to prevent concurrent refreshes.
- The last refresh timestamp in the sidebar is updated only if at least one instrument refreshed successfully.

---

#### REQ-UI-004 — Price chart page

**Requirement:** The Charts page must render an interactive price chart with indicator overlays for a user-selected instrument.

**Acceptance criteria:**
- The user selects an instrument from a dropdown populated from `instruments.yaml`.
- The user selects a timeframe (Daily, Weekly) via a selector.
- The chart displays OHLC candlesticks or a line chart (configurable).
- The chart includes a configurable SMA overlay: the user can set fast and slow SMA window values via numeric inputs and the chart updates.
- RSI is displayed in a separate subplot below the price chart.
- MACD (line, signal line, histogram) is displayed in a second separate subplot.
- Any active buy/sell signal events from the most recent strategy run are overlaid on the price chart as markers.
- The date range selector allows at minimum: 3 months, 6 months, 1 year, 2 years, and all available data.
- The chart is rendered using a library capable of interactive zoom and pan (e.g. Plotly). Static matplotlib charts are not acceptable for the dashboard.

---

#### REQ-UI-005 — Backtest results page

**Requirement:** The Backtests page must allow the user to run a backtest for a selected instrument and strategy, and display the result.

**Acceptance criteria:**
- The user selects an instrument, timeframe, start date, end date, strategy, and strategy parameters via form inputs.
- A "Run Backtest" button initiates the backtest using the backtesting engine.
- On completion, the page displays all metrics from REQ-BT-005 in a structured summary card.
- The equity curve is displayed as a line chart.
- The trade log (entry date, exit date, side, entry price, exit price, return %) is displayed as a sortable table.
- If the backtest fails (e.g. insufficient data for the selected date range), the page displays the error message rather than crashing.
- Previous backtest results for the same instrument can be loaded from `data/backtests/` via a file selector dropdown.

---

#### REQ-UI-006 — Portfolio summary panel

**Requirement:** The Dashboard page must include a portfolio summary panel showing instrument-level state across the full watchlist.

**Acceptance criteria:**
- The panel shows: number of active Buy signals, number of active Sell signals, number of Neutral instruments, and number of instruments with missing data.
- The panel does not show actual positions or deployed capital in Phase 1 (no execution layer exists).
- The panel updates when the signal table updates.

---

#### REQ-UI-007 — Settings page

**Requirement:** The Settings page must allow the user to view and modify operational configuration without editing YAML files directly.

**Acceptance criteria:**
- The page displays the current instruments in `instruments.yaml` and their key fields.
- The page displays the current strategy parameters from the active strategy YAML.
- Changes made via the Settings page are written back to the relevant YAML config file on disk.
- The page does not expose or display credential fields (API keys, passwords) — it shows only non-sensitive config.
- Saving an invalid configuration (e.g. a timeframe value not in the permitted set) displays a validation error without writing the file.

---

#### REQ-UI-008 — Dashboard does not block on stale or missing data

**Requirement:** The dashboard must load and render even when curated data files are absent or stale.

**Acceptance criteria:**
- If no curated data exists for any instrument, the dashboard renders with empty or `Data Missing` states rather than raising an unhandled exception.
- The dashboard does not attempt a network call on page load; all displayed data comes from files on disk.
- A stale data warning is displayed if the most recent bar in any instrument's curated file is more than 2 trading days behind the current date.

---

### 3.6 Non-Functional Requirements

#### REQ-NFR-001 — Reproducibility

A backtest run given the same `BacktestConfig` and the same curated Parquet file must produce bit-identical output on any machine running the same Python version and package versions declared in `pyproject.toml`. No random seeds, no system-clock-dependent logic inside the engine.

#### REQ-NFR-002 — Test coverage for core paths

The following code paths must have at least one automated unit test before Phase 1 is considered complete:
- Data normalisation (schema, UTC timestamp, null rejection)
- Strategy signal generation (warm-up period, crossover detection, RSI filter, signal value constraints)
- Backtest engine (lookahead prevention, cost application, short positions, metrics calculation)
- Config loading and validation (missing fields, invalid values)
- Instrument registry loading
- Portfolio signal view (`data_missing` behaviour)

A `tests/` directory must be created as part of Phase 1.

#### REQ-NFR-003 — No secrets in version control

All broker credentials, API keys, and account identifiers must be stored only in `.env` and must never appear in committed files. The `.gitignore` must exclude `.env`. A pre-commit hook or CI check must verify no credential patterns (API key patterns, passwords) appear in staged files.

#### REQ-NFR-004 — Configuration over code

No strategy parameter value may be hardcoded in strategy source files in a way that silently takes precedence over the YAML config. Default values in constructors are permitted only as documented fallbacks.

#### REQ-NFR-005 — Notebooks are not the system of record

No curated data, backtest result, or signal output may exist only inside a notebook. All such outputs must originate from package code or scripts and be written to the defined data directories. Notebooks may read from those directories for additional analysis.

#### REQ-NFR-006 — Ingest script idempotency

Running the data refresh script twice for the same instrument and date produces a curated file identical to the output of a single run.

#### REQ-NFR-007 — Structured logging

All scripts and the backtest engine must emit structured log output (at minimum: timestamp, level, component, message). Logs are written to `logs/` as well as stdout. A failed ingest run must produce a log entry sufficient to diagnose the failure without rerunning the script.

#### REQ-NFR-008 — Dependency resolution

The `backtrader` package is listed in the development environment but the project has built its own backtest engine. Before Phase 1 is closed, a decision must be recorded in this document: either adopt `backtrader` as the engine (and retire the custom engine) or remove `backtrader` from dependencies. The two must not coexist in an ambiguous state.

#### REQ-NFR-LLM-001 — LLM API cost minimisation through caching

LLM API calls must be minimised. Every explanation must be generated at most once per signal per calendar day and persisted to disk. Subsequent dashboard loads on the same day must read from the cache and must not trigger a new API call. The cache must be invalidated automatically when a new signal is generated for the same instrument on a new day.

**Acceptance criteria:**
- A dashboard page load for an instrument that already has a cached explanation for today's signal does not make any outbound API call; a unit test or integration test confirms this using a mock HTTP client.
- The cache file location follows the same directory convention as signal output files (`data/signals/` or equivalent) and uses a consistent naming scheme that encodes instrument symbol and date.
- Explanation cache files are excluded from version control via `.gitignore`.
- Metrics for total LLM API calls per run are logged at `INFO` level so cost can be monitored.

---

#### REQ-OPS-001 — Audit log

**Requirement:** The system must write a structured audit log recording every signal generated, every user action (approve/reject), and every LLM API call, with sufficient detail to reconstruct the decision trail for any instrument on any day.

**Acceptance criteria:**
- Every audit log entry contains at minimum: `timestamp` (ISO 8601 UTC), `instrument` (symbol), `action` (one of: `signal_generated`, `signal_approved`, `signal_rejected`, `llm_call_made`, `llm_call_cached`, `llm_call_failed`), and `values` (a structured dict with action-specific fields, e.g. signal direction, LLM response time, error message).
- Log entries are written to a dedicated structured log file at `logs/audit.log` in JSON-lines format (one JSON object per line).
- Audit log entries are appended; the file is never truncated by application code.
- Log entries older than 90 calendar days are not automatically deleted by application code. Retention management is the operator's responsibility.
- A unit test verifies that a signal generation event produces an audit entry with the correct `action` field and non-null `instrument` and `timestamp` fields.

---

#### REQ-OPS-002 — Data freshness indicator

**Requirement:** The dashboard must display, for each instrument, the timestamp of the last successful data refresh, and must flag any instrument whose data has not been refreshed within the past 24 hours.

**Acceptance criteria:**
- The signal table on the Dashboard page includes a `Last Refreshed` column showing the UTC timestamp of the most recent successful ingest for each instrument.
- Any instrument with a `Last Refreshed` timestamp more than 24 hours before the current system time is highlighted with a visual staleness indicator (e.g. amber background or warning icon).
- The freshness check uses the curated Parquet file's most recent bar timestamp, not the OS file modification time.
- An instrument with no curated file on disk displays `Never` in the `Last Refreshed` column rather than an error or blank cell.
- The 24-hour threshold is a named constant in the dashboard code, not a magic number.

---

#### REQ-OPS-003 — Push notifications (Phase 2)

**Requirement:** When a new trading signal fires, the system must optionally send a push notification to the user's configured device. This is a Phase 2 feature; it is not required for Phase 1 completion.

**Acceptance criteria:**
- Push notification delivery uses a free, no-auth-registration service — either ntfy.sh or Pushover — configured via an environment variable (`PUSH_NOTIFICATION_URL` or equivalent).
- Notifications are enabled/disabled via a boolean flag in `config/settings.yaml` (`notifications.enabled`). Disabling requires no code change.
- A notification payload contains at minimum: instrument name, signal direction (Buy/Sell), and the current close price.
- If the push notification call fails for any reason, the failure is logged at `WARNING` level and does not interrupt signal generation or dashboard rendering.
- When `notifications.enabled` is `false`, no outbound HTTP call to the notification service is made; a unit test asserts this using a mock HTTP client.

**Assumption A-013:** The user's device can receive push notifications from the configured service (ntfy.sh app or Pushover app installed). Network connectivity between the local machine and the notification service is available.

---

#### REQ-OPS-004 — Dark mode

**Requirement:** The Streamlit dashboard must default to dark mode.

**Acceptance criteria:**
- The Streamlit `config.toml` file sets `[theme] base = "dark"` so that dark mode is active on first launch without any user action.
- The dark mode setting is committed to version control so all users of the repository share the same default.
- Chart colours (candlestick bodies, SMA lines, RSI subplot) are visually legible against a dark background — white or near-white backgrounds for chart areas are not used.

---

#### REQ-OPS-005 — Backtest comparison across instruments

**Requirement:** The Backtests page must support running the same strategy configuration across multiple instruments simultaneously and displaying the results in a single comparative table.

**Acceptance criteria:**
- A "Compare Instruments" mode on the Backtests page allows the user to select two or more instruments from the watchlist and run the same strategy YAML configuration against each.
- Results are displayed in a single table with one row per instrument, showing at minimum: instrument name, total return, annualised return, Sharpe ratio, maximum drawdown, win rate, and number of trades.
- The best-performing instrument by total return is highlighted in the results table.
- Each row in the results table is expandable to show the full equity curve for that instrument.
- If the backtest for any instrument fails (e.g. insufficient data), that row displays the error reason rather than crashing the entire comparison run.
- The comparison uses the same `BacktestConfig` parameters (date range, costs, strategy params) for all selected instruments; per-instrument overrides are not supported in this mode.

---

### 3.7 LLM Signal Explanation

#### Objective

After each trading signal is generated, call an LLM API to produce a plain English explanation of why the signal was generated. The explanation is displayed alongside the signal in the Streamlit dashboard. Explanations are cached to disk to avoid repeated API calls on every page load.

---

#### REQ-LLM-001 — LLM explainer interface contract

**Requirement:** The LLM explanation subsystem must be implemented behind an abstract interface so that the underlying LLM provider (Claude API by default) can be swapped without modifying signal generation or dashboard code.

**Acceptance criteria:**
- An abstract base class `SignalExplainer` (or equivalent protocol) declares a single method — e.g. `explain(signal_context: SignalContext) -> str` — with no provider-specific logic.
- `AnthropicSignalExplainer` is the default concrete implementation and uses the Claude API.
- A `FakeSignalExplainer` (or equivalent stub) exists in the test suite and returns a fixed string without making network calls; all unit tests that exercise explanation-adjacent code use this stub.
- Swapping the explainer implementation requires only a configuration change (e.g. a key in `config/settings.yaml` or an environment variable), not a source-code change.

**Assumption:** The Claude API (Anthropic) is available and accessible from the deployment environment. If it becomes unavailable, the graceful-degradation requirement (REQ-LLM-004) applies.

---

#### REQ-LLM-002 — Signal context passed to LLM

**Requirement:** The payload submitted to the LLM for each signal must contain a defined, complete set of fields so the model has enough context to produce an accurate and useful explanation.

**Acceptance criteria:**
- The `SignalContext` object (or equivalent dict/dataclass) passed to the explainer contains all of the following fields: instrument name, signal direction (`LONG`, `SHORT`, or `FLAT`), current close price, SMA 50 value, SMA 200 value, RSI value, recent price trend summary (e.g. a short human-readable string such as "price has risen 4.2% over the past 5 bars"), suggested stop loss price, suggested take profit price, and risk/reward ratio.
- A unit test confirms that a `SignalContext` constructed from a known signals DataFrame row contains all required fields and no field is `None` or `NaN`.
- The explainer implementation must not accept a raw signals DataFrame directly; it must receive only the structured `SignalContext` object, enforcing the boundary between signal generation and explanation logic.

**Assumption:** Stop loss, take profit, and risk/reward ratio are derived from the strategy's output columns (or a dedicated risk module) and are available at the time explanation is requested. If these fields are not yet present in the signal output, the dependent fields must be added to the signal schema before REQ-LLM-002 can be considered complete.

---

#### REQ-LLM-003 — LLM output format and consistency

**Requirement:** The LLM must return a plain English explanation of 3–5 sentences. The explanation must be directionally consistent with the signal it describes and must not contradict the trade direction.

**Acceptance criteria:**
- The prompt sent to the LLM explicitly instructs it to produce between 3 and 5 sentences, in plain English, suitable for a non-technical trader.
- The prompt explicitly instructs the LLM that if the signal is `LONG`, the explanation must not suggest selling or a bearish view, and vice versa for `SHORT`. If the signal is `FLAT`, the explanation must clearly state why no trade action is recommended.
- A post-generation validation step checks that the returned string is non-empty and does not exceed a defined character limit (e.g. 1 000 characters). If the validation fails, the explanation is treated as unavailable and the graceful-degradation path (REQ-LLM-004) is triggered.
- The prompt template is stored in a dedicated file or configuration location (not embedded in the explainer class body) so it can be reviewed and updated without modifying source code.

**Assumption:** The LLM is capable of following the direction-consistency instruction reliably for the signal types produced by `SmaCrossStrategy`. If future strategies produce signals the model cannot contextualise, prompt revision will be required.

---

#### REQ-LLM-004 — Graceful degradation on LLM failure

**Requirement:** If the LLM API call fails for any reason (network error, API error, timeout, validation failure), the signal must still be displayed in the dashboard. The explanation field must degrade gracefully to a static fallback message.

**Acceptance criteria:**
- When the LLM call raises any exception or returns an invalid response, the explainer catches the error, logs it at `WARNING` level with the instrument name and error detail, and returns the string `"Explanation unavailable."`.
- The dashboard renders the fallback string in place of the explanation without raising an exception or showing a stack trace to the user.
- A unit test simulates an API failure (using the stub or a mock that raises an exception) and confirms the fallback string is returned without propagating the exception.
- The fallback string `"Explanation unavailable."` is defined as a constant in the explainer module, not duplicated across multiple call sites.

**Assumption:** A failed explanation does not invalidate the signal itself. Signal correctness is independent of the LLM subsystem.

---

#### REQ-LLM-005 — Per-day, per-signal explanation caching

**Requirement:** Explanations must be generated at most once per signal per calendar day and cached to disk. The dashboard must read from the cache on all subsequent loads within the same day rather than calling the LLM API again.

**Acceptance criteria:**
- After the explainer produces a new explanation, it writes the result to a cache file at a path that encodes the instrument symbol and the signal date (e.g. `data/signals/explanations/GC=F_2026-04-03.json`).
- On a subsequent request for the same instrument and date, the explainer reads from the cache file and returns its content without making an API call.
- If the cache file is absent or corrupted (unparseable), the explainer falls back to calling the API and overwrites the cache with the new result.
- Cache files are human-readable JSON containing at minimum: `instrument`, `date`, `signal_direction`, `explanation`, `generated_at` (ISO 8601 timestamp).
- A unit test verifies that a second call for the same instrument and date does not invoke the underlying API client (asserted via mock call count).

**Assumption:** Signal outputs are regenerated daily by the scheduled refresh script (REQ-DATA-004). If a new signal is generated on the same calendar day for the same instrument (e.g. due to a manual re-run), the cache for that date is overwritten with a fresh explanation.

---

#### REQ-LLM-006 — API key management

**Requirement:** The Anthropic API key must be stored only in `.env` as `ANTHROPIC_API_KEY` and must never be hardcoded in source code, config files, or committed files.

**Acceptance criteria:**
- The explainer reads the API key exclusively from the `ANTHROPIC_API_KEY` environment variable at runtime.
- If `ANTHROPIC_API_KEY` is absent or empty when the explainer is instantiated, a `ConfigurationError` is raised with a message that identifies the missing variable by name.
- The existing REQ-NFR-003 pre-commit hook or CI check covers this variable name as a forbidden pattern in staged files.
- A unit test confirms that instantiating the explainer without `ANTHROPIC_API_KEY` set raises `ConfigurationError` (using `monkeypatch` or equivalent to clear the variable).

**Assumption:** `.env` is already excluded from version control by `.gitignore` as required by REQ-NFR-003. No additional `.gitignore` changes are needed solely for this feature.

---

#### REQ-LLM-007 — Dashboard display of explanations

**Requirement:** The Streamlit dashboard must display the LLM-generated explanation alongside the signal for each instrument, within the existing signal table or as an expandable detail view.

**Acceptance criteria:**
- Each row in the signal table on the Dashboard page includes an accessible explanation — either inline (truncated with a "show more" expander) or via a per-row expander component.
- The explanation is displayed as plain text; no Markdown or HTML rendering of the LLM output is permitted (to avoid injection risk from unexpected model output).
- If the explanation for a given instrument is the fallback string `"Explanation unavailable."`, it is displayed in a visually distinct style (e.g. muted text or an italicised note) so the user can distinguish a missing explanation from a real one.
- The explanation display does not trigger a new LLM API call during a dashboard page load; it reads exclusively from the cache layer provided by REQ-LLM-005.
- A manual smoke test confirms that an instrument with a cached explanation renders correctly, and an instrument without a cache (simulated by deleting the cache file) renders the fallback string without a dashboard error.

**Assumption:** The Streamlit dashboard is used by a single user on a local machine (consistent with OQ-UI-001). Concurrent read/write access to the explanation cache is not a concern in Phase 1.

---

#### REQ-LLM-008 — News headlines as LLM context

**Requirement:** The LLM explanation subsystem must fetch recent news headlines for each instrument at the time of data refresh and include up to five headlines as additional context in the prompt sent to the LLM.

**Acceptance criteria:**
- News headlines are fetched using yfinance's built-in news feed (`Ticker.news`) — no additional API key, third-party service, or package beyond the existing yfinance dependency is required.
- Up to five of the most recent headlines are selected, ordered by recency (newest first). If fewer than five headlines are available, all available headlines are used.
- Each headline passed to the LLM includes three fields: `title`, `source` (publisher name), and `timestamp` (ISO 8601 UTC).
- News is fetched at the same time as the price data refresh (REQ-DATA-004) and stored in the signal cache file alongside the signal data, so that the LLM receives the news that was current at the time the signal was generated — not news fetched at dashboard load time.
- If yfinance returns no news for an instrument (empty list or API error), the LLM call proceeds without news context. The prompt explicitly notes that no recent news is available rather than omitting the field silently.
- A unit test verifies that when five headlines are available, exactly five are passed to the prompt; and that when zero headlines are available, the prompt contains the "no recent news available" note and makes no reference to specific headlines.

**Assumption A-014:** yfinance's news feed provides headline-level data (title, source, timestamp) that is sufficient for an LLM to form a view. Full article body content is not fetched or passed. The quality of news context depends on yfinance's aggregation of Yahoo Finance's news feed, which may not be comprehensive for all instruments.

---

#### REQ-LLM-009 — News-driven vs technical explanation distinction

**Requirement:** When news headlines are available, the LLM explanation must explicitly distinguish between signal drivers that are purely technical (SMA crossover, RSI) and any corroborating or contradicting news context.

**Acceptance criteria:**
- The prompt instructs the LLM to structure its explanation in two parts when news is available: (1) technical basis — why the signal fired based on price action and indicators; (2) news context — whether recent headlines support, contradict, or are neutral relative to the signal direction.
- When news headlines contradict the signal direction (e.g. bearish news on a buy signal), the explanation must explicitly flag this tension rather than presenting a falsely unified narrative.
- When no news is available, the explanation is purely technical and does not speculate about news that might exist.
- The post-generation validation step (from REQ-LLM-003) applies equally to news-informed explanations; the explanation must still be 3–5 sentences, non-empty, and within the character limit.
- A manual review of at least three generated explanations (with and without news context) is performed before this requirement is considered complete, to confirm the model is following the two-part structure instruction.

**Assumption:** The two-part structure instruction increases prompt complexity. If the configured LLM provider cannot reliably follow the two-part instruction, the prompt template must be revised. This does not change the requirement itself.

---

#### REQ-LLM-010 — Multi-provider support

**Requirement:** The LLM layer must support four providers — Gemini, DeepSeek, OpenAI, and Claude — selectable via a factory function. All four must implement the same `LLMClient` abstract base class.

**Acceptance criteria:**
- An `LLMClient` ABC declares a single abstract method `complete(prompt: str) -> str` with no provider-specific logic.
- A factory function `create_llm_client(config) -> LLMClient` reads `llm.provider` from config and returns the appropriate concrete implementation.
- The factory raises a `ConfigurationError` for any `llm.provider` value not in `{"gemini", "deepseek", "openai", "claude"}`.
- Swapping the active provider requires only changing `llm.provider` in `config/environments/local.yaml`; no source-code change is required.
- A `StubLLMClient` exists in the test suite and returns a fixed string without making network calls; all unit tests that exercise LLM-adjacent code use this stub.
- If the LLM call fails for any reason, the system falls back to `StubLLMClient` behaviour (returns `"Explanation unavailable."`) and does not attempt another provider. The failure is logged at `WARNING` level.

---

#### REQ-LLM-011 — Default provider

**Requirement:** The default LLM provider is Gemini 2.0 Flash, accessed via the Google AI Studio free tier. If `GOOGLE_API_KEY` is absent and `llm.provider` is `gemini`, the system must degrade gracefully rather than raising an unhandled error.

**Acceptance criteria:**
- `llm.provider` defaults to `gemini` when not specified in `config/environments/local.yaml`.
- If `GOOGLE_API_KEY` is absent or empty and `llm.provider` is `gemini`, the system logs a `WARNING` at startup identifying the missing variable by name and substitutes `StubLLMClient` for all LLM calls in that run.
- The `WARNING` message includes the text `"GOOGLE_API_KEY not set"` and states that LLM explanations will be unavailable for that run.
- A unit test verifies that with `GOOGLE_API_KEY` unset and `llm.provider=gemini`, the factory returns a `StubLLMClient` and does not raise an exception.

---

#### REQ-LLM-012 — Provider API key environment variables

**Requirement:** Each supported LLM provider reads its API key from a dedicated environment variable. A missing key for the configured provider is a startup error, except for `gemini` which degrades to a stub (REQ-LLM-011).

**Acceptance criteria:**
- Provider-to-env-var mapping is fixed and documented:
  - `gemini` → `GOOGLE_API_KEY`
  - `deepseek` → `DEEPSEEK_API_KEY`
  - `openai` → `OPENAI_API_KEY`
  - `claude` → `ANTHROPIC_API_KEY`
- If the env var for the configured provider is absent or empty and the provider is not `gemini`, the factory raises a `ConfigurationError` identifying the missing variable by name.
- No provider implementation reads another provider's env var. A unit test for each provider asserts that only the correct env var is consulted.
- All four env var names are covered by the REQ-NFR-003 pre-commit hook as forbidden patterns in staged files.

---

### 3.8 Stop Loss and Take Profit Recommendations

#### Objective

Calculate and display ATR-based stop loss and risk/reward-derived take profit levels with every non-flat signal, stored in cache alongside the signal so downstream components (LLM explainer, dashboard, position sizing) always have access to the levels without recomputing them.

---

#### REQ-SL-001 — ATR-based stop loss calculation

**Requirement:** The signal generation pipeline must compute an ATR-based stop loss distance for every non-flat signal and store the resulting stop level alongside the signal.

**Acceptance criteria:**
- Stop loss distance is calculated as `1.5 × ATR(atr_period)` from the entry price, where `atr_period` defaults to 14 and is configurable per strategy in the strategy YAML file.
- For a LONG signal, the stop loss level is `entry_price - stop_distance`. For a SHORT signal, the stop loss level is `entry_price + stop_distance`.
- The ATR is calculated from the curated bar data using the standard Wilder ATR formula (true range = max of: `high - low`, `|high - prev_close|`, `|low - prev_close|`).
- The computed `stop_loss_level` and `stop_distance` (absolute value) are added as columns to the signals DataFrame output.
- A unit test verifies that for a LONG signal with a known ATR of 10.0 and `atr_multiplier=1.5`, the stop loss level equals `entry_price - 15.0`.
- A unit test verifies that for a SHORT signal the stop is placed above entry price.

**Assumption A-015:** The entry price used for stop/target calculation is the close price of the signal bar. In live execution, the actual fill price will differ; the stop level stored in the cache is an estimate for research and display purposes.

---

#### REQ-SL-002 — Take profit calculation

**Requirement:** The signal generation pipeline must compute a take profit level for every non-flat signal based on a configurable risk/reward ratio and store the resulting target level alongside the signal.

**Acceptance criteria:**
- Take profit distance is calculated as `stop_distance × risk_reward_ratio`, where `risk_reward_ratio` defaults to 2.0 and is configurable per strategy in the strategy YAML file.
- For a LONG signal, the take profit level is `entry_price + take_profit_distance`. For a SHORT signal, the take profit level is `entry_price - take_profit_distance`.
- The computed `take_profit_level` is added as a column to the signals DataFrame output.
- A unit test verifies that with `stop_distance=15.0` and `risk_reward_ratio=2.0`, the take profit distance is 30.0.
- Both `risk_reward_ratio` and `atr_multiplier` are validated at strategy load time: `atr_multiplier` must be positive and non-zero; `risk_reward_ratio` must be ≥ 1.0. A `ConfigValidationError` is raised if either constraint is violated.

---

#### REQ-SL-003 — Dashboard display of stop and target levels

**Requirement:** The signal table on the Dashboard page must display the stop loss level and take profit level for every instrument with an active non-flat signal.

**Acceptance criteria:**
- The signal table adds two new columns: `Stop Loss` and `Take Profit`, showing the computed levels to the same decimal precision as the instrument's close price.
- For instruments with a FLAT signal (`signal = 0`), both columns display `—` (an em-dash or equivalent) rather than a value, blank cell, or zero.
- Both levels are also displayed in the signal detail expander (the same expandable panel used for LLM explanations per REQ-LLM-007).
- The risk/reward ratio is displayed alongside the stop and target (e.g. `R/R: 2.0`), computed from the cached values rather than recalculated in the dashboard.

---

#### REQ-SL-004 — Stop and target persistence in signal cache

**Requirement:** The stop loss level, take profit level, ATR value, and risk/reward ratio must be stored in the signal cache file so they are available to the LLM explainer, dashboard, and position sizing components without recomputation.

**Acceptance criteria:**
- The signal cache file (as defined by REQ-LLM-005) is extended to include the fields: `stop_loss_level`, `take_profit_level`, `atr_value` (the raw ATR at the time of signal generation), `atr_multiplier`, and `risk_reward_ratio`.
- All five fields are present and non-null for every cached signal with direction LONG or SHORT.
- For FLAT signals, the fields are present in the cache schema but set to `null`.
- The `SignalContext` object (REQ-LLM-002) is updated to include `stop_loss_level` and `take_profit_level`, which are read from the cache rather than recomputed.

---

### 3.9 Exit Signal Recommendations

#### Objective

Define a phased approach to exit management: Phase 1 provides display-only stop and target levels for the user to act on manually; Phase 2 adds active monitoring of open positions and programmatic CLOSE recommendations; Phase 3 automates stop placement via the IG API at order entry.

---

#### REQ-EXIT-001 — Phase 1: Display stop and target levels (display only)

**Requirement:** In Phase 1, the stop loss and take profit levels computed by REQ-SL-001 and REQ-SL-002 must be displayed for each active signal. No automated exit monitoring or recommendation is performed. All exit decisions remain with the user.

**Acceptance criteria:**
- Stop loss and take profit levels are visible in the signal table and signal detail panel (satisfied by REQ-SL-003).
- No automated close recommendation is generated in Phase 1.
- No polling of open positions occurs in Phase 1 (no execution layer exists).
- Dashboard documentation or tooltip text on the stop/target columns makes clear that these are reference levels for the user's own position management, not automated instructions.

---

#### REQ-EXIT-002 — Phase 2: Open position tracking for exit monitoring

**Requirement:** In Phase 2, the system must track open positions recorded in the trade journal and continuously evaluate each position against its exit conditions.

**Acceptance criteria:**
- The exit monitoring component reads open trades from `data/journal/trades.parquet` (REQ-JOURNAL-001) to identify positions that have not yet been closed.
- For each open position, the monitor evaluates the following exit conditions on each data refresh (see REQ-EXIT-003 for full condition list).
- The exit monitor runs as part of the scheduled data refresh cycle, not as a separate persistent process.
- A unit test verifies that a position with no exit conditions met produces no CLOSE recommendation.

---

#### REQ-EXIT-003 — Phase 2: Exit condition evaluation

**Requirement:** The exit monitor must evaluate five exit conditions for each open position and generate a CLOSE recommendation when any condition is met.

**Acceptance criteria:**
- The following five conditions are evaluated, and a CLOSE recommendation is generated if any one is true:
  1. **Stop hit:** current close price is at or beyond the stored `stop_loss_level` (at or below for LONG; at or above for SHORT).
  2. **Target hit:** current close price is at or beyond the stored `take_profit_level` (at or above for LONG; at or below for SHORT).
  3. **Opposite signal:** the strategy has generated a signal in the opposite direction to the open position (e.g. a SELL signal fires while a LONG position is open).
  4. **Signal age:** the number of calendar days since the signal was generated exceeds `exit.max_signal_age_days`, which defaults to 10 and is configurable per strategy in the strategy YAML.
  5. **RSI extreme:** for a LONG position, RSI exceeds 80; for a SHORT position, RSI falls below 20. The RSI thresholds are named constants, configurable in the strategy YAML.
- Each CLOSE recommendation records which exit condition triggered it.
- All five thresholds (`stop_loss_level`, `take_profit_level`, opposite signal logic, `max_signal_age_days`, RSI thresholds) are stored per-position and evaluated against current market data at each refresh.
- A unit test for each of the five conditions verifies that the condition correctly triggers a CLOSE recommendation when the threshold is crossed, and does not trigger when the threshold is not yet reached.

---

#### REQ-EXIT-004 — Phase 2: CLOSE recommendation display

**Requirement:** When the exit monitor generates a CLOSE recommendation for an open position, that recommendation must be displayed prominently in the dashboard.

**Acceptance criteria:**
- A CLOSE recommendation is displayed at the top of the Dashboard page, above the signal table, in a visually distinct panel (e.g. a warning-coloured banner or card).
- The panel displays: instrument name, position direction, the exit condition that triggered the recommendation, the current close price, and the stored stop/target levels for reference.
- Multiple simultaneous CLOSE recommendations (for different instruments) are each shown as separate cards or rows within the panel.
- A CLOSE recommendation does not automatically place a close order; it is a recommendation only. User action is required (Phase 2 remains fully discretionary).
- Once the user has manually closed the position (reflected by the trade journal update), the CLOSE recommendation disappears from the panel.

---

#### REQ-EXIT-005 — Phase 2: CLOSE recommendation persistence

**Requirement:** Each CLOSE recommendation generated by the exit monitor must be persisted to the signal cache so it survives a dashboard restart.

**Acceptance criteria:**
- CLOSE recommendations are appended to `data/journal/signals.parquet` (REQ-JOURNAL-002) as a new signal record with `signal = 0` (exit to flat) and a `trigger_condition` field identifying which exit condition fired.
- A CLOSE recommendation for the same position is not duplicated if the exit condition persists across multiple refresh cycles. Only one active CLOSE recommendation per open position exists at any time.
- A unit test verifies that generating two consecutive refresh cycles with the same exit condition results in only one CLOSE recommendation record, not two.

---

#### REQ-EXIT-006 — Phase 2: Exit monitoring configuration

**Requirement:** All thresholds used by the exit monitor must be configurable per strategy in the strategy YAML file and must not be hardcoded.

**Acceptance criteria:**
- The strategy YAML supports the following exit-related fields: `exit.max_signal_age_days` (default 10), `exit.rsi_long_exit_threshold` (default 80), `exit.rsi_short_exit_threshold` (default 20).
- The config loader validates these fields at strategy load time: `max_signal_age_days` must be a positive integer; RSI thresholds must be in the range `[0, 100]`; `rsi_long_exit_threshold` must be greater than `rsi_short_exit_threshold`.
- A `ConfigValidationError` is raised with the offending field name if any constraint is violated.

**Assumption A-016:** The exit monitor operates on daily bar data. Intraday stop-out or target-hit events between daily bars will not be detected until the following day's refresh. This is acceptable for the holding period of days to weeks defined in section 2.

---

#### REQ-EXIT-007 — Phase 3: Automated stop loss placement via IG API

**Requirement:** In Phase 3, when a new order is submitted to the IG live account, the system must automatically attach a stop loss order at the computed `stop_loss_level` (REQ-SL-001) as part of the same order submission call.

**Acceptance criteria:**
- The order submission payload sent to the IG REST API includes a `stopLevel` field set to `stop_loss_level` from the signal cache.
- If the IG API rejects the stop level (e.g. the level is too close to the current market price), the order is cancelled and the user is shown the IG error message and the minimum permitted stop distance before being asked to confirm with a manually adjusted stop.
- The `stopLevel` field is required in the order payload; the order submission function raises a `ValidationError` if it is absent. (This is consistent with REQ-EXEC-003.)
- The automated stop placement is logged in the order audit log (`logs/orders.log`) with the stop level value.
- A manual test on the IG demo account confirms that the stop appears on the open position immediately after order fill.

---

### 3.10 Signal Quality and Intelligence

#### Objective

Augment each signal with a computed confidence score and supporting quality indicators so the user can quickly assess how strong and clean the signal is before deciding to act on it.

---

#### REQ-QUAL-001 — Confidence score

**Requirement:** The signal generation pipeline must compute a confidence score in the range 0–100 for every non-flat signal, based on indicator agreement.

**Acceptance criteria:**
- The confidence score formula is: `base(50) + sma_bonus(0 or 25) + rsi_bonus(0 or 25)`.
  - `sma_bonus = 25` if the absolute SMA gap (`|fast_sma - slow_sma|`) is greater than 1% of the current close price; otherwise 0.
  - `rsi_bonus = 25` if RSI confirms the signal direction: RSI < 40 for a LONG signal, RSI > 60 for a SHORT signal. RSI in the range [40, 60] is treated as neutral and contributes 0 bonus regardless of signal direction.
- For FLAT signals, the confidence score is `null`.
- The `confidence_score` is added as a column to the signals DataFrame and stored in the signal cache.
- The dashboard displays the confidence score as a percentage (e.g. `75%`) alongside each signal.
- A unit test verifies all four possible score combinations: 50, 75 (sma only), 75 (rsi only), 100 (both bonuses).
- The formula constants (base 50, sma bonus 25, rsi bonus 25, sma gap threshold 1%, RSI neutral band 40–60) are defined as named constants, not magic numbers inline.

**Assumption A-017:** The confidence score is a heuristic indicator aid, not a probabilistic forecast. It is displayed as a guide to signal conviction; it does not gate signal display or execution.

---

#### REQ-QUAL-002 — Signal strength indicator

**Requirement:** The dashboard must display the SMA gap as a percentage of the current close price alongside each signal, labelled as signal strength.

**Acceptance criteria:**
- Signal strength is calculated as `(|fast_sma - slow_sma| / close_price) × 100`, expressed as a percentage rounded to two decimal places.
- The `signal_strength_pct` is added as a column to the signals DataFrame and stored in the signal cache.
- The dashboard signal table displays signal strength alongside the signal direction (e.g. `BUY (1.42%)`).
- For FLAT signals, signal strength displays `—` in the dashboard (not zero, which could be misleading).

---

#### REQ-QUAL-003 — Conflicting indicator warning

**Requirement:** When the SMA crossover direction and the RSI reading point in opposite directions, the dashboard must display a warning on that instrument's signal card.

**Acceptance criteria:**
- A conflict is defined as: the SMA crossover fires a LONG signal while RSI is above 60, or the SMA crossover fires a SHORT signal while RSI is below 40.
- When a conflict is detected, a `conflicting_indicators` boolean flag is set to `True` in the signal cache for that instrument.
- The dashboard displays a warning indicator (e.g. a caution icon or amber label `Conflicting Indicators`) on any signal row where `conflicting_indicators` is `True`.
- The LLM explanation prompt (REQ-LLM-002) is updated to include the `conflicting_indicators` flag; when `True`, the LLM is instructed to acknowledge the conflict in its explanation.
- A unit test verifies: LONG signal with RSI = 65 produces `conflicting_indicators = True`; LONG signal with RSI = 35 produces `conflicting_indicators = False`.

---

#### REQ-QUAL-004 — Volatility filter and HIGH VOLATILITY flag

**Requirement:** If the current ATR(14) exceeds twice its 30-day rolling average, the signal must be flagged as HIGH VOLATILITY and a warning displayed in the dashboard.

**Acceptance criteria:**
- The 30-day rolling average of ATR(14) is computed from the curated bar data at the time of signal generation. The rolling window is 30 trading days.
- If `current_atr > 2 × rolling_avg_atr`, a `high_volatility` boolean flag is set to `True` for that signal.
- `high_volatility` and `rolling_avg_atr` are stored as columns in the signals DataFrame and in the signal cache.
- The dashboard displays a prominent `HIGH VOLATILITY` warning on any signal card where `high_volatility` is `True`. The warning must be visually distinct (e.g. a red or amber badge) and not easily overlooked.
- The warning is displayed regardless of signal direction (LONG, SHORT) or confidence score.
- A unit test verifies that `high_volatility = True` when `current_atr = 21.0` and `rolling_avg_atr = 10.0` (ratio = 2.1 > 2.0), and `high_volatility = False` when `current_atr = 19.0` and `rolling_avg_atr = 10.0` (ratio = 1.9 < 2.0).

---

### 3.11 Risk Management

> **ID note:** The requirements in this section use the `REQ-RISK-` prefix for Phase 1 risk management features. Pre-existing Phase 3 live-trading risk controls in section 5.3 have been relabelled `REQ-LRISK-001` and `REQ-LRISK-002` to avoid collision.

#### Objective

Surface portfolio-level risk information in the dashboard during Phase 1 research, and define the position-state-dependent controls that will be activated later once trade and position state exist.

---

**Phase note:** `REQ-RISK-001` and `REQ-RISK-002` are designed in Phase 1 but are deferred from the committed Phase 1 build because they require persisted position state. `REQ-RISK-003` and `REQ-RISK-004` remain committed Phase 1 display features.

#### REQ-RISK-001 - Daily loss limit warning (deferred)

**Requirement:** Once trade journal and position state exist, the system must display a warning and suppress new signal display if the user's configured daily loss limit has been reached, as derived from the trade journal.

**Acceptance criteria:**
- `risk.daily_loss_limit_pct` is configurable in `config/environments/local.yaml` and defaults to 3% of configured capital. Capital is read from `config/environments/local.yaml` as `account.capital`.
- On each dashboard load and data refresh, the system computes today's realised losses from the trade journal (sum of negative `net_return` values for trades with `exit_timestamp` on the current calendar day).
- If today's realised losses equal or exceed `daily_loss_limit_pct x capital`, the dashboard displays a prominent warning banner: `DAILY LOSS LIMIT REACHED - No new signals displayed`.
- When the limit is reached, signal cards for new signals are hidden; existing open positions remain visible.
- The system does not automatically close any position when the limit is reached; it is a display-only warning.
- A unit test verifies that with `daily_loss_limit_pct = 0.03` and `capital = 10000`, a daily loss of 300 GBP triggers the warning and a daily loss of 299 GBP does not.

**Assumption A-018:** Phase 1 does not yet have persisted position state, so this requirement is specified now but remains inactive until Phase 2 signal approval and trade journaling are available.

---

#### REQ-RISK-002 - Maximum open positions limit (deferred)

**Requirement:** Once open position state exists, the system must suppress new signal display when the number of currently open positions equals or exceeds the configured maximum.

**Acceptance criteria:**
- `risk.max_open_positions` is configurable in `config/environments/local.yaml` and defaults to 3.
- Open position count is derived from the trade journal: trades with a non-null `entry_timestamp` and a null `exit_timestamp` are counted as open.
- When open positions equal or exceed `max_open_positions`, the dashboard displays a warning: `MAXIMUM POSITIONS REACHED (N open) - No new signals displayed`, where N is the current count.
- New signal cards are hidden when the limit is reached. Existing open position cards and CLOSE recommendations (REQ-EXIT-004) remain visible.
- A unit test verifies that with `max_open_positions = 3`, three open trades suppresses new signals and two open trades does not.

**Assumption A-019:** Phase 1 does not yet have persisted position state, so this requirement is specified now but remains inactive until Phase 2 open-position tracking is available.

---

#### REQ-RISK-003 - Correlation warning

**Requirement:** When two or more instruments in the watchlist show the same-direction signal simultaneously and their 60-day rolling price correlation exceeds 0.7, the dashboard must display a correlation warning.

**Acceptance criteria:**
- The 60-day rolling pairwise Pearson correlation between instruments is computed from their curated daily close price series using a 60-bar rolling window.
- If two instruments both have an active LONG signal, or both have an active SHORT signal, and their 60-day correlation coefficient exceeds 0.7, a warning is displayed in the dashboard: `CORRELATION WARNING: <Instrument A> and <Instrument B> are highly correlated (r = X.XX) and both show <direction> signals. Consider concentrated risk.`
- The correlation warning is displayed per pair; if three instruments are correlated and all show the same direction, each pair that exceeds the threshold is shown separately.
- The correlation coefficient is recomputed on each data refresh from the curated price data; it is not cached between refreshes.
- The 0.7 threshold is a named constant, not a magic number.
- A unit test using a synthetic dataset verifies that two instruments with `r = 0.75` and both showing LONG produce a warning, and the same pair with `r = 0.65` does not.

**Assumption A-020:** Correlation is computed from daily close prices in the curated dataset. At least 60 bars of overlapping data must exist for both instruments for the calculation to be valid. If fewer than 60 overlapping bars exist, the correlation check is skipped for that pair and a note is logged at DEBUG level.

---

#### REQ-RISK-004 - Position sizing calculator

**Requirement:** The dashboard must display a recommended position size (in units and GBP risk) for each active non-flat signal, computed from configured capital, risk per trade percentage, and the ATR-based stop loss distance.

**Acceptance criteria:**
- Position size formula: `position_size_units = (capital x risk_per_trade_pct) / stop_distance`, where `capital` and `risk_per_trade_pct` are from `config/environments/local.yaml` (default `risk_per_trade_pct = 0.01`), and `stop_distance` is the ATR-based value from REQ-SL-001.
- `GBP_risk` is displayed as `capital x risk_per_trade_pct` (the fixed risk amount for this trade).
- Both `position_size_units` (rounded down to the nearest whole number) and `GBP_risk` are displayed in the signal detail panel for each active LONG or SHORT signal.
- If `stop_distance` is zero or null (which should not occur given REQ-SL-001 but must be guarded against), the position size displays `N/A - stop distance unavailable` rather than a division-by-zero error.
- The calculation inputs (`capital`, `risk_per_trade_pct`, `stop_distance`) are shown transparently in the signal detail panel alongside the result.
- For FLAT signals, no position size is calculated or displayed.
- A unit test verifies: `capital = GBP10,000`, `risk_per_trade_pct = 0.01`, `stop_distance = 50` -> `position_size_units = 2`, `GBP_risk = GBP100`.
### 3.12 Market Context

#### Objective

Provide the user with environmental context — upcoming high-impact economic events, market session status, and signal age — so they can factor external conditions into their review of each signal before acting.

---

#### REQ-CTX-001 — Economic calendar integration

**Requirement:** The dashboard must display warnings for high-impact economic events scheduled within the next 5 trading days that are relevant to the instruments currently showing active signals.

**Acceptance criteria:**
- Economic calendar data is fetched from a free, publicly accessible source (Investing.com RSS feed or equivalent). No paid API key is required.
- Events are filtered to those rated as `high impact` by the source. Medium and low impact events are not displayed.
- Events are matched to instruments by related currency or market (e.g. US economic events are relevant to all USD-denominated commodities in the Phase 1 watchlist: Gold, Oil, Silver, Copper, Natural Gas).
- Relevant events within the next 5 trading days are displayed as a warning on the signal card for the affected instrument: `UPCOMING EVENT: <event name>, <date>, <time UTC>`.
- Calendar data is fetched at the same time as the price data refresh and cached to disk. It is not re-fetched on each dashboard page load.
- If the calendar source is unavailable (HTTP error, timeout, parse failure), the system proceeds without calendar data. Affected signal cards display no event warning. The failure is logged at `WARNING` level.
- A unit test verifies that when calendar fetch fails, no exception propagates to the dashboard and signal cards render normally.

**Assumption A-021:** The Investing.com RSS feed (or chosen equivalent) provides sufficient event data for the five Phase 1 commodity instruments. The feed URL and parsing logic may need adjustment if the source changes format or becomes unavailable.

---

#### REQ-CTX-002 — Market session awareness

**Requirement:** The dashboard must display whether each instrument's primary market is currently open or closed, based on session hours declared in `instruments.yaml`.

**Acceptance criteria:**
- Each instrument entry in `instruments.yaml` declares a `session_open` and `session_close` time (HH:MM) alongside the existing `session_timezone` field.
- The dashboard computes whether the current system time (converted to the instrument's `session_timezone`) falls within `[session_open, session_close]` on a weekday (Monday–Friday). Weekends are always treated as closed.
- Each signal card and each row in the signal table displays a session status badge: `OPEN` (green) or `CLOSED` (grey).
- The session calculation is performed at dashboard render time using the current system clock; it is not cached.
- Public holiday calendars are out of scope for Phase 1. The session logic uses weekday/weekend only.
- A unit test verifies the session logic for at least three cases: a time within session hours (OPEN), a time outside session hours (CLOSED), and a Saturday (CLOSED regardless of time).

**Assumption A-022:** Session hours for the five Phase 1 commodity futures instruments are sufficiently well-known (e.g. COMEX Gold: 18:00–17:00 ET next day, effectively near-24-hour) that the operator can populate `session_open` and `session_close` accurately in `instruments.yaml`. The system does not auto-detect session hours.

---

#### REQ-CTX-003 — Signal age indicator

**Requirement:** The dashboard must display how many days ago the current signal was generated for each instrument, and must flag signals older than 5 days as STALE.

**Acceptance criteria:**
- Signal age is computed as the number of calendar days between the signal generation date (the date of the bar on which the signal fired) and the current system date.
- Each signal card and signal table row displays: `Signal age: N day(s)`.
- Any signal with age ≥ 5 days displays an additional `STALE` badge (amber or red) alongside the age indicator.
- The STALE threshold (5 days) is a named constant in the dashboard code, not a magic number.
- When a signal is generated on the same day as the current date, the displayed age is `0 days` (not `1 day`).
- A unit test verifies: a signal generated 4 days ago is not marked STALE; a signal generated 5 days ago is marked STALE.

---

### 3.13 Strategy Validation

#### Objective

Prevent overfitting by requiring every strategy to be evaluated against a held-back out-of-sample period that was never used during parameter development. Results from both periods are persisted as separate artefacts, compared on a performance degradation metric, and must meet defined thresholds before the strategy is eligible for Phase 2 paper trading.

---

#### REQ-VAL-001 — In-sample / out-of-sample data split

**Requirement:** The backtesting engine must partition each instrument's curated bar data into a contiguous in-sample period and a contiguous out-of-sample period before any strategy parameter is finalised, such that the out-of-sample period is always the most recent data.

**Acceptance criteria:**
- The split ratio is configurable per strategy in the strategy YAML file under the key `validation.oos_ratio` (a float in the range 0.10–0.40 inclusive). The default value when the key is absent is `0.30` (30% out-of-sample).
- The split is applied chronologically: the earliest `(1 − oos_ratio)` fraction of bars form the in-sample period; the most recent `oos_ratio` fraction form the out-of-sample period. No random shuffling of bars is performed at any stage.
- The split is computed from the full curated bar history available at the time the backtest is run. Adding new data via a subsequent ingest extends the out-of-sample window automatically on the next backtest run.
- A validation function raises a `DataSplitError` with a descriptive message if the resulting out-of-sample period contains fewer than 30 bars, naming the instrument and the actual bar count.
- A unit test verifies that for a dataset of 200 bars with `oos_ratio = 0.30`, the in-sample period contains exactly 140 bars and the out-of-sample period contains exactly 60 bars, with no bar appearing in both periods.

**Assumption A-023:** Bar counts rather than calendar dates are used to compute the split boundary. This avoids complexity around weekends and public holidays and is consistent with the existing bar-indexed backtest engine. Operators who require a fixed calendar date boundary may override `validation.oos_split_date` in the strategy YAML; if both `oos_ratio` and `oos_split_date` are present, `oos_split_date` takes precedence and `oos_ratio` is ignored.

---

#### REQ-VAL-002 — Parameter lock before out-of-sample evaluation

**Requirement:** Strategy parameters (e.g. SMA windows, RSI thresholds) must be finalised exclusively on in-sample data. The system must enforce that no parameter is changed or re-tuned after the out-of-sample period has been revealed.

**Acceptance criteria:**
- The backtest runner exposes two explicit execution modes: `mode=in_sample` and `mode=out_of_sample`. The `mode=out_of_sample` run can only be triggered after a `mode=in_sample` run has completed and its results have been written to `data/backtests/` for the same strategy and instrument.
- Attempting to run `mode=out_of_sample` without a prior `mode=in_sample` artefact raises a `ValidationOrderError` with the message: `"Out-of-sample run blocked: no in-sample artefact found for strategy '<name>' on '<symbol>'. Finalise parameters on in-sample data first."`.
- The strategy parameter values are read from the strategy YAML at the start of the in-sample run and written verbatim into the in-sample artefact under the key `parameters_locked`. The out-of-sample run reads `parameters_locked` from the artefact and uses those exact values; it does not re-read the strategy YAML for parameters.
- If the strategy YAML parameter values differ from `parameters_locked` at the time the out-of-sample run is initiated, the run is aborted and a `ParameterDriftError` is raised naming the differing parameter(s) and their in-sample vs current values.
- A unit test verifies that modifying a strategy parameter in the YAML after an in-sample run and then initiating an out-of-sample run raises `ParameterDriftError`.

---

#### REQ-VAL-003 — Separate artefact persistence

**Requirement:** The backtesting engine must save the in-sample and out-of-sample results as two separate Parquet artefacts in `data/backtests/`, with clearly distinct filenames that identify the period type, strategy name, instrument symbol, and run timestamp.

**Acceptance criteria:**
- In-sample artefacts are written to `data/backtests/<strategy_name>_<symbol>_in_sample_<YYYYMMDD_HHMMSS>.parquet`.
- Out-of-sample artefacts are written to `data/backtests/<strategy_name>_<symbol>_out_of_sample_<YYYYMMDD_HHMMSS>.parquet`.
- Each artefact contains at minimum: the bar-level trades DataFrame, the computed performance metrics (`total_return_pct`, `sharpe_ratio`, `max_drawdown_pct`, `win_rate`, `trade_count`), the split boundary bar index (as `split_bar_index`), the period label (`in_sample` or `out_of_sample`), and the `parameters_locked` dict.
- Artefacts are written atomically: a temporary file is written first and renamed into the final path only on successful completion. A failed write does not leave a partial file at the final path.
- A unit test verifies that a complete validation run for one strategy and one instrument produces exactly two files in `data/backtests/` whose names match the expected patterns.

---

#### REQ-VAL-004 — Out-of-sample approval thresholds

**Requirement:** A strategy is eligible for Phase 2 paper trading only if its out-of-sample backtest results meet both of the following thresholds: out-of-sample Sharpe ratio > 0.5 AND out-of-sample maximum drawdown < 25%.

**Acceptance criteria:**
- The thresholds are defined as named constants in `backtesting/validation.py`: `OOS_MIN_SHARPE = 0.5` and `OOS_MAX_DRAWDOWN_PCT = 25.0`. They are not magic numbers and must not be hardcoded elsewhere.
- After the out-of-sample run completes, a `validate_oos_thresholds(results)` function evaluates both conditions and returns a `ValidationResult` object with fields `approved: bool`, `sharpe_ratio: float`, `max_drawdown_pct: float`, and `failure_reasons: list[str]`.
- If either threshold is not met, `approved` is `False` and `failure_reasons` lists each failed condition in plain English (e.g. `"Sharpe ratio 0.38 does not meet minimum threshold of 0.50"`).
- The dashboard displays the approval status prominently on the strategy validation panel: a green `APPROVED FOR PAPER TRADING` badge if both thresholds are met, or a red `NOT APPROVED` badge with the failure reason(s) if not.
- The approval status is written into the out-of-sample artefact under the key `oos_approval`.
- Unit tests verify: a result with Sharpe = 0.6 and drawdown = 20% is approved; a result with Sharpe = 0.4 and drawdown = 20% is not approved (Sharpe failure); a result with Sharpe = 0.6 and drawdown = 28% is not approved (drawdown failure); a result with Sharpe = 0.4 and drawdown = 28% is not approved (both failures listed).

**Assumption A-024:** The Sharpe ratio used for threshold evaluation is computed using daily returns over the out-of-sample period only, with a risk-free rate of zero. This is consistent with the existing backtest engine's Sharpe calculation.

---

#### REQ-VAL-005 — Performance degradation metric and overfitting warning

**Requirement:** The backtesting UI must compute and display a performance degradation metric defined as the difference between the in-sample Sharpe ratio and the out-of-sample Sharpe ratio, and must display a prominent overfitting warning if degradation exceeds 50% of the in-sample Sharpe ratio.

**Acceptance criteria:**
- Performance degradation is computed as `degradation_pct = ((sharpe_in_sample − sharpe_out_of_sample) / |sharpe_in_sample|) × 100`, expressed as a percentage rounded to one decimal place. This metric is stored in the out-of-sample artefact under the key `degradation_pct`.
- The dashboard validation panel displays both Sharpe ratios side-by-side (in-sample and out-of-sample) and the degradation percentage as a labelled metric: `Performance Degradation: X.X%`.
- If `degradation_pct > 50.0`, the dashboard displays a prominent `OVERFITTING WARNING` banner (red background, bold text) on the strategy validation panel. The banner must include the text: `"In-sample Sharpe (X.XX) significantly exceeds out-of-sample Sharpe (X.XX). Strategy may be overfit to historical data."`.
- The dashboard must visually distinguish which chart regions correspond to the in-sample period and which to the out-of-sample period (e.g. a shaded background region, a vertical dividing line, or distinct axis labels). The labels `In-Sample` and `Out-of-Sample` must appear in the chart.
- The degradation metric and any overfitting warning are also written to the out-of-sample artefact for auditability.
- Unit tests verify: in-sample Sharpe = 1.2, out-of-sample Sharpe = 0.5 → `degradation_pct = 58.3%`, overfitting warning displayed; in-sample Sharpe = 1.2, out-of-sample Sharpe = 0.7 → `degradation_pct = 41.7%`, no overfitting warning.

**Assumption A-025:** If `sharpe_in_sample` is zero or negative, the degradation percentage is undefined and is displayed as `N/A` in the dashboard. No overfitting warning is shown in this case, as the in-sample performance itself indicates an unviable strategy.

---

## 4. Phase 2 — IG Demo Account, Paper Trading, Indices, Signal Approval Workflow

Phase 2 begins only after Phase 1 is complete and all Phase 1 tests pass. No Phase 2 code may be merged until Phase 1 is stable. Additionally, a strategy must pass REQ-VAL-004 (out-of-sample approval thresholds) before it is permitted to enter paper trading in Phase 2.

### 4.1 IG API Integration

#### REQ-IG-001 — Authentication

**Requirement:** The system must authenticate to the IG REST API using credentials stored in `.env` and must support both demo and live environments via a single config flag.

**Acceptance criteria:**
- Credentials (`IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, `IG_ACCOUNT_ID`, `IG_ENVIRONMENT`) are loaded from `.env` via `python-dotenv`. No credential is hardcoded or present in YAML.
- `IG_ENVIRONMENT` accepts values `demo` or `live`. Any other value raises a `ConfigValidationError` at startup.
- The IG adapter in `execution/ig.py` exposes a `connect()` method that returns an authenticated session or raises an `AuthenticationError` with a descriptive message.
- A failed authentication attempt logs the failure at ERROR level without printing the password or API key.
- Session tokens are refreshed before expiry using IG's token refresh mechanism; the adapter handles this automatically.

---

#### REQ-IG-002 — Environment isolation

**Requirement:** The system must make it impossible to accidentally execute live orders when configured for demo, and vice versa.

**Acceptance criteria:**
- The IG adapter includes an `environment` property that returns `"demo"` or `"live"`.
- Any order placement call checks `environment` before submitting; attempting to call `place_order` on a demo-configured adapter against a live endpoint raises an `EnvironmentMismatchError`.
- The Streamlit dashboard displays a persistent banner indicating whether the current session is `DEMO` or `LIVE`.
- Switching environment requires changing `IG_ENVIRONMENT` in `.env` and restarting the application. There is no runtime environment toggle.

---

#### REQ-IG-003 — IG REST API error handling

**Requirement:** All IG REST API calls must handle error responses gracefully and surface actionable messages to the operator.

**Acceptance criteria:**
- HTTP 4xx responses (client errors) are raised as a typed `IGAPIError` with the response code and IG error code included.
- HTTP 5xx responses (server errors) are retried up to 3 times with exponential backoff before raising an `IGAPIError`.
- Rate limit errors (HTTP 429) are caught, the retry delay respects the `Retry-After` header if present, and a warning is logged.
- Network timeouts raise an `IGConnectionError`, not an unhandled exception.
- The retry count and backoff parameters are configurable from `config/environments/local.yaml`.

---

#### REQ-IG-004 — Market data via IG (Phase 2 live data)

**Requirement:** For execution timing in Phase 2, live candle data must come from the IG Streaming API, not yfinance.

**Acceptance criteria:**
- The IG Streaming adapter subscribes to OHLC candle updates for all instruments in `instruments.yaml`.
- Candle updates are written to a separate `data/live/` directory using the same schema as curated data (REQ-DATA-002), with `source="ig_streaming"`.
- The dashboard's data refresh indicator distinguishes between yfinance (historical/research) and IG Streaming (live) data sources.
- If the IG Streaming connection drops, the adapter attempts reconnection up to 5 times with exponential backoff and logs each attempt. After 5 failures it raises an alert visible in the dashboard.
- yfinance remains the data source for backtesting; IG Streaming data is not used as backtest input.

---

### 4.2 Signal Approval Workflow

#### REQ-APPROVE-001 — Signal pending state

**Requirement:** When the system generates a new signal for an instrument, that signal must enter a `pending` state and remain there until the user explicitly approves or rejects it.

**Acceptance criteria:**
- Signals have a lifecycle state: `pending`, `approved`, `rejected`, `expired`.
- A signal that has not been acted on within 24 hours (configurable) transitions to `expired`. An expired signal cannot be approved.
- Signal state is persisted to disk (Parquet or JSON) so that a dashboard restart does not lose pending signals.
- At most one pending signal per instrument exists at any time. If a new signal fires for an instrument that already has a pending signal, the new signal supersedes the old one and the old one transitions to `expired`.

---

#### REQ-APPROVE-002 — Approve and reject UI

**Requirement:** The Streamlit dashboard must provide approve and reject buttons for each pending signal.

**Acceptance criteria:**
- Each row in the signal table with `status="pending"` displays an Approve button and a Reject button.
- Clicking Approve transitions the signal to `approved` and (in Phase 2) triggers the order submission flow (REQ-EXEC-001).
- Clicking Reject transitions the signal to `rejected`. A rejection requires no further action; no order is placed.
- Clicking Approve opens a confirmation modal displaying: instrument, direction (Buy/Sell), current price, suggested position size, suggested stop loss, and suggested take profit before the order is placed. The user must confirm.
- A rejected or expired signal row is visually distinct from a pending signal (greyed out or moved to a history section).
- Neither button submits an order without confirmation. Double-click or accidental single-click must not place an order.

---

#### REQ-APPROVE-003 — Position sizing recommendation

**Requirement:** The dashboard must display a suggested position size for each pending signal based on configured risk parameters.

**Acceptance criteria:**
- Position size is calculated as: `(account_balance * risk_per_trade_pct) / abs(entry_price - stop_loss_price)`, where all inputs are displayed to the user.
- `risk_per_trade_pct` is configurable in `config/environments/local.yaml` and defaults to 1%.
- The suggested stop loss is calculated as the signal's `stop_loss_level` output by the strategy, or as `entry_price * (1 - default_stop_pct)` if the strategy does not emit a stop level.
- The suggested position size is displayed as a number of contracts (or units) rounded down to the nearest integer.
- The calculation is shown transparently in the confirmation modal (inputs and result visible, not just the final number).
- The user may override the suggested size before confirming.

---

### 4.3 Paper Trade Execution and Position Tracking

#### REQ-EXEC-001 — Paper order submission to IG demo

**Requirement:** When the user approves a signal, the system must submit a market order to the IG demo account via the IG REST API.

**Acceptance criteria:**
- Order parameters submitted to IG include: epic (instrument identifier), direction (BUY/SELL), size, order type (MARKET), currency code, and force open flag.
- The IG epic for each instrument is stored in `instruments.yaml` under an `ig_epic` field. The system must not infer or guess epics.
- A successful order response from IG is logged at INFO level with the deal reference and deal ID.
- A failed order response (any non-success status from IG) is logged at ERROR level with the full IG error response. The signal transitions to `rejected` and the user is notified in the dashboard.
- The order submission call is non-blocking; the dashboard does not freeze while waiting for the IG response.

---

#### REQ-EXEC-002 — Open position tracking

**Requirement:** The system must track open positions on the IG demo account and display them in the dashboard.

**Acceptance criteria:**
- Open positions are retrieved from the IG REST API (`GET /positions`) on each dashboard refresh.
- The positions panel shows: instrument, direction, size, open price, current price, unrealised P&L, and stop level.
- Unrealised P&L is computed using the current mid-price from the IG Streaming API if a streaming connection is active, or the last known price if not.
- Position data is cached locally; a failed API call displays the last successful data with a staleness indicator rather than crashing the dashboard.

---

#### REQ-EXEC-003 — Stop loss enforcement

**Requirement:** Every order placed through the system must include a stop loss level.

**Acceptance criteria:**
- The order submission function raises a `ValidationError` if a stop loss level is not provided.
- The stop loss level is derived from the strategy's signal output or the position sizing recommendation (REQ-APPROVE-003).
- The stop loss is submitted as a guaranteed stop or controlled risk stop where supported by IG (configurable per instrument in `instruments.yaml`).
- If the IG API rejects a stop level as invalid (e.g. too close to current price), the error is surfaced to the user with the minimum permitted stop distance before the order is cancelled.

---

### 4.4 Trade Journal and Signal History

#### REQ-JOURNAL-001 — Trade journal persistence

**Requirement:** Every completed trade (entry and exit) must be recorded in a persistent trade journal stored as Parquet at `data/journal/trades.parquet`.

**Acceptance criteria:**
- Each trade record contains: `trade_id`, `symbol`, `direction`, `entry_timestamp`, `entry_price`, `exit_timestamp`, `exit_price`, `size`, `gross_return`, `cost`, `net_return`, `stop_level`, `signal_id`, `approved_by` (always `"manual"` in Phase 2), `notes` (freetext, nullable).
- A trade record is written at entry and updated at exit; the entry record is not deleted on exit.
- The journal is never overwritten in full; records are appended.
- The dashboard can display the trade journal filtered by instrument, date range, and direction.

---

#### REQ-JOURNAL-002 — Signal history persistence

**Requirement:** Every signal emitted by the system must be persisted, regardless of whether it was approved, rejected, or expired.

**Acceptance criteria:**
- Each signal record contains: `signal_id`, `symbol`, `timestamp_generated`, `signal` (1 or -1), `close_at_generation`, `fast_sma`, `slow_sma`, `rsi`, `status` (pending/approved/rejected/expired), `timestamp_actioned` (nullable), `deal_id` (nullable, set if approved and order was placed).
- Signal records are appended to `data/journal/signals.parquet`; existing records are not overwritten.
- The dashboard can display signal history filtered by instrument, status, and date range.

---

### 4.5 Streamlit Dashboard — Phase 2 Additions

#### REQ-UI-009 — Signal approval panel

**Requirement:** The Dashboard page must display pending signals with approve and reject actions as described in REQ-APPROVE-002.

---

#### REQ-UI-010 — Open positions panel

**Requirement:** The Dashboard page must include an open positions panel as described in REQ-EXEC-002.

---

#### REQ-UI-011 — Trade journal view

**Requirement:** A new Journal page must display the trade journal (REQ-JOURNAL-001) and signal history (REQ-JOURNAL-002).

**Acceptance criteria:**
- The Journal page has two tabs: Trades and Signals.
- Both tabs support filtering by instrument, date range, and status.
- The Trades tab displays a running P&L curve below the trade log.
- The Signals tab shows the accept/reject rate as a summary metric.

---

#### REQ-UI-012 — Environment banner

**Requirement:** The dashboard must display a persistent banner identifying the current environment (DEMO or LIVE) as described in REQ-IG-002.

---

### 4.6 Non-Functional Requirements — Phase 2

#### REQ-NFR-009 — Demo-only gate

No Phase 2 code path that results in an order being submitted may be reachable when `IG_ENVIRONMENT=live`. This constraint must be enforced programmatically, not by convention.

#### REQ-NFR-010 — Order audit trail

Every IG API call that places, modifies, or cancels an order must be logged to `logs/orders.log` with a timestamp, the full request payload (credentials redacted), and the full response payload. This log must not be deleted by any application code.

#### REQ-NFR-011 — No concurrent order submissions

The system must prevent submitting more than one order for the same instrument while the first order is pending confirmation from IG. A lock or state check must be in place; a duplicate submission raises an error and does not proceed.

---

## 5. Phase 3 — IG Live Account, Forex, Live Risk Controls

Phase 3 begins only after all Phase 2 acceptance criteria are met, at least 30 days of paper trading on the IG demo account have been completed without critical defects, and a risk review sign-off has been recorded in `docs/risk-review.md`.

### 5.1 Live Order Placement

#### REQ-LIVE-001 — Credential switch to live

**Requirement:** Switching from demo to live execution must require only a change to `IG_ENVIRONMENT=live` and live credentials in `.env`.

**Acceptance criteria:**
- No code changes are required to switch environments. The adapter selects the correct IG endpoint based solely on `IG_ENVIRONMENT`.
- Switching to `live` causes the environment banner (REQ-UI-012) to display prominently in red with the text `LIVE ACCOUNT — REAL MONEY`.
- On application startup with `IG_ENVIRONMENT=live`, the system logs a WARNING at the first line of the startup sequence identifying the live environment.

---

#### REQ-LIVE-002 — Pre-submission risk checks

**Requirement:** Every order submitted against the live account must pass a pre-submission risk check that enforces configured limits before the IG API call is made.

**Acceptance criteria:**
- Pre-submission checks are performed in this order, and each check must pass before the next is evaluated:
  1. Daily loss limit: if the day's realised losses exceed `risk.daily_loss_limit_pct` of account balance, no new orders are submitted.
  2. Total exposure cap: if total open exposure (sum of position sizes * current prices) would exceed `risk.max_exposure_pct` of account balance after this order, the order is blocked.
  3. Per-instrument position limit: if the instrument already has an open position, a second order in the same direction is blocked.
  4. Stop loss present: the order must include a stop loss (enforced by REQ-EXEC-003).
- Each blocked order logs the reason at WARN level and displays the reason to the user in the dashboard.
- Risk limit values are stored in `config/environments/local.yaml` and are not hardcoded.

---

### 5.2 Live Position and Account Monitoring

#### REQ-LIVE-003 — Real-time position monitoring

**Requirement:** Open live positions must be monitored via the IG Streaming API with price updates at the subscribed candle frequency.

**Acceptance criteria:**
- The streaming adapter updates displayed unrealised P&L at each new candle tick.
- If the IG Streaming connection drops for more than 60 seconds, the dashboard displays a `CONNECTION LOST` alert and disables the Approve button until the connection is restored.
- Account balance and available margin are retrieved from the IG REST API on each refresh and displayed in the positions panel.

---

### 5.3 Risk Controls for Live Capital

#### REQ-LRISK-001 — Kill switch

**Requirement:** The system must provide a single action that closes all open positions and prevents any new orders from being placed.

**Acceptance criteria:**
- A Kill Switch button is visible on every page of the dashboard when `IG_ENVIRONMENT=live`.
- Clicking the Kill Switch opens a confirmation modal. Confirming the modal triggers a close request for every open position via the IG REST API.
- After activation, the system enters a `halted` state. No new orders can be submitted until the `halted` state is manually cleared by restarting the application.
- The Kill Switch must complete all close requests (or exhaust retries) within 60 seconds. The dashboard displays a countdown and the status of each position closure.
- The Kill Switch activation event is logged to `logs/orders.log` with a timestamp and the positions affected.

---

#### REQ-LRISK-002 — Risk parameter configuration

**Requirement:** All risk limits governing live trading must be readable from `config/environments/local.yaml` and must not require code changes to adjust.

**Acceptance criteria:**
- The following parameters are configurable: `risk.daily_loss_limit_pct`, `risk.max_exposure_pct`, `risk.max_open_positions`, `risk.risk_per_trade_pct`, `risk.default_stop_pct`.
- The application validates all risk parameters at startup and raises a `ConfigValidationError` if any value is outside a sane range (e.g. `daily_loss_limit_pct > 50` is rejected as an unsafe value).
- Changing a risk parameter requires an application restart; there is no hot-reload of risk config.

---

### 5.4 Forex Expansion

#### REQ-FX-001 — Forex instrument support

**Requirement:** Phase 3 adds forex instruments to `instruments.yaml`. The system must support these without code changes.

**Acceptance criteria:**
- `asset_class: fx` is a valid value (already in the permitted set from REQ-DATA-007).
- Forex instruments added to `instruments.yaml` are ingested, signal-generated, and displayed in the dashboard identically to commodity instruments.
- Each forex instrument entry in `instruments.yaml` includes its IG epic for order placement.
- The signal table groups instruments by `asset_class` to separate commodities from forex visually.

---

### 5.5 Streamlit Dashboard — Phase 3 Additions

#### REQ-UI-013 — Kill switch button

**Requirement:** A Kill Switch button is visible on all pages when `IG_ENVIRONMENT=live`, as specified in REQ-LRISK-001.

---

#### REQ-UI-014 — Actual vs backtest performance tracking

**Requirement:** The Journal page must include a tab comparing actual trade performance against the backtest predictions for the same instruments and period.

**Acceptance criteria:**
- For each instrument with at least 5 completed live trades, the tab displays: actual win rate vs backtest win rate, actual average trade return vs backtest average trade return, and actual Sharpe ratio vs backtest Sharpe ratio.
- Divergences greater than 20% between actual and backtest metrics are highlighted with a warning indicator.
- The comparison uses only the backtest results that correspond to the same strategy and parameters currently in use.

---

#### REQ-UI-015 — Risk dashboard panel

**Requirement:** The Dashboard page must include a risk summary panel when `IG_ENVIRONMENT=live`.

**Acceptance criteria:**
- The panel displays: account balance, available margin, current day P&L, daily loss limit remaining, total exposure as a percentage of balance, and current number of open positions.
- Each metric has a visual indicator (green/amber/red) based on proximity to configured limits.

---

### 5.6 Non-Functional Requirements — Phase 3

#### REQ-NFR-012 — Pre-live checklist

Before `IG_ENVIRONMENT=live` is used for the first time, the following must be recorded as completed in `docs/risk-review.md`:
- All Phase 2 tests pass on the demo account.
- At least 30 consecutive calendar days of paper trading completed with no critical defects.
- Risk parameters in `config/environments/local.yaml` reviewed and signed off.
- Kill switch tested successfully on the demo account.
- Order audit log reviewed for completeness.

#### REQ-NFR-013 — Live order log retention

`logs/orders.log` must not be cleared by any automated process. Log rotation must append to a new file, not overwrite the existing one.

---

## 6. Phase 4 — Automated Execution (stub)

Phase 4 removes the human approval step. The system generates signals, obtains an LLM go/no-go decision, and submits orders automatically without requiring user input. Phase 4 has not been designed in detail; this section is a stub that captures the known scope and prerequisites so future design work begins from a documented baseline.

**Prerequisites before Phase 4 begins:**
- Phase 3 complete and stable on the IG live account.
- At least 30 days of stable Phase 2 paper trading completed with no critical defects recorded.
- Kill switch (REQ-LRISK-001) tested and verified on the IG demo account.
- Automated pipeline validated on the IG demo account for 30 days before live auto-trading is enabled (REQ-AUTO-006).

**Out of scope for Phase 4:**
- ML-based signal generation.
- Portfolio optimisation or mean-variance allocation.

---

### 6.1 Automated Pipeline

#### REQ-AUTO-001 — Automated pipeline

**Requirement:** A scheduled script must run the full pipeline — ingest, signal generation, LLM decision, position sizing, and order submission — without human intervention.

**Acceptance criteria:**
- The script is schedulable via cron or Windows Task Scheduler and requires no interactive input to run.
- The complete sequence is: data ingest → signal generation → LLM go/no-go decision → guardrail checks → position sizing → order submission (if all gates pass).
- Each pipeline stage logs its outcome at `INFO` level before proceeding to the next stage.
- A dry-run mode (`--dry-run` flag) executes all stages up to but not including order submission and logs what would have been submitted.

---

### 6.2 Guardrails

#### REQ-AUTO-002 — LLM gate

**Requirement:** An automated order fires only when `confidence_score >= configurable_threshold` AND `llm_recommendation == "GO"`. Any other LLM output suppresses the order.

**Acceptance criteria:**
- The confidence threshold is configurable in `config/environments/local.yaml` under `automation.confidence_threshold` and defaults to `70`.
- An automated order is submitted only when both conditions are true simultaneously: `confidence_score >= automation.confidence_threshold` AND `llm_recommendation == "GO"`.
- An LLM output of `"UNCERTAIN"` or `"NO_GO"` suppresses the order regardless of confidence score. The suppression is logged at `INFO` level with instrument, recommendation, and confidence score.
- The threshold value is validated at startup: must be an integer in `[0, 100]`. A value outside this range raises a `ConfigValidationError`.

---

#### REQ-AUTO-003 — Guardrails

**Requirement:** Five guardrail checks must all pass before any automated order is submitted. A single failing check blocks the order.

**Acceptance criteria — all five checks are evaluated in this order:**
1. **Kill switch check:** if the system is in `halted` state (REQ-LRISK-001), no order is submitted.
2. **Market hours check:** the instrument's primary market must be open (using session hours from `instruments.yaml`). Orders are not submitted outside market hours.
3. **Daily loss limit:** today's realised losses must not equal or exceed `risk.daily_loss_limit_pct` of account balance.
4. **Max open positions:** the number of currently open positions must be below `risk.max_open_positions`.
5. **Duplicate position guard:** if a position in the same instrument and direction already exists, the order is suppressed.
- Each blocked order logs the reason at `WARNING` level with instrument name, the failing guardrail name, and the current values that triggered the block.
- All guardrail thresholds are read from `config/environments/local.yaml`; none are hardcoded.

---

### 6.3 Notifications and Audit Trail

#### REQ-AUTO-004 — Notification on automated order placement

**Requirement:** Every automated order placement must trigger a push notification. Notification failure must not block or roll back the order.

**Acceptance criteria:**
- A notification is sent via ntfy.sh (or equivalent configurable endpoint) on every automated order submitted to the broker.
- The notification payload contains at minimum: instrument name, direction (BUY/SELL), position size, and entry price.
- If the notification call fails for any reason, the failure is logged at `WARNING` level and order processing continues. The order is not cancelled due to a notification failure.
- The notification endpoint is configurable via `PUSH_NOTIFICATION_URL` in `.env`. When this variable is absent, notifications are disabled and no outbound call is made.

---

#### REQ-AUTO-005 — Audit trail for automated decisions

**Requirement:** Every automated decision — whether an order was placed, suppressed, or blocked — must be written to `logs/audit.log` with full context.

**Acceptance criteria:**
- Every automated pipeline run writes an audit entry for each instrument processed, regardless of outcome.
- Each entry contains at minimum: `timestamp` (ISO 8601 UTC), `instrument`, `pipeline_run_id`, `signal_direction`, `confidence_score`, `llm_recommendation`, `guardrails_passed` (list of passed checks), `guardrails_failed` (list of failed checks, empty if none), `action` (one of: `order_submitted`, `order_suppressed_llm`, `order_blocked_guardrail`), and `deal_id` (non-null only when `action="order_submitted"`).
- Audit entries are appended to `logs/audit.log` in JSON-lines format. The file is never truncated by application code.
- A unit test verifies that a suppressed order (LLM returned `"UNCERTAIN"`) produces an audit entry with `action="order_suppressed_llm"` and a non-null `llm_recommendation` field.

---

### 6.4 Demo Validation Gate

#### REQ-AUTO-006 — Demo account validation before live auto-trading

**Requirement:** Automated trading must run for a minimum of 30 days on the IG demo account before live auto-trading is enabled.

**Acceptance criteria:**
- A config flag `automation.live_auto_trading_enabled` in `config/environments/local.yaml` defaults to `false`. Automated order submission against the live account is blocked unless this flag is explicitly set to `true`.
- Before setting `live_auto_trading_enabled: true`, the operator must record a sign-off entry in `docs/risk-review.md` confirming: 30 days of demo auto-trading completed, audit log reviewed, kill switch tested on demo account, and no critical defects observed.
- The automated pipeline checks this flag at startup. If `IG_ENVIRONMENT=live` and `live_auto_trading_enabled=false`, the pipeline logs a prominent `WARNING` and exits without processing any instruments.
- A unit test verifies that with `IG_ENVIRONMENT=live` and `live_auto_trading_enabled=false`, the pipeline exits before any signal generation or order submission occurs.

---

## 7. Discretionary Workflow — End to End

This section describes the complete operational workflow in Phase 1 (research only) and Phase 2 (signal approval and paper execution). It is the reference for UI designers and engineers implementing the dashboard interaction model.

### 7.1 Daily Research Workflow (Phase 1)

```
1. SCHEDULE: User opens Streamlit dashboard (or runs refresh manually each morning).

2. DATA REFRESH:
   - User clicks "Refresh Data" on the Dashboard page.
   - System runs ingest_market_data.py for all instruments in instruments.yaml.
   - Each instrument's curated Parquet file is updated with the latest daily bar.
   - Dashboard displays refresh summary (N succeeded, M failed).
   - Last refresh timestamp updated in sidebar.

3. SIGNAL COMPUTATION:
   - On refresh completion (or on-demand), system runs SmaCrossStrategy with RSI filter
     for all instruments on their curated daily data.
   - Results are written to a persisted signal snapshot under `data/signals/`.
   - Signal table on Dashboard page reads from that snapshot and updates.

4. HUMAN REVIEW:
   - User reviews the signal table: which instruments show Buy, Sell, or Neutral.
   - User navigates to Charts page to inspect price chart with SMA and RSI overlays
     for any instrument of interest.
   - User navigates to Backtests page to review historical strategy performance if needed.

5. DECISION:
   - User decides whether to act on any signal (manually, outside the system in Phase 1).
   - No order is placed by the system in Phase 1.
   - No signal approval or rejection is recorded in Phase 1.

6. END OF DAY:
   - Dashboard may be left open; stale data warning appears if data is more than 2 days old.
```

### 7.2 Signal Approval and Paper Trade Workflow (Phase 2)

```
1. DATA REFRESH (same as Phase 1, Step 1-2).

2. SIGNAL COMPUTATION:
   - Signals are computed as in Phase 1.
   - Any new signal (where signal changes from neutral to buy or sell) transitions to "pending"
     state and is persisted to data/journal/signals.parquet.
   - The Dashboard page shows the pending signal with Approve and Reject buttons.

3. HUMAN REVIEW (same as Phase 1, Step 4).

4. DECISION POINT — APPROVE:
   a. User clicks Approve on a pending signal row.
   b. Confirmation modal appears showing:
      - Instrument name and direction (Buy/Sell)
      - Current price (from last known bar)
      - Suggested position size (from REQ-APPROVE-003)
      - Suggested stop loss level
      - Suggested take profit level (if emitted by strategy)
      - Risk/reward ratio
   c. User may adjust size within the modal.
   d. User confirms by clicking "Place Order".
   e. System submits market order to IG demo account (REQ-EXEC-001).
   f. On IG confirmation: signal status updated to "approved", deal ID recorded.
   g. Dashboard positions panel updates to show new open position.

4. DECISION POINT — REJECT:
   a. User clicks Reject on a pending signal row.
   b. No confirmation required.
   c. Signal status updated to "rejected" in signals.parquet.
   d. No order is placed.

5. SIGNAL EXPIRY:
   - Any pending signal not acted on within 24 hours (configurable) transitions to "expired".
   - Expired signals are moved to the history section of the signal table.
   - No order is placed for an expired signal.

6. POSITION MONITORING:
   - Open positions displayed in the positions panel on the Dashboard page.
   - Unrealised P&L updates with each new candle from IG Streaming.
   - When a position is closed (manually via IG platform or by stop/take-profit trigger),
     the system retrieves the close details from IG REST API on next refresh and records
     the completed trade in the trade journal (REQ-JOURNAL-001).

7. POSITION EXIT (if managed via the dashboard in a future iteration):
   - Out of scope for Phase 2. Position exits are managed directly on the IG platform.
   - The system records exits by polling IG open positions and detecting closed deals.
```

### 7.3 Key Decision Points and Human Judgment Boundaries

| Step | System action | Human decision required |
|---|---|---|
| Data refresh | Fetches and normalises data | No (triggered manually or on schedule) |
| Signal computation | Applies strategy rules | No (rule-based, deterministic) |
| Signal review | Displays signal with supporting data | Yes — review chart, backtest context, market conditions |
| Signal approval | Awaits user input | Yes — Approve or Reject |
| Position sizing | Recommends size; user may override | Yes — confirm or adjust size |
| Order placement | Submits to IG after confirmation | Yes — explicit confirmation required |
| Position exit | Not managed by system in Phase 2 | Yes — user acts on IG platform |
| Kill switch (Phase 3) | Closes all positions | Yes — explicit confirmation required |

---

## 8. Gaps and Contradictions

### GAP-001 — BacktestConfig is missing required fields

The current `BacktestConfig` model in `backtesting/models.py` contains only `initial_cash`, `commission_bps`, and `slippage_bps`. It is missing `symbol`, `timeframe`, `strategy_name`, `strategy_params`, `start_date`, and `end_date`. A backtest result saved to disk today cannot be reproduced from config alone. This must be resolved before REQ-BT-001 and REQ-BT-006 can pass.

### GAP-002 — No tests directory exists

The repository has no `tests/` directory and no test suite. REQ-NFR-002 requires tests for all core paths. This is the largest implementation gap in Phase 1.

### GAP-003 — Signal contract not enforced at the boundary

`Strategy.generate_signals` returns a DataFrame but the base class does not validate that the return value contains a `signal` column or that signal values are within `{-1, 0, 1}`. Any downstream code can silently receive a malformed DataFrame. A post-call validation step must be added to the base class.

### GAP-004 — Engine is documented as long/flat-only but IG spreadbetting supports shorts

The previous requirements document specified a long/flat-only engine. This was a placeholder before the broker was confirmed. IG spreadbetting natively supports short positions on all instruments. The backtest engine must be updated to support shorts (REQ-BT-004). The strategy's `-1` signal must be treated as a short position, not flat. This is a breaking change to the engine semantics.

### GAP-005 — No structured logging

Scripts and the backtest engine produce no structured log output. REQ-NFR-007 requires structured logs to `logs/`. Without this, silent failures in the ingest pipeline cannot be diagnosed after the fact.

### GAP-006 — Adjusted prices flag not propagated to curated output

`MarketDataRequest` carries an `adjusted` field but the normalisation step in `transforms.py` does not write this flag into the curated Parquet file. A strategy consuming a curated file cannot verify whether it is operating on adjusted or unadjusted prices. REQ-DATA-002 requires the `adjusted` column to be present in the curated schema.

### GAP-007 — backtrader dependency is ambiguous

`backtrader` is installed but the project has built its own backtest engine. The two cannot coexist without creating ambiguity about which is the authoritative backtesting path. REQ-NFR-008 requires a decision and resolution before Phase 1 closes.

### GAP-008 — No IG epic mapping in instruments.yaml

Phase 2 requires submitting orders to IG using IG's internal `epic` identifier (e.g. `IX.D.FTSE.DAILY.IP`), not the yfinance symbol (e.g. `GC=F`). These are different identifiers. `instruments.yaml` does not currently include an `ig_epic` field. This must be added before Phase 2 order placement can work. The epic values must be sourced from IG's instrument search API or documentation and manually verified.

### GAP-009 — No signal persistence in Phase 1

Phase 1 computes signals and writes them to a persisted snapshot on disk. Phase 2 requires signal history persistence for the approval workflow and extends the same persisted records with approval states.

### CONFLICT-001 — Backtest engine short-selling constraint vs broker capability

The previous `requirements-phase1.md` explicitly prohibited short selling in the backtest engine ("long/flat only"). The confirmed broker (IG spreadbetting) supports shorts on all instruments and is specifically designed for it. The prohibition was an explicit simplification, not a business constraint. It must be removed and REQ-BT-004 must replace it.

### CONFLICT-002 — yfinance futures symbols vs IG spreadbetting epics

yfinance uses continuous futures symbols (e.g. `GC=F` for Gold). IG spreadbetting uses its own epic system and does not map directly from Yahoo symbols. The signal generation layer uses yfinance symbols throughout. Before Phase 2, a mapping table between yfinance symbols and IG epics must be established and maintained. Any mismatch will cause Phase 2 order placement to fail silently or route to the wrong instrument.

---

## 9. Assumptions Register

| ID | Assumption | Phase | Impact if wrong |
|---|---|---|---|
| A-001 | Overwriting curated files on refresh is acceptable; no historical versions needed | 1 | Medium — old backtests cannot be reproduced if upstream data changes |
| A-002 | All Phase 1 data is fetched adjusted; unadjusted prices have no Phase 1 use case | 1 | Low — the `adjusted` column is in the schema; adding unadjusted support requires only a new ingest path |
| A-003 | Schedule trigger for data refresh is out of scope; manual invocation is sufficient for Phase 1 | 1 | Low — the script is designed to be schedulable |
| A-004 | The 5% null threshold in REQ-DATA-005 is a starting value pending confirmation | 1 | Low for Phase 1; should be confirmed before going to Phase 2 with live data |
| A-005 | 252 trading days is the correct annualisation constant for daily commodity strategies | 1 | Low for relative comparisons; commodity futures trade on slightly different calendars. Must be confirmed |
| A-006 | Risk-free rate for Sharpe calculation is 0% | 1 | Low for relative comparisons; wrong for absolute interpretation |
| A-007 | `.env` contains all secrets; no secrets appear in YAML config files | All | High — if a strategy YAML contains credentials it will be committed to version control |
| A-008 | The IG demo account API is identical to the live API; no behaviour differences exist | 2 | High — if APIs differ, Phase 2 paper trading results will not accurately predict Phase 3 live behaviour |
| A-009 | Position exits in Phase 2 are managed on the IG platform, not through the dashboard | 2 | Medium — if the user wants exit management in the dashboard, REQ-EXEC scope must expand |
| A-010 | Daily bars from yfinance are sufficient for entry timing research; intraday precision is not needed | 1 | Medium — if the strategy requires intraday precision for entries, yfinance daily data will produce unreliable backtest results |
| A-011 | The holding period of "days to weeks" implies that daily bar resolution is sufficient for signal generation | 1 | Low — consistent with the chosen timeframe and instruments |
| A-012 | The user operates in UK timezone; all UI date/time displays should use UK local time (GMT/BST) | All | Medium — if the user is not in the UK, times displayed will be confusing relative to IG platform timestamps |

---

## 10. Open Questions

These questions must be answered before the indicated requirement can be finalised. Each question is an explicit blocker or a risk to correctness.

| ID | Question | Blocks | Priority |
|---|---|---|---|
| OQ-BT-002 | Should the backtest support multiple simultaneous positions (e.g. Gold and Oil both long), or is it single-instrument only per run? | BacktestConfig scope, portfolio-level metrics | High |
| OQ-DATA-001 | What is the intended historical data retention period — 1 year, 5 years, all available? This affects storage sizing and minimum backtest lookback. | REQ-DATA-004, REQ-BT-007 | Medium |
| OQ-DATA-002 | Should the refresh script be runnable on a schedule (cron, Windows Task Scheduler), or is manual invocation sufficient for all phases? | REQ-DATA-004 | Medium |
| OQ-SIG-001 | Should the strategy emit a take profit level in addition to a stop loss? This affects REQ-APPROVE-003 and the confirmation modal. | REQ-APPROVE-003 | Medium |
| OQ-SIG-002 | When a sell signal fires on an instrument that has no open long position, should it be presented as a short entry opportunity, or suppressed? | REQ-SIG-003, REQ-APPROVE-002 | High |
| OQ-UI-001 | Should the Streamlit dashboard support multiple simultaneous users, or is it strictly single-user local? Concurrent sessions could produce conflicting approvals. | REQ-APPROVE-001, REQ-NFR-011 | Medium |
| OQ-UI-002 | What is the expected frequency of dashboard use — once per day after market close, or intraday? This determines whether real-time price updates are needed in Phase 1. | REQ-UI-002, REQ-UI-004 | Medium |
| OQ-DEP-001 | Should `backtrader` be kept, adopted as the engine, or removed from dependencies? | GAP-007, REQ-NFR-008 | Medium |
| OQ-IG-001 | What are the correct IG epics for the five Phase 1 commodity instruments? These are required before Phase 2 order placement can be implemented. | REQ-EXEC-001, GAP-008 | High (for Phase 2) |
| OQ-IG-002 | Does the IG spreadbetting demo account support all five commodity instruments (GC=F equivalent, CL=F equivalent, etc.)? Some products may only be available on the live account. | REQ-IG-001, REQ-EXEC-001 | High (for Phase 2) |
| OQ-RISK-001 | What are the target values for `risk.daily_loss_limit_pct`, `risk.max_exposure_pct`, and `risk.risk_per_trade_pct`? These must be set before Phase 3 goes live. | REQ-LIVE-002, REQ-LRISK-001 | High (for Phase 3) |
| OQ-MTF-001 | How should the annualisation constant be determined for weekly bars — from BacktestConfig, from the data's inferred frequency, or from instruments.yaml? | REQ-BT-008 | Low |

---

## 11. Dependency Map

```
Phase 1 dependencies
====================

REQ-DATA-007 (instruments.yaml)
    --> REQ-DATA-001 (raw persistence)
    --> REQ-DATA-004 (scheduled refresh)
    --> REQ-WATCH-001 (watchlist)
    --> REQ-UI-002 (signal table)

REQ-DATA-001 + REQ-DATA-002 + REQ-DATA-005 (ingest + schema + validation)
    --> REQ-SIG-001 (strategy interface)
    --> REQ-BT-001 (backtest config)
    --> REQ-UI-004 (price charts)

REQ-SIG-001 + REQ-SIG-003 + REQ-SIG-004 (strategy interface + SMA cross + RSI filter)
    --> REQ-BT-001 (backtest config)
    --> REQ-WATCH-002 (portfolio signal view)
    --> REQ-UI-002 (signal table)

REQ-BT-001 + REQ-BT-002 + REQ-BT-003 + REQ-BT-004 (config + no-lookahead + costs + long/short)
    --> REQ-BT-005 (metrics)
    --> REQ-BT-006 (persistence)
    --> REQ-BT-007 (date range)
    --> REQ-BT-008 (annualisation)
    --> REQ-UI-005 (backtest results page)

REQ-SIG-006 (indicators: SMA, RSI, MACD)
    --> REQ-SIG-003 (SMA cross strategy)
    --> REQ-SIG-004 (RSI filter)
    --> REQ-UI-004 (chart overlays)

REQ-DATA-006 (multi-timeframe)
    --> separate curated files per interval
    --> REQ-BT-008 (annualisation by timeframe)

Phase 2 dependencies (require Phase 1 complete)
================================================

REQ-IG-001 (authentication)
    --> REQ-IG-002 (environment isolation)
    --> REQ-IG-003 (error handling)
    --> REQ-EXEC-001 (paper order submission)

REQ-APPROVE-001 (signal pending state)
    --> REQ-APPROVE-002 (approve/reject UI)
    --> REQ-APPROVE-003 (position sizing)
    --> REQ-EXEC-001 (paper order submission)
    --> REQ-JOURNAL-002 (signal history)

REQ-EXEC-001 (paper order submission)
    --> REQ-EXEC-002 (open position tracking)
    --> REQ-EXEC-003 (stop loss enforcement)
    --> REQ-JOURNAL-001 (trade journal)

Phase 3 dependencies (require Phase 2 complete + risk review)
=============================================================

REQ-LIVE-001 (credential switch)
    --> REQ-LIVE-002 (pre-submission risk checks)
    --> REQ-LRISK-001 (kill switch)
    --> REQ-UI-013 (kill switch button)
    --> REQ-UI-015 (risk dashboard panel)

REQ-FX-001 (forex instruments)
    --> REQ-DATA-007 (instrument registry — asset_class: index and fx already permitted)
    --> REQ-EXEC-001 (order submission — ig_epic field required per instrument)
```

---

---

## 11. Market Context Engine

### Objective

Define a new component responsible for aggregating non-technical, contextual inputs (sentiment, news, economic events, commodity-specific events) and producing a structured output that downstream components — primarily the LLM explainer and decision layer — can consume. This component does not generate signals, does not compute composite scores, and does not override strategy logic.

---

### 11.1 Market Context Engine Component

#### REQ-CONTEXT-001 — Engine definition and boundaries

**Requirement:** A `MarketContextEngine` class must exist in `src/trading_lab/context/engine.py`. It is responsible solely for aggregating contextual inputs and returning a structured `MarketContext` object. It has no dependency on strategy or backtest code.

**Acceptance criteria:**
- `MarketContextEngine` exposes a single public method: `build_context(symbol: str, as_of_date: date) -> MarketContext`.
- The method aggregates all available context sources defined in this section for the given instrument and date.
- The method returns a `MarketContext` object (REQ-CONTEXT-002); it never returns raw text, a dict of strings, or an unstructured blob.
- `MarketContextEngine` does not call strategy methods, read signal files, or write to `data/signals/`. Its output path is `data/context/` only.
- A unit test confirms that `build_context` can be called with a mocked data layer (no network calls) and returns a fully populated `MarketContext` without error.
- The engine does not compute a composite sentiment score. It aggregates raw inputs; score computation is explicitly out of scope for this component.

**Assumption A-026:** The Market Context Engine is called as part of the daily data refresh pipeline, after price data has been ingested but before LLM explanation is generated. It is not called at dashboard render time.

---

#### REQ-CONTEXT-002 — MarketContext output schema

**Requirement:** The `MarketContext` object must be a typed dataclass (or Pydantic model) conforming to a fixed schema. All fields must be typed; no raw text strings or untyped dicts are permitted at the top level.

**Acceptance criteria:**
- `MarketContext` contains the following top-level fields:
  - `symbol: str` — the instrument identifier.
  - `as_of_date: date` — the date for which context was assembled.
  - `fetch_timestamp: datetime` — UTC timestamp of when the context was assembled.
  - `news_events: list[ContextEvent]` — news headlines (see REQ-EVENT-001 for `ContextEvent` schema).
  - `macro_events: list[ContextEvent]` — scheduled economic calendar events relevant to this instrument.
  - `commodity_events: list[ContextEvent]` — commodity-specific events (EIA inventory, OPEC meetings, China PMI).
  - `ig_sentiment: IGSentiment | None` — IG client sentiment data (see REQ-SENT-001); `None` if unavailable.
  - `event_freshness: EventFreshness` — metadata about event age across all three event lists (see REQ-EVENT-001).
- A `MarketContext` can be serialised to and deserialised from JSON without loss of typing information.
- A unit test verifies round-trip serialisation: a `MarketContext` serialised to JSON and deserialised produces an object equal to the original.

---

#### REQ-CONTEXT-003 — Market context persistence

**Requirement:** The assembled `MarketContext` must be written to disk as part of the daily refresh pipeline so that the LLM and dashboard can read it without triggering a re-fetch.

**Acceptance criteria:**
- Context is written to `data/context/<symbol>_<YYYY-MM-DD>.json` using the `as_of_date` field.
- The file is written only after the `MarketContext` object has been fully assembled and validated; a partial write does not leave a file at the final path.
- A subsequent refresh for the same symbol and date overwrites the existing file and logs the overwrite at `INFO` level.
- Context files are excluded from version control via `.gitignore`.
- The LLM explainer reads from this file rather than triggering a new context fetch; it raises a `ContextNotAvailableError` if the file is absent, which triggers graceful degradation (explanation proceeds without context, logged at `WARNING`).

---

### 11.2 Event Freshness and Classification

#### Objective

Every event ingested by the Market Context Engine must be tagged with structured metadata so that consuming components can filter, sort, and distinguish events by type, recency, and relevance without parsing free text.

---

#### REQ-EVENT-001 — Event tagging schema

**Requirement:** Every event included in a `MarketContext` must conform to the `ContextEvent` schema with all required fields populated at ingestion time.

**Acceptance criteria:**
- `ContextEvent` is a typed dataclass containing:
  - `title: str` — headline or event name.
  - `source: str` — publisher or data provider name (e.g. `"Yahoo Finance"`, `"EIA"`, `"Investing.com"`).
  - `event_timestamp: datetime` — UTC datetime of the event or publication. Must be timezone-aware.
  - `event_type: Literal["macro", "supply", "geopolitical", "central_bank", "commodity_inventory", "sentiment", "news"]` — classification of the event.
  - `relevance: list[str]` — list of instrument symbols for which this event is considered relevant (e.g. `["GC=F", "SI=F"]`).
  - `is_scheduled: bool` — `True` if the event was pre-announced on an economic calendar; `False` for breaking news or unscheduled publications.
- An `EventFreshness` object contains:
  - `oldest_event_age_days: float` — age in calendar days of the oldest event in the combined event lists.
  - `newest_event_age_days: float` — age in calendar days of the most recent event.
  - `total_event_count: int` — total number of events across all three lists.
- `time_since_event` is not stored statically; it is computed at the point of use as `(current_datetime - event_timestamp).total_seconds() / 86400`.
- A unit test verifies that a `ContextEvent` constructed with a naive datetime raises a `ValueError`.

---

#### REQ-EVENT-002 — Scheduled vs unscheduled event classification

**Requirement:** Events sourced from an economic calendar (REQ-CTX-001) must be classified as `is_scheduled=True`. Events sourced from news headline feeds (REQ-LLM-008) must be classified as `is_scheduled=False`.

**Acceptance criteria:**
- The ingestion path for economic calendar events (Investing.com feed or equivalent) sets `is_scheduled=True` on all produced `ContextEvent` objects.
- The ingestion path for yfinance news headlines sets `is_scheduled=False` on all produced `ContextEvent` objects.
- A unit test confirms that a `ContextEvent` produced by the calendar ingestion path has `is_scheduled=True`, and one produced by the news path has `is_scheduled=False`.
- The `is_scheduled` field is included in the serialised JSON output.

---

#### REQ-EVENT-003 — Stale and duplicate event suppression

**Requirement:** The Market Context Engine must not include stale or duplicate events in the assembled `MarketContext`.

**Acceptance criteria:**
- An event is considered stale if `time_since_event > STALE_EVENT_THRESHOLD_DAYS`. `STALE_EVENT_THRESHOLD_DAYS` defaults to 5 and is defined as a named constant in `context/engine.py`, not a magic number.
- Stale events are excluded before the `MarketContext` is assembled. The count of excluded stale events is logged at `DEBUG` level.
- A duplicate event is defined as two events with the same `title` (case-insensitive, stripped of leading/trailing whitespace) and the same `event_timestamp` (to the nearest minute). Only the first occurrence is retained.
- The deduplication step runs after staleness filtering and before the `MarketContext` is constructed.
- A unit test verifies: given two events with identical `title` and `event_timestamp`, the assembled context contains exactly one of them.
- A unit test verifies: an event with `time_since_event = 6` days is excluded when `STALE_EVENT_THRESHOLD_DAYS = 5`.

---

### 11.3 IG Client Sentiment Integration

#### Objective

Ingest IG client sentiment data — the percentage of IG retail clients holding long and short positions on each instrument — and make it available as structured positioning data in the `MarketContext`. This data represents retail client positioning only and must never be described as full market sentiment or used as a directional signal.

---

#### REQ-SENT-001 — IG client sentiment ingestion

**Requirement:** The system must fetch IG client sentiment data for each instrument in the watchlist via the IG REST API client sentiment endpoint and produce a structured `IGSentiment` object.

**Acceptance criteria:**
- The IG sentiment endpoint (`GET /clientsentiment?marketIds=<epic>`) is called using the authenticated IG session established by REQ-IG-001. No additional authentication is required.
- `IGSentiment` is a typed dataclass containing:
  - `market_id: str` — the IG epic identifier for the instrument.
  - `long_position_pct: float` — percentage of IG clients holding long positions (0–100).
  - `short_position_pct: float` — percentage of IG clients holding short positions (0–100).
  - `long_pct_daily_change: float | None` — change in `long_position_pct` versus the previous day's value; `None` if unavailable.
  - `short_pct_daily_change: float | None` — change in `short_position_pct` versus the previous day's value; `None` if unavailable.
  - `fetch_timestamp: datetime` — UTC timestamp of when the data was fetched.
- `long_position_pct + short_position_pct` must equal 100 (within a floating-point tolerance of 0.1). If the API returns values that violate this, a `DataQualityError` is raised and the `IGSentiment` field in `MarketContext` is set to `None`.
- If the IG API is unavailable or returns an error for sentiment, `ig_sentiment` is set to `None` in the `MarketContext`. The context assembly proceeds without it; the absence is logged at `WARNING` level.
- A unit test verifies that sentiment is set to `None` when the API returns an HTTP error, without propagating the exception.

**Assumption A-027:** IG client sentiment data is available for all five Phase 1 commodity instruments via the IG API. If an instrument has no sentiment data (e.g. because it is not widely traded by IG retail clients), `ig_sentiment` is `None` and the system proceeds without it.

---

#### REQ-SENT-002 — Sentiment classification constraint

**Requirement:** IG client sentiment data must be labelled as retail client positioning in all contexts where it is displayed or passed to the LLM. It must not be presented as a directional market indicator.

**Acceptance criteria:**
- In the `MarketContext` schema and all serialised outputs, the sentiment data block is labelled `ig_client_sentiment`, not `market_sentiment` or `sentiment_signal`.
- In the LLM prompt template, the sentiment data is introduced with the phrase: `"IG retail client positioning (note: this reflects IG retail clients only, not the full market)"` — not `"market sentiment"` or `"sentiment indicator"`.
- The dashboard, if it displays sentiment data, labels it `IG Client Positioning` not `Market Sentiment`.
- A code review check (documented in `docs/conventions.md` or equivalent) prohibits use of the string `"market sentiment"` when referring to IG client positioning data.

---

#### REQ-SENT-003 — Sentiment persistence

**Requirement:** IG client sentiment data must be fetched during the daily data refresh and stored in the `MarketContext` cache. It must not be re-fetched at dashboard render time.

**Acceptance criteria:**
- `IGSentiment` data is written as part of the `MarketContext` JSON file (REQ-CONTEXT-003) and is therefore cached with the same lifecycle as other context data.
- The dashboard reads `IGSentiment` from the cached `MarketContext` file; it does not make a direct call to the IG sentiment endpoint.
- The `fetch_timestamp` on the `IGSentiment` object reflects when the data was retrieved during the refresh, not when it is read by the dashboard.

---

### 11.4 Structured Model Context

#### Objective

Define the schema extension that encapsulates all inputs passed to the LLM for both explanation and decision outputs. All fields must be structured and typed. Raw text dumps, unstructured string concatenations, and untyped dicts are prohibited as LLM inputs.

---

#### REQ-MCTX-001 — Structured model context schema

**Requirement:** All data passed to the LLM must be encapsulated in a `ModelContext` typed object. `ModelContext` extends the existing `SignalContext` (REQ-LLM-002) with fields from the `MarketContext` (REQ-CONTEXT-002).

**Acceptance criteria:**
- `ModelContext` is a typed dataclass containing:
  - `price_context: PriceContext` — a sub-object containing: `signal_direction` (LONG/SHORT/FLAT), `confidence_score` (int or None), `signal_strength_pct` (float or None), `conflicting_indicators` (bool), `high_volatility` (bool), `fast_sma` (float), `slow_sma` (float), `rsi` (float), `close_price` (float), `stop_loss_level` (float or None), `take_profit_level` (float or None), `risk_reward_ratio` (float or None).
  - `positioning: IGSentiment | None` — IG client sentiment (from REQ-SENT-001); `None` if unavailable.
  - `macro_events: list[ContextEvent]` — macro and central bank events from `MarketContext`.
  - `news_events: list[ContextEvent]` — news headlines from `MarketContext`.
  - `commodity_events: list[ContextEvent]` — commodity-specific events from `MarketContext`.
  - `event_freshness: EventFreshness` — event age metadata from `MarketContext`.
- The LLM prompt builder serialises `ModelContext` to a structured format (e.g. nested JSON or clearly labelled sections) before constructing the prompt string. It does not pass raw field values as unstructured prose.
- The LLM prompt builder does not accept a raw `DataFrame`, a plain `dict`, or a free-text string as its primary input. It accepts only a `ModelContext` object.
- A unit test verifies that constructing a `ModelContext` with a `None` `price_context` raises a `TypeError` at construction time.

**Assumption A-028:** `ModelContext` is constructed by composing the signal output (from `SignalContext`) and the persisted `MarketContext` file. If the `MarketContext` file is absent, the `macro_events`, `news_events`, `commodity_events`, and `positioning` fields are set to empty lists / `None`, and the LLM proceeds with price context only. This is the graceful-degradation path.

---

#### REQ-MCTX-002 — Structured model context validation gate

**Requirement:** Before the `ModelContext` is passed to any LLM call, a validation step must confirm that the mandatory fields are populated. LLM calls with incomplete mandatory context are blocked.

**Acceptance criteria:**
- A `validate_model_context(ctx: ModelContext) -> None` function raises a `ModelContextValidationError` if any of the following fields are `None` or empty: `price_context`, `price_context.signal_direction`, `price_context.close_price`.
- `macro_events`, `news_events`, `commodity_events`, and `positioning` may be empty lists or `None` without triggering the error; their absence is handled by REQ-MCTX-001's degradation path.
- The validation function is called immediately before every LLM API invocation; it is not optional.
- A unit test verifies that a `ModelContext` with `price_context=None` causes `ModelContextValidationError` to be raised by the validator.

---

### 11.5 LLM Decision Role Extension

#### Objective

Extend the LLM's role beyond producing a plain English explanation (REQ-LLM-003) to also outputting a structured trade recommendation. The system remains fully discretionary: the LLM recommendation requires explicit user approval before any action is taken.

---

#### REQ-LLMDEC-001 — LLM decision output contract

**Requirement:** In addition to the explanation string (REQ-LLM-003), the LLM must return a structured `LLMDecision` object containing a trade direction recommendation and supporting parameters.

**Acceptance criteria:**
- `LLMDecision` is a typed dataclass containing:
  - `direction: Literal["LONG", "SHORT", "NONE"]` — the LLM's recommended trade direction. `NONE` is a valid and expected outcome.
  - `stop_loss: float | None` — LLM-suggested stop loss level; may differ from ATR-based stop (REQ-SL-001). `None` if `direction` is `NONE`.
  - `take_profit: float | None` — LLM-suggested take profit level. `None` if `direction` is `NONE`.
  - `confidence: int` — LLM confidence in the direction recommendation, in the range 0–100.
  - `position_size_multiplier: Literal[0.25, 0.5, 0.75, 1.0]` — suggested scaling of the calculated position size (REQ-RISK-004). `NONE` direction must produce a multiplier of `0.25` or lower, not `1.0`.
  - `rationale: str` — one sentence explaining why the LLM chose this direction over alternatives.
- The LLM is instructed (via the prompt template) to return a JSON block conforming to the `LLMDecision` schema in addition to the plain English explanation. The JSON block and the explanation are returned in the same response.
- The prompt template instructs the LLM that `NONE` is the correct direction when evidence is mixed, stale, or insufficient, and that `NONE` is preferable to a low-confidence directional call.
- The prompt template is stored in a dedicated file or config location, consistent with REQ-LLM-003's prompt storage requirement.

**Assumption A-029:** The LLM's `stop_loss` and `take_profit` values are advisory outputs derived from the model's qualitative assessment of the context. They do not replace the ATR-based values from REQ-SL-001 and REQ-SL-002. Both sets of values are displayed to the user; the ATR-based values remain the default for position sizing.

---

#### REQ-LLMDEC-002 — Structured decision response parsing

**Requirement:** The system must parse the `LLMDecision` JSON block from the LLM response. If parsing fails, the system must degrade gracefully without surfacing an error to the user.

**Acceptance criteria:**
- The response parser extracts the JSON block from the LLM response and deserialises it into an `LLMDecision` object.
- If the JSON block is absent, malformed, or fails schema validation, the parser returns a default `LLMDecision` with `direction="NONE"`, `confidence=0`, `position_size_multiplier=0.25`, and `rationale="LLM decision unavailable."`. It does not raise an exception.
- The parse failure is logged at `WARNING` level with the raw response excerpt (truncated to 200 characters) for diagnostics.
- The explanation string is still returned even when decision parsing fails; the two outputs are independent.
- A unit test simulates a malformed JSON block in the LLM response and confirms the default `LLMDecision` is returned without raising an exception.

---

#### REQ-LLMDEC-003 — Discretionary constraint preserved

**Requirement:** The LLM decision output must not trigger any automated action. All LLM direction recommendations remain advisory; user approval is required before any order is placed.

**Acceptance criteria:**
- No code path exists in which an `LLMDecision` with `direction="LONG"` or `direction="SHORT"` directly initiates an order submission without passing through the approval workflow (REQ-APPROVE-001 and REQ-APPROVE-002).
- The dashboard displays the LLM decision as a recommendation card, not as a pending order.
- The confirm modal (REQ-APPROVE-002) shows the LLM decision alongside the technical signal; the user retains full control over whether to approve.
- An automated test confirms that calling `place_order` directly from a `LLMDecision` object raises an `AuthorisationError` — i.e. no such direct call path exists in the codebase.

---

#### REQ-LLMDEC-004 — LLM vs technical signal comparison and conflict display

**Requirement:** When the LLM direction contradicts the technical signal direction, the conflict must be displayed prominently. The system must not silently resolve or suppress the disagreement.

**Acceptance criteria:**
- A conflict is defined as: technical signal is `LONG` and LLM direction is `SHORT` or `NONE`; or technical signal is `SHORT` and LLM direction is `LONG` or `NONE`.
- When a conflict exists, the dashboard displays a `LLM/SIGNAL CONFLICT` warning card for that instrument, showing both directions side-by-side: e.g. `Technical: LONG | LLM: NONE`.
- The conflict flag is stored as a boolean field `llm_signal_conflict` in the signal cache (alongside `LLMDecision`) so it can be read on subsequent dashboard loads without re-evaluation.
- The LLM rationale for its direction is always displayed in the conflict card, regardless of confidence score.
- A unit test verifies that a technical signal of `LONG` and an LLM direction of `NONE` produces `llm_signal_conflict=True`.

---

### 11.6 Guardrails

#### Objective

Define explicit constraints that prevent the system from surfacing low-quality or poorly-supported signals for user action, while ensuring that conflicts and uncertainties are visible rather than suppressed.

---

#### REQ-GUARD-001 — "No trade" is a valid and first-class outcome

**Requirement:** The system must treat a "no trade" recommendation — whether from the LLM (REQ-LLMDEC-001) or from guardrail evaluation — as a substantive, displayable outcome, not as an absence of output or a system error.

**Acceptance criteria:**
- An LLM decision of `direction="NONE"` is displayed in the dashboard with the same visual weight as `LONG` or `SHORT`, including the rationale and confidence score.
- A signal that is blocked by a guardrail (REQ-GUARD-002 or REQ-GUARD-003) is displayed with a `BLOCKED` status and the specific guardrail reason. It is not silently hidden.
- `BLOCKED` signals are included in the signal history (REQ-JOURNAL-002) with a `block_reason` field populated.
- A unit test verifies that a signal blocked by REQ-GUARD-002 appears in the signal history with `status="blocked"` and a non-null `block_reason`.

---

#### REQ-GUARD-002 — Price confirmation gate

**Requirement:** A signal must not be surfaced for user approval unless it passes a minimum price confirmation check, ensuring the technical evidence for the signal is present and measurable.

**Acceptance criteria:**
- A signal passes price confirmation if both of the following are true: `signal_strength_pct > 0` (the SMA gap is non-zero) AND `confidence_score >= 50` (REQ-QUAL-001).
- Signals that fail this check are assigned `status="blocked"` with `block_reason="price_confirmation_failed"`. They are displayed in the dashboard with a `BLOCKED` badge but are not shown in the pending approval queue.
- `PRICE_CONFIRMATION_MIN_STRENGTH` (0) and `PRICE_CONFIRMATION_MIN_CONFIDENCE` (50) are defined as named constants; they are not magic numbers.
- A unit test verifies: `signal_strength_pct=0.5` and `confidence_score=75` → passes; `signal_strength_pct=0.5` and `confidence_score=25` → blocked; `signal_strength_pct=0.0` and `confidence_score=100` → blocked.

---

#### REQ-GUARD-003 — Event freshness gate

**Requirement:** A signal must not be surfaced for user approval if all available context events are stale (i.e. older than `STALE_EVENT_THRESHOLD_DAYS` from REQ-EVENT-003) AND no `IGSentiment` data is available. When fresh context is absent, the signal is shown with a warning, not blocked outright.

**Acceptance criteria:**
- If `event_freshness.total_event_count = 0` OR `event_freshness.newest_event_age_days >= STALE_EVENT_THRESHOLD_DAYS`, AND `ig_sentiment` is `None`, the dashboard displays a `STALE CONTEXT` warning banner on the signal card: `"No recent events available for this instrument. Signal context may not reflect current conditions."`.
- The `STALE CONTEXT` warning does not block the signal from appearing in the approval queue; it is advisory only. The user may still approve or reject.
- If fresh sentiment data (`ig_sentiment` is not `None`) is available, the `STALE CONTEXT` warning is suppressed even if all events are stale, since sentiment data provides some current positioning context.
- The stale context check uses `STALE_EVENT_THRESHOLD_DAYS` from REQ-EVENT-003; it is not a separately defined constant.
- A unit test verifies: `total_event_count=0` and `ig_sentiment=None` → warning displayed; `total_event_count=0` and `ig_sentiment` populated → no warning.

---

#### REQ-GUARD-004 — Conflicting signals must be surfaced, not suppressed

**Requirement:** When multiple conflict conditions exist simultaneously on the same instrument, all active conflicts must be displayed. No conflict may be hidden because another conflict is already visible.

**Acceptance criteria:**
- The following conflict types are independently tracked and displayed:
  1. `conflicting_indicators` — technical indicators disagree (REQ-QUAL-003).
  2. `llm_signal_conflict` — LLM direction contradicts technical signal (REQ-LLMDEC-004).
  3. `high_volatility` — ATR spike warning (REQ-QUAL-004).
- All active conflict flags are stored in the signal cache as separate boolean fields.
- The dashboard renders each conflict as a separate badge or warning line on the signal card. A signal card with three active conflicts displays three visible warnings; they are not collapsed into a single generic warning.
- The confirmation modal (REQ-APPROVE-002) also surfaces all active conflict warnings before the user confirms an order.
- A unit test verifies that a signal with all three conflict flags set to `True` produces three distinct warning entries in the rendered signal card data structure.

---

### 11.7 Data Cost Constraint

#### Objective

Constrain the Market Context Engine and all supporting data integrations to free or low-cost data sources. The system must not introduce dependencies on paid data providers without an explicit decision and documentation.

---

#### REQ-COST-001 — Free and low-cost data sources only

**Requirement:** All data sources used by the Market Context Engine (section 11) and by the LLM explanation subsystem (section 3.7) must be free or accessible via the existing IG account subscription. No additional paid data service may be introduced without an explicit decision record.

**Acceptance criteria:**
- The following sources are explicitly permitted:
  - IG REST API (client sentiment, market data, open positions) — covered by existing IG account.
  - yfinance (price OHLCV, news headlines via `Ticker.news`) — free, no auth.
  - Investing.com RSS feed or equivalent free economic calendar (as specified in REQ-CTX-001) — free, no auth.
  - EIA public data API (e.g. `https://api.eia.gov`) — free, requires free registration key stored in `.env`.
  - OPEC public website data (scraped or RSS where available) — free, no subscription.
- The following sources are explicitly prohibited:
  - Reuters Eikon / Refinitiv Elektron API.
  - Bloomberg Terminal API or Bloomberg Data License.
  - Quandl premium datasets (free Quandl datasets are permitted if relevant).
  - Any service with a per-call cost or a monthly subscription fee above £0, unless already covered by the existing IG account.
- A `config/data_sources.yaml` file documents each active data source, its cost classification (`free` / `ig_included` / `paid_excluded`), and the environment variable or config key used to access it.
- Any attempt to add a new data source to the Market Context Engine must include an update to `config/data_sources.yaml` as part of the same change. A CI check (or pre-commit hook) verifies this file exists and is valid YAML before merging.
- A unit test confirms that `config/data_sources.yaml` contains no entry with `cost_classification: paid` (which would indicate a paid source has been introduced in violation of this requirement).

**Assumption A-030:** The EIA API free registration key has no usage cost and provides sufficient data for Phase 1 commodity inventory data (crude oil, natural gas). If EIA imposes fees, it must be removed from the permitted list and `config/data_sources.yaml` updated.

---

*End of Trading Lab Requirements — v2.1*
*Supersedes: `docs/requirements-phase1.md`*





