# Phase 1 Requirements: Core Research

**Document status:** Draft — pending resolution of the trading style blocker (see Section 1).
**Scope:** Data ingestion, signal generation, backtesting, watchlist management.
**Explicitly out of scope:** Broker integration, live order placement, paper trading mode.
**Date:** 2026-03-30

---

## Table of Contents

1. [Critical Blocker: Trading Style](#1-critical-blocker-trading-style)
2. [Scope Boundaries](#2-scope-boundaries)
3. [Data Ingestion and Normalisation](#3-data-ingestion-and-normalisation)
4. [Signal Generation](#4-signal-generation)
5. [Backtesting and Evaluation](#5-backtesting-and-evaluation)
6. [Watchlist Management](#6-watchlist-management)
7. [Price Charts and Indicator Overlays](#7-price-charts-and-indicator-overlays)
8. [Multi-Timeframe Analysis](#8-multi-timeframe-analysis)
9. [Non-Functional Requirements](#9-non-functional-requirements)
10. [Gaps and Contradictions](#10-gaps-and-contradictions)
11. [Assumptions Register](#11-assumptions-register)
12. [Open Questions](#12-open-questions)
13. [Dependency Map](#13-dependency-map)

---

## 1. Critical Blocker: Trading Style

**This is the single most important decision before requirements for signal generation, risk controls, and any UI can be finalised.**

The system has no defined stance on how recommendations become actions. The three possible modes produce fundamentally different system designs:

| Mode | System behaviour | Risk surface |
|---|---|---|
| Discretionary | System recommends; user decides and acts manually | Low — no execution path needed in Phase 1 |
| Semi-automated | System recommends; user approves; system executes | Medium — approval workflow and execution stub required |
| Fully automated | System detects signal; system executes without user review | High — requires kill switches, position limits, and circuit breakers before any execution code ships |

**Required answers before signal and execution requirements can be finalised:**

1. When the system emits a buy signal for a watched instrument, what is the expected next step — a notification, a manual trade, or an automated order?
2. Is human review required before any capital is committed, even in paper trading mode?
3. If the system is eventually semi- or fully-automated, must a human be able to halt all activity in under 60 seconds?
4. Will the system manage open positions (trailing stops, take-profit exits), or only entry signals?
5. Is there a maximum number of concurrent open positions, or a maximum total capital exposure percentage, that the system must enforce?

**Until these are answered, requirements in Sections 4 and onwards are written for the discretionary mode.** That is: the system outputs recommendations; no execution path is included in Phase 1. If the mode changes, execution, approval, and risk-control requirements must be added before any broker adapter is activated.

---

## 2. Scope Boundaries

### In scope for Phase 1

- Fetching and persisting market data via yfinance
- Normalising raw data into the project bar schema
- Generating signals from rule-based strategies
- Running backtests from normalised data with explicit cost assumptions
- Reporting backtest performance metrics
- Managing a watchlist of instruments via YAML configuration
- Rendering price charts with indicator overlays for notebook-based inspection
- Multi-timeframe data ingestion (daily and weekly bars)

### Out of scope for Phase 1

- Live or paper order placement via any broker API
- IG API integration beyond the existing stub
- Machine learning or statistical models
- Portfolio optimisation or mean-variance allocation
- Cloud storage or deployment
- Real-time streaming data
- Trade journal (operational feature, deferred to Phase 2)
- Signal history persistence and vs-actual tracking (deferred to Phase 2)
- Instrument correlation analysis (deferred — dependency on multi-instrument curated dataset)
- Exposure summary and deployed capital tracking (deferred — requires position state, which implies execution)

---

## 3. Data Ingestion and Normalisation

### Objective

Fetch market data from yfinance, persist it in both raw and curated form, and guarantee the curated dataset conforms to a fixed schema before any downstream code consumes it.

### REQ-DATA-001 — Raw persistence

**Requirement:** The ingestion pipeline must write the source-shaped yfinance payload to `data/raw/<symbol>_<interval>_<source>.parquet` before any transformation is applied.

**Acceptance criteria:**
- The raw file exists on disk after a successful ingest run.
- The raw file is not modified by the normalisation step.
- A second ingest run for the same symbol and interval overwrites the existing raw file and logs the overwrite.

**Assumption:** Overwrite-on-refresh is acceptable. Versioned history of raw files is not required in Phase 1.

---

### REQ-DATA-002 — Curated schema

**Requirement:** The curated dataset for any instrument must conform to the schema `timestamp, open, high, low, close, volume, symbol, source`, where `timestamp` is a timezone-aware UTC datetime.

**Acceptance criteria:**
- A schema validation function raises a descriptive error if any required column is absent.
- `timestamp` values are UTC-aware `datetime64[ns, UTC]`; a test asserts this type explicitly.
- `symbol` and `source` columns are populated from the ingest request, not inferred from filenames.
- No rows with a null `close` price are written to the curated file.

---

### REQ-DATA-003 — Adjusted vs unadjusted flag

**Requirement:** Every curated file must carry metadata indicating whether prices are split- and dividend-adjusted.

**Acceptance criteria:**
- The curated Parquet file includes an `adjusted` boolean column, or a sidecar metadata file contains the flag.
- The flag is set from `MarketDataRequest.adjusted`, not hardcoded.
- A curated file written with `adjusted=False` cannot be silently consumed by a strategy that expects adjusted prices — the consuming code must check or the schema must enforce it.

**Open question OQ-DATA-001:** Is there a use case for unadjusted prices in Phase 1? If not, `adjusted=True` should be the only permitted value and the field can be a schema invariant rather than a variable.

---

### REQ-DATA-004 — Scheduled daily refresh

**Requirement:** A script must exist that, when run, refreshes market data for all instruments listed in `config/instruments.yaml`.

**Acceptance criteria:**
- Running the script with no arguments processes every instrument in the YAML.
- If yfinance returns no data for a symbol, the script logs the failure with the symbol name and continues processing remaining symbols — it does not abort.
- The script exit code is non-zero if any symbol failed to ingest.
- The script does not delete existing curated files before confirming the new download is non-empty.

**Assumption:** The schedule trigger (cron, task scheduler, manual) is outside the scope of this requirement. The script must be triggerable from the command line.

---

### REQ-DATA-005 — Data validation on ingest

**Requirement:** The normalisation step must detect and reject data quality problems before writing the curated file.

**Acceptance criteria:**
- Rows where `close <= 0` are logged as anomalies and excluded from the curated output.
- If more than 5% of rows in a downloaded payload have null `close` values, the ingest raises an error rather than writing a partially populated curated file.
- If the downloaded date range does not overlap with the requested period by at least one bar, the ingest raises a descriptive error.
- Timezone conversion from exchange-local time to UTC is explicit in the transform code, not delegated to pandas defaults.

**Assumption:** The 5% null threshold is a placeholder. The correct value depends on asset class and intended period. This must be confirmed before implementation.

---

### REQ-DATA-006 — Multi-timeframe ingestion

**Requirement:** The ingestion layer must support both daily (`1d`) and weekly (`1wk`) intervals for the same symbol, stored as separate files.

**Acceptance criteria:**
- `MarketDataRequest` accepts `interval` values of at least `"1d"` and `"1wk"`.
- Daily and weekly files for the same symbol are stored under distinct filenames and do not overwrite each other.
- A weekly bar dataset for the same symbol and period contains fewer rows than its daily equivalent, and a test asserts this relationship.
- Unsupported interval values cause the request to fail at construction time, not at download time.

---

### REQ-DATA-007 — Instrument registry

**Requirement:** `config/instruments.yaml` is the single source of truth for which instruments the system will ingest and analyse.

**Acceptance criteria:**
- Adding an instrument to `instruments.yaml` is sufficient for the daily refresh script to include it; no code change is required.
- Each instrument entry must declare: `symbol`, `asset_type`, `timeframe`, `source`, `session_timezone`, and `adjusted_prices`.
- The config loader raises a validation error at startup if any required field is missing from an instrument entry.
- Instruments not in `instruments.yaml` cannot be ingested by the refresh script.

---

## 4. Signal Generation

> Note: Requirements in this section assume discretionary mode (system recommends, user decides). If trading style is confirmed as semi-automated or automated, additional requirements must be written for approval workflows, execution gating, and signal state persistence.

### Objective

Allow rule-based strategies to consume normalised bar data and emit a signal column that downstream components — backtesting engine and human reviewer — can consume without knowledge of the strategy's internals.

### REQ-SIG-001 — Strategy interface contract

**Requirement:** Every strategy must implement the `Strategy` abstract base class, accepting a bars `DataFrame` and returning a signals `DataFrame` that includes the original columns plus at least a `signal` column.

**Acceptance criteria:**
- A strategy that does not return a `signal` column raises a `ValueError` before any backtest or display code consumes it.
- The `signal` column contains only integer values from `{-1, 0, 1}`. Any other value causes a validation error.
- A strategy does not perform file I/O, network calls, or broker API calls. A test confirms that strategy `generate_signals` can be called with a static in-memory DataFrame with no external dependencies.
- Strategy parameters are accepted at construction time and are not read from global state or environment variables inside `generate_signals`.

---

### REQ-SIG-002 — Strategy parameterisation via YAML

**Requirement:** Strategy parameters must be loadable from a YAML file in `config/strategies/`, with no parameter values hardcoded in strategy class defaults that contradict the config.

**Acceptance criteria:**
- A loader function reads a strategy YAML file and returns a constructed strategy instance with parameters applied.
- If a required parameter is absent from the YAML file, the loader raises a descriptive error identifying the missing field.
- The same strategy class can be instantiated with two different YAML files and produces different signals for the same input data.
- Strategy YAML schema is documented by a comment block or inline schema in the YAML file itself.

---

### REQ-SIG-003 — SMA cross reference strategy

**Requirement:** The SMA cross strategy must be fully implemented as the reference strategy and must be exercisable end-to-end from a curated Parquet file to a signals DataFrame.

**Acceptance criteria:**
- `SmaCrossStrategy` accepts `fast_window` and `slow_window` as constructor parameters.
- Constructing an instance where `fast_window >= slow_window` raises a `ValueError`.
- Signals are not emitted for the first `slow_window - 1` bars (warm-up period); those rows carry `signal = 0`.
- A buy signal (`signal = 1`) appears on the first bar where `fast_sma` crosses above `slow_sma`.
- A sell signal (`signal = -1`) appears on the first bar where `fast_sma` crosses below `slow_sma`.
- All of the above are verified by unit tests with a synthetic bar dataset.

---

### REQ-SIG-004 — Signal output metadata

**Requirement:** The signals DataFrame returned by any strategy must carry enough context for a human reviewer to understand what generated the signal without reading strategy source code.

**Acceptance criteria:**
- The signals DataFrame contains the columns `timestamp`, `close`, and `signal` at minimum.
- For the SMA cross strategy, the intermediate columns `fast_sma` and `slow_sma` are retained in the output.
- A `position_change` column (or equivalent) is present and indicates entry and exit events distinctly from hold rows.

---

### REQ-SIG-005 — Indicator computation (SMA, RSI, MACD)

**Requirement:** The features layer must provide standalone indicator functions for SMA, RSI, and MACD that operate on a price series and return a named Series or DataFrame of computed values.

**Acceptance criteria:**
- Each indicator function accepts a `pd.Series` of close prices and a set of period parameters.
- Each function raises a `ValueError` if the input series is shorter than the minimum required length for the given parameters.
- Indicator functions do not modify the input series in place.
- SMA with `window=20` on a 100-bar series produces exactly 81 non-null values (and 19 null warm-up values).
- RSI with `period=14` produces values in the range `[0, 100]` for all non-null outputs; a test asserts this bound.
- MACD output includes signal line and histogram columns, not only the MACD line.
- All three functions are covered by unit tests using synthetic price data.

---

## 5. Backtesting and Evaluation

### Objective

Run reproducible simulations of strategy performance on historical curated data, with explicit cost assumptions, no lookahead bias, and a defined set of output metrics saved to disk.

### REQ-BT-001 — Backtest configuration contract

**Requirement:** Every backtest run must be fully described by an explicit configuration object. No backtest parameter may be inferred from runtime state or environment variables.

**Acceptance criteria:**
- `BacktestConfig` must declare: `initial_cash`, `commission_bps`, `slippage_bps`, `symbol`, `timeframe`, `start_date`, `end_date`.
- `symbol` and date range fields are currently absent from `BacktestConfig`; they must be added before a backtest result can be reproduced from config alone.
- Running the same `BacktestConfig` against the same curated dataset on two separate runs produces bit-identical equity curve output.
- A backtest cannot be initiated without a fully populated config — partial configs must raise at construction time.

**Gap:** The current `BacktestConfig` model contains only `initial_cash`, `commission_bps`, and `slippage_bps`. It is missing `symbol`, `timeframe`, and date range fields. This must be resolved before REQ-BT-002 can be implemented.

---

### REQ-BT-002 — No-lookahead enforcement

**Requirement:** The backtest engine must not allow a signal generated on bar N to result in a trade executed at bar N's close price. Execution must occur at the open of bar N+1 at the earliest.

**Acceptance criteria:**
- The engine shifts the signal column by one bar before applying it to returns.
- A test constructs a synthetic signal series where a signal fires on bar 5 and confirms no position is taken until bar 6.
- The implementation must document the assumed execution price (next-bar open, next-bar close, or VWAP approximation) in a code comment.

**Open question OQ-BT-001:** Should the backtest engine execute at next-bar open or next-bar close? The current implementation uses next-bar close (`shift(1)` applied to close-to-close returns). If the strategy is intended for end-of-day signals acted on the following morning open, this overstates realisable returns. A decision must be recorded.

---

### REQ-BT-003 — Cost model

**Requirement:** Every backtest must apply a configurable cost deduction on each position change to approximate commission and spread/slippage.

**Acceptance criteria:**
- Cost is applied as `(commission_bps + slippage_bps) / 10000` per unit of position change.
- A zero-cost backtest (both bps set to 0) produces gross returns equal to market returns for a fully-invested long position.
- A test confirms that a strategy producing 100 trades in a backtest incurs a higher cost drag than the same strategy producing 10 trades on the same equity.
- The cost model does not account for bid-ask spread separately from slippage in Phase 1; this is an explicit simplification recorded in the config schema.

---

### REQ-BT-004 — Long/flat only

**Requirement:** The Phase 1 backtest engine supports long and flat positions only. Short selling is not supported and a `signal = -1` must be treated as flat (position = 0), not as a short position.

**Acceptance criteria:**
- Passing a signal of `-1` to the engine produces a position of `0`, not `-1`.
- This behaviour is documented in the engine's docstring.
- A test confirms that an all-short signal series produces an equity curve identical to holding cash.

**Out of scope:** Short-side execution. If short selling becomes a requirement, a new engine variant must be written, not a patch to the existing one.

---

### REQ-BT-005 — Performance metrics

**Requirement:** The backtest reporting module must compute a defined set of performance metrics from an equity curve and trade log.

**Acceptance criteria — the following metrics must be computed and returned:**
- Total return (percentage, from initial cash to final equity)
- Annualised return (CAGR, assuming 252 trading days per year)
- Annualised Sharpe ratio (using risk-free rate of 0% unless overridden in config; 252-day annualisation)
- Maximum drawdown (percentage peak-to-trough on the equity curve)
- Maximum drawdown duration (number of bars from peak to recovery or end of series if unrecovered)
- Win rate (percentage of closed trades with positive net return)
- Number of trades (round-trip entries and exits counted as one trade)
- Average trade return (mean net return per closed trade)

**Acceptance criteria — computation rules:**
- Sharpe ratio uses daily net returns, not gross returns.
- If fewer than two closed trades exist in the result, win rate and average trade return are returned as `None`, not zero.
- All metrics are computed deterministically from the equity curve DataFrame; no random elements.
- A test verifies Sharpe ratio and max drawdown against a hand-calculated reference equity curve.

---

### REQ-BT-006 — Backtest result persistence

**Requirement:** Every completed backtest run must save both a summary metrics file and a bar-level trade log to `data/backtests/`.

**Acceptance criteria:**
- The summary file is a JSON file containing all metrics from REQ-BT-005 plus the full `BacktestConfig` as a nested object.
- The trade log is a Parquet file containing at minimum: `timestamp`, `close`, `signal`, `position`, `net_return`, `equity_curve`.
- Output filenames encode the symbol, timeframe, strategy name, and a run timestamp, e.g. `spy_1d_sma_cross_20260330T1200Z_summary.json`.
- If a file with the same name already exists, the new run does not silently overwrite it — it either appends a suffix or raises an error. The behaviour must be deterministic and documented.
- A backtest that fails mid-run does not write a partial summary file.

---

### REQ-BT-007 — Date range filtering

**Requirement:** The backtest engine must accept and enforce explicit start and end dates, operating only on bars within that range from the curated dataset.

**Acceptance criteria:**
- Bars outside `[start_date, end_date]` are excluded before the engine runs.
- If the curated dataset contains fewer than `slow_window * 2` bars within the specified range, the backtest raises an error rather than producing metrics on insufficient data.
- The start and end dates used in the run are recorded in the summary output.

---

## 6. Watchlist Management

### Objective

Allow the user to define a set of instruments of interest that drives data ingestion, signal generation runs, and chart rendering without code changes.

### REQ-WATCH-001 — YAML-driven instrument list

**Requirement:** `config/instruments.yaml` serves as the watchlist. Adding or removing an instrument from this file is the only action required to include or exclude it from all Phase 1 workflows.

**Acceptance criteria:**
- The refresh script, signal runner, and chart renderer all read from `instruments.yaml`; none maintain their own hardcoded symbol list.
- Removing an instrument from `instruments.yaml` does not delete its existing data files; it only excludes it from future runs.
- A validation step at startup checks that each instrument entry contains all required fields and raises with the instrument symbol identified if any are missing.

---

### REQ-WATCH-002 — Instrument metadata

**Requirement:** Each watchlist entry must carry sufficient metadata to drive ingestion without further user input.

**Acceptance criteria:**
- Required fields per instrument: `symbol` (string), `asset_type` (one of: `etf`, `equity`, `index`, `fx`), `timeframe` (one of supported intervals from REQ-DATA-006), `source` (string), `session_timezone` (valid IANA timezone string), `adjusted_prices` (boolean).
- The config loader rejects any `asset_type` value not in the permitted set.
- The config loader rejects any `timeframe` value not in the permitted set from REQ-DATA-006.
- `session_timezone` is validated as a legal IANA timezone identifier at load time.

---

### REQ-WATCH-003 — Portfolio-level signal view

**Requirement:** A function must exist that, given the full instrument list and a target strategy, returns a consolidated signal summary across all instruments for the most recent available bar.

**Acceptance criteria:**
- The output is a DataFrame with one row per instrument containing: `symbol`, `timestamp_of_last_bar`, `signal`, `close`, `fast_sma`, `slow_sma` (or equivalent strategy-specific columns).
- If a curated data file is absent for an instrument, that instrument appears in the output with `signal = None` and a status of `"data_missing"`, not as a missing row.
- The function does not trigger a data refresh; it operates on whatever curated files are currently on disk.

---

## 7. Price Charts and Indicator Overlays

### Objective

Provide a reproducible chart function that renders OHLC price data with indicator overlays for notebook-based inspection. Chart rendering is for human review only — it is not a system output consumed by any other component.

### REQ-CHART-001 — OHLC chart with indicator overlays

**Requirement:** A chart function must render a price chart for a given symbol with configurable indicator overlays.

**Acceptance criteria:**
- The function accepts a curated DataFrame, a symbol string, and a list of indicator names to overlay.
- Supported overlays in Phase 1: SMA (configurable window), RSI (separate subplot), MACD (separate subplot with signal line and histogram).
- The function raises a `ValueError` if an unsupported indicator name is passed.
- The chart displays a date axis with readable labels for ranges of 6 months or more.
- The function returns a `matplotlib` Figure object so tests can assert the figure was created without rendering to screen.
- The chart function does not write to disk; the caller is responsible for saving if needed.

---

### REQ-CHART-002 — Chart does not modify data

**Requirement:** Calling the chart function must not alter the input DataFrame.

**Acceptance criteria:**
- A test confirms the input DataFrame is identical (shape, dtypes, values) before and after a chart call.

---

## 8. Multi-Timeframe Analysis

### Objective

Support ingestion and strategy execution at both daily and weekly timeframes for the same instrument, with the two datasets stored independently.

### REQ-MTF-001 — Independent timeframe storage

**Requirement:** Daily and weekly curated datasets for the same symbol must be stored as separate Parquet files and must not be derived from each other at read time.

**Acceptance criteria:**
- Filenames for daily and weekly data differ in the interval segment: `spy_1d_yfinance.parquet` vs `spy_1wk_yfinance.parquet`.
- Weekly data is fetched directly from yfinance using `interval="1wk"`, not resampled from daily bars.
- Running a strategy on weekly bars and on daily bars for the same symbol produces two independent result sets.

---

### REQ-MTF-002 — Strategy execution on weekly bars

**Requirement:** The strategy interface and backtest engine must operate without modification on weekly bar data.

**Acceptance criteria:**
- `SmaCrossStrategy.generate_signals` produces correct signals when given weekly bars as input.
- The backtest engine's Sharpe ratio annualisation uses 52 weeks per year when the input timeframe is weekly, not 252.

**Open question OQ-MTF-001:** How should the annualisation constant be determined — from the `BacktestConfig`, from the data's inferred bar frequency, or from `instruments.yaml`? This must be decided before REQ-MT-002's acceptance criteria can be fully tested.

---

## 9. Non-Functional Requirements

### REQ-NFR-001 — Reproducibility

A backtest run given the same config and the same curated Parquet file must produce bit-identical output on any machine running the same Python version and package versions declared in `pyproject.toml`. No random seeds, no system-clock-dependent logic inside the engine.

### REQ-NFR-002 — Test coverage for core paths

The following code paths must have at least one automated test before Phase 1 is considered complete:
- Data normalisation (schema, UTC timestamp, null rejection)
- Strategy signal generation (warm-up period, crossover detection, signal value constraints)
- Backtest engine (lookahead prevention, cost application, metrics calculation)
- Config loading and validation (missing fields, invalid values)

A `tests/` directory does not currently exist in the repository. It must be created as part of Phase 1.

### REQ-NFR-003 — No secrets in version control

All broker credentials, API keys, and account identifiers must be stored only in `.env` and must never appear in committed files. The `.gitignore` must exclude `.env`. CI or pre-commit hooks must verify no credential patterns are committed.

### REQ-NFR-004 — Configuration over code for strategy parameters

No strategy parameter value may be hardcoded in strategy source files in a way that silently takes precedence over the YAML config. Default values in constructors are permitted only as fallbacks when no config is provided.

### REQ-NFR-005 — Notebooks are not the system of record

No curated data, backtest result, or signal output may exist only inside a notebook. All such outputs must originate from scripts or package code and be written to the defined data directories. Notebooks may read from those directories for visualisation.

### REQ-NFR-006 — Ingest script idempotency

Running the data refresh script twice for the same instrument and date must not corrupt or double-write data. The resulting curated file must be identical to the output of a single run.

---

## 10. Gaps and Contradictions

### GAP-001 — BacktestConfig is missing required fields

`BacktestConfig` currently carries `initial_cash`, `commission_bps`, and `slippage_bps` only. There is no `symbol`, `timeframe`, `start_date`, or `end_date`. A backtest result saved to disk today cannot be reproduced from config alone. This must be resolved before REQ-BT-001 and REQ-BT-006 can pass.

### GAP-002 — No tests directory exists

The repository has no `tests/` directory and no test suite. REQ-NFR-002 requires tests for all core paths. This is the largest implementation gap relative to the stated architectural principles.

### GAP-003 — Signal contract is not enforced at the boundary

`Strategy.generate_signals` returns a DataFrame but the base class does not validate that the return value contains a `signal` column, or that signal values are within `{-1, 0, 1}`. Any code consuming the result can silently receive a malformed DataFrame. A post-call validation step is needed either in the base class or in a dedicated validator.

### GAP-004 — Backtest engine only supports long/flat but signals emit -1

`SmaCrossStrategy` emits `signal = -1` when fast SMA is below slow SMA. The backtest engine clips signals at 0 (long/flat only). This means the strategy and the engine have mismatched semantics: the strategy's sell signal carries no information in the backtest. The strategy should either emit `{0, 1}` only, or the engine's long/flat behaviour must be more explicitly communicated to avoid the assumption that `-1` means short.

### GAP-005 — No run-level logging or audit trail

Scripts and the backtest engine produce no structured log output. If an ingest run fails silently (e.g. yfinance returns an empty frame that bypasses the empty-check), there is no record of what ran, when, or what was skipped. REQ-DATA-004 requires non-zero exit codes on failure, but structured logging to `logs/` is not specified and should be added.

### GAP-006 — Correlation analysis and exposure summary are listed as Phase 1 candidates but depend on Phase 2 state

Instrument correlation analysis requires a multi-instrument curated dataset, which is achievable in Phase 1. However, "exposure summary (capital deployed vs available)" implies the system has knowledge of open positions. Position state only exists if there is an execution layer. This feature cannot be built in Phase 1 without a simulated position tracker, which is a scope expansion. It has been deferred.

### GAP-007 — `backtrader` is installed but not used

`pyproject.toml` / the dev environment includes `backtrader` as a dependency, but the project has built its own backtest engine. Either `backtrader` should be removed from dependencies to reduce confusion, or a decision should be made to adopt it and retire the custom engine. The two cannot coexist without creating ambiguity about which is the authoritative backtesting path.

### GAP-008 — Adjusted prices flag is in the request but not in the curated output

`MarketDataRequest` carries an `adjusted` field. The normalised schema in `transforms.py` does not write this flag into the curated Parquet file. A strategy consuming a curated file has no way to verify whether it is operating on adjusted or unadjusted prices without reading the ingestion request — which is not persisted.

---

## 11. Assumptions Register

| ID | Assumption | Impact if wrong |
|---|---|---|
| A-001 | yfinance is the only data source for Phase 1 | Low — source field is in schema; adding a new source requires a new ingest function, not a schema change |
| A-002 | All instruments use daily bars as the primary timeframe | Low — weekly ingestion is included as a secondary path |
| A-003 | The backtest engine is long/flat only; short selling is not a Phase 1 concern | Medium — the SMA cross strategy emits `-1` signals that are currently ignored by the engine |
| A-004 | 252 trading days is the correct annualisation constant for daily strategies | Low for relative comparisons; medium for absolute Sharpe values. Must be confirmed for weekly timeframe |
| A-005 | Overwriting curated files on each refresh is acceptable; no historical versions need to be kept | Medium — if data quality changes upstream (e.g. survivorship bias adjustment), old backtests cannot be reproduced |
| A-006 | Signal output is for human consumption in Phase 1; no persistence of signal history is required | High — if trading style is confirmed as semi- or fully-automated, signal persistence becomes a hard requirement |
| A-007 | Risk-free rate for Sharpe calculation is 0% | Low for comparison purposes; would be wrong for absolute interpretation |
| A-008 | The `.env` file contains all secrets; no secrets are in YAML config files | High — if a strategy YAML contains API keys or credentials, they will be committed to version control |

---

## 12. Open Questions

| ID | Question | Blocks |
|---|---|---|
| OQ-STYLE-001 | What is the intended trading style: discretionary, semi-automated, or fully automated? | Signal persistence, execution requirements, risk controls, approval workflows |
| OQ-STYLE-002 | Does the user intend to manage open positions (trailing stops, exits) or only entry signals? | Position management requirements, execution layer scope |
| OQ-DATA-001 | Is there a Phase 1 use case for unadjusted prices? | REQ-DATA-003 |
| OQ-DATA-002 | What is the intended data retention period — 1 year of history, 5 years, all available? | Storage sizing, backtest minimum lookback |
| OQ-DATA-003 | Should the refresh script be runnable on a schedule (e.g. via cron or Windows Task Scheduler), or is manual invocation sufficient for Phase 1? | REQ-DATA-004 |
| OQ-BT-001 | Should the backtest execute at next-bar close or next-bar open? | REQ-BT-002 |
| OQ-BT-002 | Should the backtest support multiple simultaneous positions (e.g. SPY and QQQ both long at the same time), or is it single-instrument only? | BacktestConfig scope, portfolio-level metrics |
| OQ-MTF-001 | How should the annualisation constant be determined for non-daily timeframes? | REQ-MTF-002 |
| OQ-WATCH-001 | Should the watchlist support instrument groups or tags (e.g. "US equities", "sector ETFs") for bulk operations? | REQ-WATCH-001, signal runner design |
| OQ-DEP-001 | Should `backtrader` be kept, adopted as the engine, or removed? | GAP-007 |

---

## 13. Dependency Map

```
REQ-DATA-007 (instruments.yaml)
    --> REQ-DATA-001 (raw persistence)
    --> REQ-DATA-004 (scheduled refresh)
    --> REQ-WATCH-001 (watchlist)

REQ-DATA-001 + REQ-DATA-002 + REQ-DATA-005 (ingest + schema + validation)
    --> REQ-SIG-001 (strategy interface)
    --> REQ-BT-001 (backtest config)
    --> REQ-CHART-001 (charting)

REQ-SIG-001 + REQ-SIG-003 (strategy interface + SMA cross)
    --> REQ-BT-001 (backtest config)
    --> REQ-WATCH-003 (portfolio signal view)

REQ-BT-001 + REQ-BT-002 + REQ-BT-003 (config + no-lookahead + cost model)
    --> REQ-BT-005 (metrics)
    --> REQ-BT-006 (persistence)
    --> REQ-BT-007 (date range)

REQ-SIG-005 (indicators)
    --> REQ-CHART-001 (overlays)

REQ-DATA-006 (multi-timeframe)
    --> REQ-MTF-001 (independent storage)
    --> REQ-MTF-002 (strategy on weekly bars)
```

---

*End of Phase 1 Requirements — v1.0 Draft*
