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
4. [Phase 2 — IG Demo Account, Paper Trading, Signal Approval Workflow](#4-phase-2--ig-demo-account-paper-trading-signal-approval-workflow)
   - 4.1 [IG API Integration](#41-ig-api-integration)
   - 4.2 [Signal Approval Workflow](#42-signal-approval-workflow)
   - 4.3 [Paper Trade Execution and Position Tracking](#43-paper-trade-execution-and-position-tracking)
   - 4.4 [Trade Journal and Signal History](#44-trade-journal-and-signal-history)
   - 4.5 [Streamlit Dashboard — Phase 2 Additions](#45-streamlit-dashboard--phase-2-additions)
   - 4.6 [Non-Functional Requirements — Phase 2](#46-non-functional-requirements--phase-2)
5. [Phase 3 — IG Live Account, Indices, Live Risk Controls](#5-phase-3--ig-live-account-indices-live-risk-controls)
   - 5.1 [Live Order Placement](#51-live-order-placement)
   - 5.2 [Live Position and Account Monitoring](#52-live-position-and-account-monitoring)
   - 5.3 [Risk Controls for Live Capital](#53-risk-controls-for-live-capital)
   - 5.4 [Indices Expansion](#54-indices-expansion)
   - 5.5 [Streamlit Dashboard — Phase 3 Additions](#55-streamlit-dashboard--phase-3-additions)
   - 5.6 [Non-Functional Requirements — Phase 3](#56-non-functional-requirements--phase-3)
6. [Discretionary Workflow — End to End](#6-discretionary-workflow--end-to-end)
7. [Gaps and Contradictions](#7-gaps-and-contradictions)
8. [Assumptions Register](#8-assumptions-register)
9. [Open Questions](#9-open-questions)
10. [Dependency Map](#10-dependency-map)

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

Out of scope:
- Any broker API integration beyond the existing execution stub
- Live order placement in any form (paper or live)
- Machine learning or statistical models
- Portfolio optimisation or mean-variance allocation
- Cloud storage or deployment
- Real-time streaming data
- Trade journal (requires position state — deferred to Phase 2)
- Signal history persistence and vs-actual tracking (deferred to Phase 2)
- Instrument correlation analysis (deferred — depends on having a clean multi-instrument dataset first)
- Exposure summary with deployed capital (requires execution layer — deferred to Phase 2)

### Phase 2 — IG Demo Account (paper trading, signal approval, no live capital at risk)

In scope:
- Authenticating to IG demo account via REST API
- Submitting paper orders to IG demo account in response to user-approved signals
- Monitoring open demo positions via IG Streaming API
- Signal approval workflow in the Streamlit dashboard (approve/reject buttons)
- Trade journal persisted to disk
- Signal history persistence (what was recommended vs what happened)
- Exposure summary (demo account positions)
- Live market data via IG Streaming API replacing yfinance for execution timing

Out of scope:
- Any action against the IG live account
- Automated execution without user approval
- Indices instruments (Phase 3)

### Phase 3 — IG Live Account (real capital, expanded instruments, live risk controls)

In scope:
- Switching from demo to live IG credentials via a single config/env change
- Enforcing pre-execution risk controls (position limits, daily loss limit, exposure cap)
- Adding indices instruments to the watchlist and signal pipeline
- Actual vs backtest performance tracking
- Kill switch to halt all activity within 60 seconds

Out of scope:
- Forex instruments (future phase)
- Fully automated execution without user approval (may be considered as a future phase)

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

**Requirement:** The backtest engine must not allow a signal generated on bar N to result in a trade executed at bar N's close price. Execution must occur at the open of bar N+1.

**Acceptance criteria:**
- The engine shifts the signal column by one bar before applying it to price series.
- A unit test constructs a synthetic signal series where a signal fires on bar 5 and confirms no position change occurs before bar 6.
- The assumed execution price (next-bar open) is documented in a module-level docstring in `engine.py`.
- A comment records the known limitation: daily OHLC data from yfinance does not expose intraday open prices; next-bar open is approximated as next-bar close for the Phase 1 cost model.

**Open question OQ-BT-001:** If execution is intended to occur at next-day open rather than next-day close, the backtest will overstate achievable returns for trending strategies. A decision on execution price assumption must be recorded before the first backtest result is shared externally.

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

**Requirement:** A function must exist that, given the full instrument list and a target strategy, returns a consolidated signal summary across all instruments for the most recent available bar.

**Acceptance criteria:**
- The output is a DataFrame with one row per instrument containing at minimum: `symbol`, `name`, `timestamp_of_last_bar`, `signal`, `close`, `fast_sma`, `slow_sma`, `rsi`.
- If a curated data file is absent for an instrument, that instrument appears in the output with `signal=None` and `status="data_missing"`, not as a missing row.
- The function does not trigger a data refresh; it operates on whatever curated files are currently on disk.
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
- The table reflects the most recently computed signals from curated data on disk; it does not recompute signals on each page load. A manual refresh button triggers recomputation.

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

---

## 4. Phase 2 — IG Demo Account, Paper Trading, Signal Approval Workflow

Phase 2 begins only after Phase 1 is complete and all Phase 1 tests pass. No Phase 2 code may be merged until Phase 1 is stable.

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
- Position size is calculated as: `(account_balance * risk_per_trade_pct) / (entry_price - stop_loss_price)`, where all inputs are displayed to the user.
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

## 5. Phase 3 — IG Live Account, Indices, Live Risk Controls

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

#### REQ-RISK-001 — Kill switch

**Requirement:** The system must provide a single action that closes all open positions and prevents any new orders from being placed.

**Acceptance criteria:**
- A Kill Switch button is visible on every page of the dashboard when `IG_ENVIRONMENT=live`.
- Clicking the Kill Switch opens a confirmation modal. Confirming the modal triggers a close request for every open position via the IG REST API.
- After activation, the system enters a `halted` state. No new orders can be submitted until the `halted` state is manually cleared by restarting the application.
- The Kill Switch must complete all close requests (or exhaust retries) within 60 seconds. The dashboard displays a countdown and the status of each position closure.
- The Kill Switch activation event is logged to `logs/orders.log` with a timestamp and the positions affected.

---

#### REQ-RISK-002 — Risk parameter configuration

**Requirement:** All risk limits governing live trading must be readable from `config/environments/local.yaml` and must not require code changes to adjust.

**Acceptance criteria:**
- The following parameters are configurable: `risk.daily_loss_limit_pct`, `risk.max_exposure_pct`, `risk.max_open_positions`, `risk.risk_per_trade_pct`, `risk.default_stop_pct`.
- The application validates all risk parameters at startup and raises a `ConfigValidationError` if any value is outside a sane range (e.g. `daily_loss_limit_pct > 50` is rejected as an unsafe value).
- Changing a risk parameter requires an application restart; there is no hot-reload of risk config.

---

### 5.4 Indices Expansion

#### REQ-IDX-001 — Indices instrument support

**Requirement:** Phase 3 adds index instruments to `instruments.yaml`. The system must support these without code changes.

**Acceptance criteria:**
- `asset_class: index` is a valid value (already in the permitted set from REQ-DATA-007).
- Index instruments added to `instruments.yaml` are ingested, signal-generated, and displayed in the dashboard identically to commodity instruments.
- Each index instrument entry in `instruments.yaml` includes its IG epic for order placement.
- The signal table groups instruments by `asset_class` to separate commodities from indices visually.

---

### 5.5 Streamlit Dashboard — Phase 3 Additions

#### REQ-UI-013 — Kill switch button

**Requirement:** A Kill Switch button is visible on all pages when `IG_ENVIRONMENT=live`, as specified in REQ-RISK-001.

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

## 6. Discretionary Workflow — End to End

This section describes the complete operational workflow in Phase 1 (research only) and Phase 2 (signal approval and paper execution). It is the reference for UI designers and engineers implementing the dashboard interaction model.

### 6.1 Daily Research Workflow (Phase 1)

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
   - Results written to an in-memory signal summary (not persisted in Phase 1).
   - Signal table on Dashboard page updates.

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

### 6.2 Signal Approval and Paper Trade Workflow (Phase 2)

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

### 6.3 Key Decision Points and Human Judgment Boundaries

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

## 7. Gaps and Contradictions

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

Phase 1 computes signals in memory only. Phase 2 requires signal history persistence for the approval workflow. The transition from in-memory signals to persisted signals requires defining the persistence format before Phase 2 begins. This should be designed during Phase 1 even if the write path is not active until Phase 2.

### CONFLICT-001 — Backtest engine short-selling constraint vs broker capability

The previous `requirements-phase1.md` explicitly prohibited short selling in the backtest engine ("long/flat only"). The confirmed broker (IG spreadbetting) supports shorts on all instruments and is specifically designed for it. The prohibition was an explicit simplification, not a business constraint. It must be removed and REQ-BT-004 must replace it.

### CONFLICT-002 — yfinance futures symbols vs IG spreadbetting epics

yfinance uses continuous futures symbols (e.g. `GC=F` for Gold). IG spreadbetting uses its own epic system and does not map directly from Yahoo symbols. The signal generation layer uses yfinance symbols throughout. Before Phase 2, a mapping table between yfinance symbols and IG epics must be established and maintained. Any mismatch will cause Phase 2 order placement to fail silently or route to the wrong instrument.

---

## 8. Assumptions Register

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

## 9. Open Questions

These questions must be answered before the indicated requirement can be finalised. Each question is an explicit blocker or a risk to correctness.

| ID | Question | Blocks | Priority |
|---|---|---|---|
| OQ-BT-001 | Should the backtest execute at next-bar open or next-bar close? Next-bar close is current behaviour and likely overstates returns. | REQ-BT-002 | High |
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
| OQ-RISK-001 | What are the target values for `risk.daily_loss_limit_pct`, `risk.max_exposure_pct`, and `risk.risk_per_trade_pct`? These must be set before Phase 3 goes live. | REQ-LIVE-002, REQ-RISK-001 | High (for Phase 3) |
| OQ-MTF-001 | How should the annualisation constant be determined for weekly bars — from BacktestConfig, from the data's inferred frequency, or from instruments.yaml? | REQ-BT-008 | Low |

---

## 10. Dependency Map

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
    --> REQ-RISK-001 (kill switch)
    --> REQ-UI-013 (kill switch button)
    --> REQ-UI-015 (risk dashboard panel)

REQ-IDX-001 (indices instruments)
    --> REQ-DATA-007 (instrument registry — asset_class: index already permitted)
    --> REQ-EXEC-001 (order submission — ig_epic field required per instrument)
```

---

*End of Trading Lab Requirements — v2.0*
*Supersedes: `docs/requirements-phase1.md`*
