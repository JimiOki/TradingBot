# Trading Lab — Architecture and Build Plan

**Status:** Active
**Date:** 2026-04-26
**Author:** Solution Architect
**Supersedes:** previous build-plan.md (2026-04-03)
**Informed by:** `docs/requirements.md` (including Section 11 additions, 2026-04-25), codebase audit (2026-04-26)

---

## Table of Contents

1. [Current State Assessment](#1-current-state-assessment)
2. [Target Architecture](#2-target-architecture)
3. [Phase 1 — Remaining Work](#3-phase-1--remaining-work)
4. [Phase 2 — IG Demo Account](#4-phase-2--ig-demo-account)
5. [Phase 3 — IG Live Account](#5-phase-3--ig-live-account)
6. [Interface Definitions](#6-interface-definitions)
7. [Configuration Design](#7-configuration-design)
8. [Testing Strategy](#8-testing-strategy)

---

## 1. Current State Assessment

### What Is Built and Working

The core research pipeline is functionally complete. The following modules exist and are implemented:

**Data layer**
- `data/yfinance_ingest.py` — downloads raw and curated Parquet files; atomic write; idempotent
- `data/transforms.py` — normalises yfinance output to the curated schema including `adjusted` column
- `data/models.py` — `MarketDataRequest` with interval validation

**Features layer**
- `features/indicators.py` — `sma`, `rsi`, `atr`, `macd`, `rolling_atr_average`, `sma_gap_pct`

**Strategy layer**
- `strategies/base.py` — `Strategy` ABC with `_validate_output` enforcing signal contract
- `strategies/sma_cross.py` — full implementation: SMA crossover, RSI filter, ATR stop/TP, confidence score, conflict flag, volatility flag
- `strategies/quality.py` — pure functions: `confidence_score`, `signal_strength_pct`, `is_conflicting`, `is_high_volatility`, `compute_stop_loss`, `compute_take_profit`
- `strategies/loader.py` — loads a strategy from a YAML config file

**Backtesting layer**
- `backtesting/engine.py` — long/flat/short backtest engine with no-lookahead enforcement and cost model
- `backtesting/metrics.py` — performance metrics (total return, CAGR, Sharpe, drawdown, win rate, etc.)
- `backtesting/models.py` — `BacktestConfig`, `BacktestResult` dataclasses
- `backtesting/reporter.py` — saves JSON summary and trades Parquet with atomic write
- `backtesting/validation.py` — IS/OOS split, threshold validation, degradation computation

**Scripts**
- `scripts/ingest_market_data.py` — refreshes all instruments from YAML; per-instrument error handling; `--symbol` flag
- `scripts/run_signals.py` — generates portfolio snapshot to `data/signals/portfolio_snapshot.parquet`; atomic write; audit logging

**Application layer**
- `app/pages/dashboard.py` — signal table with quality scores, SL/TP, LLM explanation display (cache-read only, fallback if absent), stale/conflict/volatility badges
- `app/pages/charts.py` — interactive Plotly candlestick with SMA/RSI/MACD overlays and signal markers
- `app/pages/backtests.py` — backtest form, results display
- `app/pages/settings.py` — instrument and strategy config viewer/editor

**Support**
- `audit.py` — JSON-lines audit log to `logs/audit.log`
- `paths.py` — central path definitions
- `exceptions.py` — `ConfigValidationError`, `DataQualityError`, `SignalValidationError`, `BacktestError`, `DataSplitError`, `ValidationOrderError`, `ParameterDriftError`

**Tests — complete**
- `tests/test_audit.py` — 7 tests
- `tests/test_dashboard_logic.py` — pure function tests for signal label, staleness, portfolio summary
- `tests/test_charts_logic.py` — lookback filter, chart builder
- `tests/test_loader.py` — strategy YAML loading, validation

### What Is Missing

The following items are required before Phase 1 can be closed. They are listed in build order.

**Infrastructure gaps**
- `src/trading_lab/config/loader.py` — instrument YAML validation (required by REQ-DATA-007, REQ-WATCH-001)
- `src/trading_lab/logging_config.py` — centralised logging setup; scripts currently use inline `basicConfig`

**LLM layer — entirely absent**
- `src/trading_lab/llm/` directory does not exist. The dashboard is wired to read from `data/signals/explanations/` but nothing generates those files.
- Required: `base.py`, `claude_client.py`, `stub_client.py`, `explainer.py`
- Extends to: news headline ingestion (REQ-LLM-008), two-part prompt (REQ-LLM-009), structured `SignalContext` (REQ-LLM-002)
- Extends further to: `MarketContext` aggregator and LLM decision output (Section 11, see Step 4 below)

**Stubbed test files — 6 files are 1-line stubs**
- `tests/test_engine.py`
- `tests/test_indicators.py`
- `tests/test_metrics.py`
- `tests/test_strategy.py`
- `tests/test_transforms.py`
- `tests/test_validation.py`

**Dashboard features not yet built**
- REQ-RISK-003 — Correlation warning (two co-directional instruments with r > 0.7)
- REQ-RISK-004 — Position sizing calculator display in signal detail panel
- REQ-CTX-001 — Economic calendar integration (high-impact event warnings)
- REQ-CTX-002 — Market session awareness (OPEN/CLOSED badge per instrument)
- REQ-OPS-005 — Backtest comparison across multiple instruments
- Strategy validation panel on Backtests page (IS/OOS result display, REQ-VAL-004/005)

---

## 2. Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EXTERNAL SOURCES                         │
│  yfinance  │  IG REST/Streaming API  │  News/Calendar (free)   │
└──────┬──────┴────────────┬───────────┴──────────┬──────────────┘
       │                   │                       │
       ▼                   ▼                       ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐
│  DATA LAYER  │   │  EXECUTION   │   │   MARKET CONTEXT LAYER   │
│              │   │  LAYER       │   │                          │
│ yfinance_    │   │ ig.py        │   │ market_context.py        │
│ ingest.py    │   │ broker_      │   │ calendar_fetcher.py      │
│ transforms.py│   │ base.py      │   │ news_fetcher.py          │
│ models.py    │   │ ig_streaming │   │ session_checker.py       │
│              │   │ .py (P2)     │   │ (ig_sentiment.py P2)     │
│ data/raw/    │   │ data/live/   │   │ data/calendar/           │
│ data/curated/│   │ (P2)         │   │ data/news/               │
└──────┬───────┘   └──────────────┘   └──────────┬───────────────┘
       │                  ▲                        │
       ▼                  │ (order)                ▼
┌──────────────┐          │           ┌──────────────────────────┐
│ FEATURES     │          │           │   LLM LAYER              │
│ LAYER        │          │           │                          │
│              │          │           │ base.py (LLMClient ABC)  │
│ indicators.py│          │           │ claude_client.py         │
│              │          │           │ stub_client.py           │
└──────┬───────┘          │           │ explainer.py             │
       │                  │           │ (llm_decision.py P1.4)   │
       ▼                  │           │                          │
┌──────────────┐   ┌──────────────┐   │ data/signals/            │
│ STRATEGY     │   │ SIGNAL       │   │   explanations/          │
│ LAYER        │──►│ APPROVAL     │   │   decisions/             │
│              │   │ LAYER (P2)   │   └──────────┬───────────────┘
│ base.py      │   │              │              │
│ sma_cross.py │   │ signal_state │              │
│ quality.py   │   │ .py          │              │
│ loader.py    │   │ position_    │              │
│              │   │ sizer.py     │              │
└──────┬───────┘   └──────────────┘              │
       │                                          │
       ▼                                          │
┌──────────────┐                                  │
│ BACKTESTING  │◄─────────────────────────────────┘
│ LAYER        │
│              │
│ engine.py    │
│ metrics.py   │
│ models.py    │
│ reporter.py  │
│ validation.py│
│              │
│ data/        │
│  backtests/  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────┐
│   APPLICATION LAYER      │
│                          │
│ app/main.py (Streamlit)  │
│ app/pages/dashboard.py   │
│ app/pages/charts.py      │
│ app/pages/backtests.py   │
│ app/pages/settings.py    │
│ app/pages/journal.py (P2)│
└──────────────────────────┘
```

---

## 3. Phase 1 — Remaining Work

Phase 1 closes when: all steps complete, all tests pass (80% line coverage on `src/` excluding `execution/ig.py`), and the Streamlit dashboard renders live signal data for all five commodity instruments with LLM explanations, market context, and strategy validation.

---

### Step 1 — Infrastructure Gaps (1 day)

**1.1 — Config loader**
Create `src/trading_lab/config/loader.py`. Implement `load_instruments(config_path: Path) -> list[dict]`. Validates each entry: all required fields present (`symbol`, `name`, `asset_class`, `timeframe`, `source`, `session_timezone`, `adjusted_prices`), `asset_class` in `{commodity, equity, index, fx}`, `timeframe` in `{1d, 1wk}`, `session_timezone` is valid IANA identifier (use `zoneinfo.available_timezones()`). Raises `ConfigValidationError` identifying the instrument and field on any failure. Tests: `tests/test_config_loader.py` (happy path, missing field, invalid asset_class, invalid timezone).

**1.2 — Logging config module**
Create `src/trading_lab/logging_config.py`. Implement `setup_logging(level=logging.INFO)` that configures a root logger with a `RotatingFileHandler` to `logs/trading_lab.log` (max 5MB, 3 backups) and a `StreamHandler` to stdout. Format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`. Update `scripts/ingest_market_data.py` and `scripts/run_signals.py` to call `setup_logging()` instead of `basicConfig`.

---

### Step 2 — Fill Stubbed Tests (1-2 days)

Fill all six stub test files. Each file should be self-contained with synthetic fixtures defined locally or in `tests/conftest.py`. No live network calls. No disk I/O except via `tmp_path`.

**`tests/test_transforms.py`** — REQ-DATA-002, REQ-DATA-003, REQ-DATA-005
```
- test_normalize_produces_required_columns
- test_timestamp_is_utc_aware
- test_adjusted_column_set_from_request
- test_null_close_rows_excluded
- test_negative_close_rows_excluded
- test_null_close_above_threshold_raises_data_quality_error
```

**`tests/test_indicators.py`** — REQ-SIG-006
```
- test_sma_warmup_produces_correct_null_count
- test_sma_values_are_correct_on_known_series
- test_rsi_values_in_valid_range
- test_rsi_short_series_raises_value_error
- test_macd_output_has_required_columns
- test_atr_positive_for_valid_ohlc
```

**`tests/test_strategy.py`** — REQ-SIG-001 to REQ-SIG-005
```
- test_missing_signal_column_raises_signal_validation_error
- test_signal_values_outside_set_raises
- test_crossover_detected_on_known_synthetic_bars
- test_sell_signal_emitted_as_negative_one
- test_rsi_filter_suppresses_overbought_buy
- test_rsi_filter_suppresses_oversold_sell
- test_rsi_filter_disabled_allows_overbought_buy
- test_fast_window_gte_slow_raises
- test_position_change_column_present
- test_stop_loss_below_entry_for_long
- test_take_profit_above_entry_for_long
- test_stop_loss_above_entry_for_short
```

**`tests/test_engine.py`** — REQ-BT-002 to REQ-BT-008
```
- test_no_lookahead_signal_bar_5_position_bar_6
- test_short_position_profits_on_falling_market
- test_short_position_loses_on_rising_market
- test_zero_cost_gross_return_equals_market_return
- test_higher_turnover_incurs_higher_cost
- test_insufficient_bars_raises_backtest_error
```

**`tests/test_metrics.py`** — REQ-BT-005
```
- test_sharpe_against_hand_calculated_reference
- test_max_drawdown_against_hand_calculated_reference
- test_max_drawdown_duration_unrecovered
- test_win_rate_fewer_than_two_trades_returns_none
- test_profit_factor_no_losing_trades_returns_none
- test_daily_annualisation_constant_252
- test_weekly_annualisation_constant_52
```

**`tests/test_validation.py`** — REQ-VAL-001 to REQ-VAL-005
```
- test_split_200_bars_oos_030_produces_140_60
- test_no_bar_in_both_periods
- test_oos_ratio_below_010_raises
- test_oos_period_under_30_bars_raises_data_split_error
- test_validate_oos_approved_when_both_thresholds_met
- test_validate_oos_rejected_sharpe_too_low
- test_validate_oos_rejected_drawdown_too_high
- test_validate_oos_rejected_both_failures_listed
- test_degradation_above_50pct_triggers_warning
- test_degradation_undefined_when_is_sharpe_zero
```

---

### Step 3 — LLM Layer (2-3 days)

The LLM layer produces plain-English explanations and (per Section 11) a structured go/no-go decision judgment. Both are cached to disk and read by the dashboard. The layer never runs synchronously on page load.

**3.1 — Exceptions**
Add `LLMError`, `LLMTimeoutError`, `ConfigurationError` to `src/trading_lab/exceptions.py`.

**3.2 — LLM module skeleton**
Create `src/trading_lab/llm/` with `__init__.py`. Files:

`base.py`
```python
class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send a prompt; return completion text."""
```

`stub_client.py`
```python
STUB_RESPONSE = "[Stub explanation — LLM not configured]"

class StubLLMClient(LLMClient):
    def complete(self, prompt: str) -> str:
        return STUB_RESPONSE
```

`claude_client.py`
- Reads `ANTHROPIC_API_KEY` from environment. Raises `ConfigurationError` if absent.
- Default model: `claude-sonnet-4-6`. Configurable via constructor.
- Raises `LLMTimeoutError` on timeout (default 30s, configurable).
- Raises `LLMError` on any API error, wrapping the original exception message.
- Logs every call at DEBUG with latency; logs every error at WARNING.

**3.3 — SignalContext dataclass**
Create `src/trading_lab/llm/context.py`. Implement `SignalContext` dataclass (REQ-LLM-002):
```python
@dataclass(frozen=True)
class SignalContext:
    symbol: str
    instrument_name: str
    signal_date: date
    signal: int                  # 1 or -1
    signal_direction: str        # "LONG" or "SHORT"
    close: float
    fast_sma: float
    slow_sma: float
    rsi: float
    recent_trend_summary: str    # e.g. "price up 4.2% over 5 bars"
    stop_loss_level: float
    take_profit_level: float
    risk_reward_ratio: float
    confidence_score: int
    conflicting_indicators: bool
    high_volatility: bool
    news_headlines: list[dict]   # each: {title, source, timestamp}; empty list if none
```

Implement `build_signal_context(signal_row: dict, instrument: dict, news: list[dict]) -> SignalContext`.

**3.4 — Prompt templates**
Create `src/trading_lab/llm/prompts.py`. Store prompt templates as module-level string constants (not embedded in classes). Two templates:

`EXPLANATION_PROMPT_WITH_NEWS` — used when `len(signal_context.news_headlines) > 0`. Two-part structure (REQ-LLM-009):
1. Technical basis: why the signal fired based on indicator readings
2. News context: whether recent headlines support, contradict, or are neutral relative to signal direction. When contradictory, the tension must be flagged explicitly.

`EXPLANATION_PROMPT_NO_NEWS` — used when no headlines available. Purely technical explanation.

Both prompts instruct the LLM: 3–5 sentences, plain English, no price predictions, no investment advice, directionally consistent with the signal.

**3.5 — ExplanationService**
Create `src/trading_lab/llm/explainer.py`. Implement:

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

class ExplanationService:
    def __init__(self, client: LLMClient, cache_dir: Path): ...
    def get_or_generate(self, context: SignalContext) -> SignalExplanation: ...
```

Cache path: `data/signals/explanations/<symbol>_<date>.json`
Cache hit: return with `cached=True`, no API call.
Cache miss: call LLM, validate output (non-empty, ≤ 1000 chars), write JSON, return with `cached=False`.
On any API failure: catch exception, log WARNING, return `SignalExplanation` with `explanation="Explanation unavailable."` (the constant from REQ-LLM-004).
Post-generation validation failure: treat as API failure (log, return fallback).
Log audit event `llm_call_made` or `llm_call_cached` or `llm_call_failed` via `audit.log_event`.

**3.6 — LLM Decision Layer (Section 11, REQ-LLMDEC-001 to REQ-LLMDEC-004)**
Create `src/trading_lab/llm/decision.py`. This extends the LLM role from explanation to structured judgment.

```python
@dataclass(frozen=True)
class LLMDecision:
    symbol: str
    signal_date: date
    signal: int                  # the technical signal direction
    llm_recommendation: str      # "GO", "NO_GO", or "UNCERTAIN"
    rationale: str               # 1-3 sentences
    conflicts_with_technical: bool
    generated_at: datetime
    model: str
    cached: bool
```

`DecisionService` follows the same cache-first pattern as `ExplanationService`. Cache path: `data/signals/decisions/<symbol>_<date>.json`.

The prompt for decision output is separate from the explanation prompt. It provides the full `SignalContext` (including news, market context when available) and asks the LLM to return a structured JSON response with `recommendation` ("GO"/"NO_GO"/"UNCERTAIN"), `rationale`, and `conflicts_with_technical` (bool). The response is parsed and validated; any parse failure falls back to `UNCERTAIN` with the explanation `"Decision unavailable."`.

"No trade" is a first-class outcome (REQ-GUARD-001): the prompt explicitly states that NO_GO or UNCERTAIN are acceptable and preferred over a forced GO when the evidence is mixed.

**3.7 — News ingestion (REQ-LLM-008)**
Add `fetch_news(symbol: str, max_headlines: int = 5) -> list[dict]` to `src/trading_lab/data/yfinance_ingest.py`. Uses `yfinance.Ticker(symbol).news`. Returns a list of dicts with `{title, source, timestamp}`. If the API returns nothing or errors, returns an empty list (logged at DEBUG).

Update `scripts/run_signals.py` to call `fetch_news` for each instrument after signal generation and store headlines in the portfolio snapshot (added as a new JSON column `news_headlines`). Headlines are then available to `ExplanationService` and `DecisionService` without a second API call.

**3.8 — Config-driven provider selection**
`config/environments/local.yaml` `llm.provider` selects the client class (`claude` or `stub`). Default: `claude`. If `ANTHROPIC_API_KEY` is absent and provider is `claude`, fall back to `stub` and log a WARNING at startup.

**3.9 — Tests**
```
tests/test_llm.py
  - test_cache_hit_does_not_call_llm
  - test_cache_miss_calls_llm_and_writes_cache
  - test_stub_client_returns_fixed_string
  - test_missing_api_key_raises_configuration_error
  - test_api_failure_returns_fallback_explanation
  - test_decision_no_go_is_first_class_outcome (UNCERTAIN returned when evidence mixed)
  - test_decision_parse_failure_falls_back_to_uncertain
  - test_fetch_news_empty_list_on_error
  - test_fetch_news_capped_at_max_headlines
  - test_signal_context_all_fields_populated
```

---

### Step 4 — Market Context Engine (1-2 days)

Covers Section 11 of requirements, Phase 1 scope only (IG sentiment deferred to Phase 2).

**4.1 — Economic calendar (REQ-CTX-001)**
Create `src/trading_lab/context/calendar_fetcher.py`. Implement `fetch_high_impact_events(lookforward_days: int = 5) -> list[dict]`. Fetches from Investing.com RSS or equivalent free source. Each event: `{name, date, time_utc, currency, impact}`. Filter to `impact="high"`. Map currency to watchlist instruments (USD events apply to all five Phase 1 commodities). Cache to `data/calendar/events_<YYYYMMDD>.json`. If fetch fails: log WARNING, return empty list — never propagate to dashboard.

**4.2 — Session awareness (REQ-CTX-002)**
Create `src/trading_lab/context/session_checker.py`. Implement `is_session_open(instrument: dict) -> bool`. Reads `session_open`, `session_close`, `session_timezone` from instrument dict. Uses current system time. Weekends always CLOSED. No holiday calendar in Phase 1. Tests: in-session, out-of-session, Saturday.

Note: `instruments.yaml` must be updated to add `session_open` and `session_close` fields for each instrument (see Section 7).

**4.3 — MarketContext aggregator (REQ-CONTEXT-001, REQ-CONTEXT-002)**
Create `src/trading_lab/context/market_context.py`. Implement:

```python
@dataclass
class MarketContext:
    symbol: str
    as_of: datetime
    session_open: bool
    upcoming_events: list[dict]      # from calendar_fetcher
    news_headlines: list[dict]       # from run_signals snapshot
    ig_sentiment: None               # Phase 2; always None in Phase 1
```

Implement `build_market_context(symbol, instrument_config, events, news) -> MarketContext`.

Persist to `data/signals/market_context_<symbol>_<YYYYMMDD>.json` during the signals run. Dashboard and LLM layer read from this file — no recomputation on page load.

**4.4 — StructuredModelContext (REQ-MCTX-001, REQ-MCTX-002)**
Create `src/trading_lab/llm/model_context.py`. Implement `build_model_context(signal_context: SignalContext, market_context: MarketContext) -> dict` that assembles the full structured payload passed to both `ExplanationService` and `DecisionService`. Validates all required fields are non-null before handing to the LLM (REQ-MCTX-002 validation gate): if any required field is null, the gate logs a WARNING and omits the null fields from the payload with an explicit note in the prompt.

**4.5 — Price confirmation guardrail (REQ-GUARD-002)**
In `scripts/run_signals.py`, after generating a signal, verify that the current close price is on the expected side of the slow SMA for the signal direction:
- LONG signal: close must be above slow_sma (or within 0.5% of it)
- SHORT signal: close must be below slow_sma (or within 0.5% of it)
If the check fails, log a WARNING and set `confidence_score` to `max(0, confidence_score - 25)`. Do not suppress the signal; this is a display-only penalty. The 0.5% tolerance is a named constant.

**4.6 — Update run_signals.py**
Update `scripts/run_signals.py` to:
- Fetch news per instrument after signal generation (Step 3.7)
- Build `MarketContext` per instrument (Step 4.3)
- Apply price confirmation guardrail (Step 4.5)
- Pass full `ModelContext` to `ExplanationService` and `DecisionService`
- Persist explanations and decisions to cache during the signals run (not on dashboard load)

---

### Step 5 — Dashboard Remaining Features (2-3 days)

**5.1 — Market context display**
Add to each signal row on the Dashboard page:
- Session badge: `OPEN` (green) or `CLOSED` (grey) — REQ-CTX-002
- Upcoming event warnings: amber badge `UPCOMING EVENT: <name> <date>` for any high-impact event within 5 trading days — REQ-CTX-001
- LLM decision badge: `GO` (green), `NO_GO` (red), `UNCERTAIN` (amber) from `DecisionService` cache
- LLM decision rationale in the signal expander (alongside explanation)

**5.2 — Position sizing calculator (REQ-RISK-004)**
Add to signal detail expander for LONG/SHORT signals:
- Inputs: `capital` (from `local.yaml`), `risk_per_trade_pct`, `stop_distance`
- Output: `position_size_units` (rounded down), `GBP_risk`
- Show all inputs transparently in the expander
- Display `N/A - stop distance unavailable` if `stop_distance` is zero/null

**5.3 — Correlation warning (REQ-RISK-003)**
Add `compute_correlation_warnings(snapshot_df, curated_dir) -> list[dict]` to dashboard logic. Computes 60-bar rolling Pearson correlation between each pair of instruments from curated close price series. Returns warnings for pairs where `r > 0.7` AND both show the same direction signal. Display above signal table as a warning card. Threshold `0.7` is a named constant. Tests in `tests/test_dashboard_logic.py`.

**5.4 — Strategy validation panel on Backtests page**
Add a "Strategy Validation" tab to the Backtests page:
- Run In-Sample and Out-of-Sample buttons (in that order; OOS blocked until IS artefact exists)
- Side-by-side Sharpe comparison, degradation percentage, overfitting warning if degradation > 50%
- Approval status badge: `APPROVED FOR PAPER TRADING` or `NOT APPROVED` with failure reasons
- Chart with shaded IS/OOS regions
- Reads artefacts from `data/backtests/` to load previous validation runs

**5.5 — Backtest comparison across instruments (REQ-OPS-005)**
Add "Compare Instruments" mode to Backtests page. Multi-select instruments. Same strategy config applied to all. Results table: instrument, total return, CAGR, Sharpe, drawdown, win rate, trades. Best performer highlighted. Each row expandable to show equity curve.

---

### Step 6 — Phase 1 Close (1 day)

- Run full test suite; all tests pass; line coverage ≥ 80% on `src/` excluding `execution/ig.py`
- Run `scripts/ingest_market_data.py` against all five instruments; verify curated files on disk
- Run `scripts/run_signals.py`; verify portfolio snapshot, explanations, and decisions written to disk
- Open dashboard; verify signal table renders with real data, LLM explanations, LLM decisions, session badges, market context
- Run one in-sample backtest and one out-of-sample backtest from the UI; verify artefacts written and validation panel renders correctly
- Confirm dark mode active (`streamlit/config.toml`)
- Confirm `logs/audit.log` contains entries for signal generation and LLM calls
- Update `instruments.yaml` with `session_open`, `session_close` for all five instruments

---

## 4. Phase 2 — IG Demo Account

Phase 2 starts only after all Phase 1 acceptance criteria pass and at least one strategy has passed REQ-VAL-004 (out-of-sample approval thresholds). No Phase 2 code merges until Phase 1 is stable.

### Prerequisites
- All Phase 1 tests passing
- IG demo account credentials in `.env`
- IG epic codes for all five instruments added to `instruments.yaml`
- `IG_ENVIRONMENT=demo` in `.env`

---

### Step 1 — IG API Authentication (2 days)

**1.1 — Environment config**
Add to `.env.example`: `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, `IG_ACCOUNT_ID`, `IG_ENVIRONMENT`. Add to `config/environments/local.yaml`: `ig.retry_attempts: 3`, `ig.retry_backoff_base: 2`, `ig.timeout_seconds: 30`.

**1.2 — IgBrokerAdapter implementation**
Implement `execution/ig.py` `IgBrokerAdapter`: `connect()`, `place_order()`, `get_positions()`, `close_position()`. Session token management and refresh. Add `IGAPIError`, `IGConnectionError`, `AuthenticationError`, `EnvironmentMismatchError` to `exceptions.py`. All API calls log request/response to `logs/orders.log` (credentials redacted) via a dedicated logger.

**1.3 — Environment isolation guard**
`IgBrokerAdapter` reads `IG_ENVIRONMENT` at init. `place_order` raises `EnvironmentMismatchError` if adapter environment does not match endpoint. Cannot be overridden at call time.

**1.4 — IG client sentiment (REQ-SENT-001 to REQ-SENT-003)**
Add `get_client_sentiment(epic: str) -> IGSentiment | None` to `IgBrokerAdapter`. Returns `IGSentiment(long_pct, short_pct, fetch_timestamp)` or `None` on error. Validates `long_pct + short_pct ≈ 100`. Persist to `data/signals/market_context_<symbol>_<YYYYMMDD>.json` extending the existing Phase 1 `MarketContext` schema. Update `MarketContext.ig_sentiment` field (was always `None` in Phase 1).

Update `ExplanationService` and `DecisionService` prompts to include IG client sentiment context with the required labelling: `"IG retail client positioning (note: this reflects IG retail clients only, not the full market)"`.

**1.5 — Tests**
Mock HTTP with `responses` library. Test auth success/failure, 429 rate limit retry, environment mismatch guard, sentiment validation (`long + short ≠ 100` raises `DataQualityError`).

---

### Step 2 — Signal State Management (2 days)

**2.1 — Signal lifecycle**
Create `src/trading_lab/signals/state.py`. `SignalStatus` enum: `pending`, `approved`, `rejected`, `expired`. `SignalRecord` dataclass per interface in Section 6. `SignalStore` backed by `data/journal/signals.parquet`: `add_signal()`, `get_pending()`, `update_status()`, `expire_stale()`.

**2.2 — Supersession**
New signal for an instrument with an existing `pending` signal: transition existing to `expired` before adding new.

**2.3 — Run_signals integration**
Update `scripts/run_signals.py` to call `SignalStore.add_signal()` for any new signal where `position_change != 0`.

**2.4 — Push notifications (REQ-OPS-003)**
Create `src/trading_lab/notifications.py`. `notify_signal(signal_context: SignalContext)`. Reads `PUSH_NOTIFICATION_URL` from env (ntfy.sh or Pushover). Enabled/disabled via `config/environments/local.yaml` `notifications.enabled`. On failure: log WARNING, do not propagate. Test: when `enabled=false`, no HTTP call is made.

---

### Step 3 — Position Sizer (1 day)

Create `src/trading_lab/execution/position_sizer.py`. `calculate_position_size(account_balance, risk_pct, entry_price, stop_loss_price) -> int`. Rounds down. Falls back to `entry_price * (1 - default_stop_pct)` if strategy emits no stop level. Tests: hand-calculated reference values.

---

### Step 4 — Signal Approval and Order Placement (3 days)

**4.1 — Dashboard approval UI**
Approve/Reject buttons per pending signal row. Approve opens confirmation modal: instrument, direction, price, suggested size, stop, risk/reward. User may override size. Confirm triggers `IgBrokerAdapter.place_order()`. No double-submit (`st.session_state` guard).

**4.2 — Order submission**
On confirm: `IgBrokerAdapter.place_order(OrderRequest(...))`. On success: update signal to `approved`, store `deal_id`, write entry to `data/journal/trades.parquet`. On failure: signal to `rejected`, surface error in dashboard.

**4.3 — Environment banner**
Persistent sidebar: `DEMO ACCOUNT` (blue) or `LIVE ACCOUNT — REAL MONEY` (red). All pages.

---

### Step 5 — IG Streaming and Position Monitoring (2-3 days)

**5.1 — Streaming adapter**
Create `execution/ig_streaming.py`. Subscribe to OHLC candles for watchlist. Write to `data/live/<symbol>_1d_ig_streaming.parquet`. Reconnection: 5 attempts with exponential backoff. After 5 failures: `CONNECTION LOST` alert in dashboard.

**5.2 — Positions panel**
Calls `IgBrokerAdapter.get_positions()` on each manual refresh. Shows: instrument, direction, size, open price, current price, unrealised P&L, stop level. Cache last successful response; staleness indicator on stale data.

**5.3 — Exit detection**
On each positions refresh, compare against prior cache. Disappeared positions are closed. Retrieve deal details and write exit row to `data/journal/trades.parquet`.

---

### Step 6 — Exit Monitor (2 days)

Implements REQ-EXIT-002 to REQ-EXIT-006.

Create `src/trading_lab/execution/exit_monitor.py`. For each open position, evaluate five exit conditions on each refresh: stop hit, target hit, opposite signal, signal age > `max_signal_age_days`, RSI extreme. Generate `CLOSE` recommendation on any trigger. Persist to `data/journal/signals.parquet`. Deduplicate: one active CLOSE recommendation per open position. Dashboard: CLOSE recommendations displayed above signal table as warning cards.

---

### Step 7 — Trade Journal and Risk Display (1-2 days)

**7.1 — Journal page**
Create `app/pages/journal.py`. Two tabs: Trades and Signals. Trades tab: filterable table, running P&L curve. Signals tab: filterable table, approve/reject rate summary.

**7.2 — Risk display (REQ-RISK-001, REQ-RISK-002)**
Now that position state exists, implement the deferred Phase 1 risk display requirements. Daily loss limit warning banner. Maximum positions warning banner. Both read from `data/journal/trades.parquet`.

---

### Step 8 — Phase 2 Close

- 30 days of paper trading on demo account with no critical defects
- All Phase 2 tests pass
- Order audit log reviewed for completeness
- Kill switch tested on demo account (close all demo positions in one action — see Phase 3 Step 2 but test on demo first)
- `docs/risk-review.md` created and signed off

---

## 5. Phase 3 — IG Live Account

Phase 3 starts only after `docs/risk-review.md` is completed and signed off.

### Step 1 — Pre-Execution Risk Controls (2 days)

Create `src/trading_lab/execution/risk_checks.py`. `check_pre_submission(order, account_state, config) -> RiskCheckResult`. Checks in order: daily loss limit, total exposure cap, per-instrument duplicate position, stop loss presence. Each failed check returns a descriptive reason. `IgBrokerAdapter.place_order()` calls this before the API call; a failed check raises `RiskCheckError`.

Risk config in `config/environments/local.yaml`:
```yaml
risk:
  daily_loss_limit_pct: 3.0
  max_exposure_pct: 25.0
  max_open_positions: 5
  risk_per_trade_pct: 1.0
  default_stop_pct: 0.02
```
`daily_loss_limit_pct > 50` rejected as unsafe at startup.

---

### Step 2 — Kill Switch (1 day)

Create `src/trading_lab/execution/kill_switch.py`. `activate()` iterates all open positions, calls `close_position()` for each, logs each closure to `logs/orders.log`. Sets `halted` flag in `st.session_state`; prevents `place_order()`. Cleared only on application restart. Dashboard: kill switch button visible on all pages when `IG_ENVIRONMENT=live`. Confirmation modal. All Approve buttons disabled while `halted=True`.

---

### Step 3 — Credential Switch to Live (0.5 days)

Update `.env` to `IG_ENVIRONMENT=live` with live credentials. Verify startup logs a WARNING at the first line. Verify environment banner renders in red.

---

### Step 4 — Forex and Indices Expansion (1 day)

Add index instruments (Phase 2) and forex instruments (Phase 3) to `instruments.yaml` with `asset_class: index` or `asset_class: fx` and their IG epics. Signal table groups instruments by `asset_class`. No code changes required if the data and strategy layers are built correctly.

---

### Step 5 — Actual vs Backtest Performance (1-2 days)

Create `src/trading_lab/reporting/performance_comparison.py`. For instruments with ≥ 5 completed live trades: compute actual win rate, average return, Sharpe vs corresponding backtest result. Display in a new Journal page tab. Highlight divergences > 20%.

---

### Step 6 — Phase 3 Close

- Pre-live checklist in `docs/risk-review.md` completed
- Kill switch exercised on demo account
- First live session: 1 instrument only, minimum position size
- Incremental expansion to full watchlist after 2 weeks of stable operation

---

## 6. Interface Definitions

### Curated Bar Schema

| Column | Type | Constraints |
|---|---|---|
| timestamp | datetime64[ns, UTC] | Non-null, UTC-aware, sorted ascending |
| open | float64 | > 0 |
| high | float64 | >= open |
| low | float64 | <= open |
| close | float64 | > 0, non-null |
| volume | float64 | >= 0 |
| symbol | str | Non-null |
| source | str | Non-null, e.g. "yfinance" |
| adjusted | bool | Non-null |

### Signal Schema (output of `Strategy.generate_signals`)

| Column | Type | Notes |
|---|---|---|
| timestamp | DatetimeIndex | UTC-aware |
| open, high, low, close | float64 | From input bars |
| signal | int8 | {-1, 0, 1} |
| position_change | int8 | 1 on entry, -1 on exit, 0 otherwise |
| fast_sma, slow_sma | float64 | NaN during warmup |
| rsi | float64 | NaN during warmup |
| atr_value, rolling_avg_atr | float64 | NaN during warmup |
| signal_strength_pct | float64 | SMA gap as % |
| confidence_score | int | 0–100; 0 for flat signals |
| conflicting_indicators | bool | |
| high_volatility | bool | |
| stop_loss_level | float64 | NaN for flat |
| take_profit_level | float64 | NaN for flat |
| stop_distance | float64 | NaN for flat |

### SignalContext (LLM input)

```python
@dataclass(frozen=True)
class SignalContext:
    symbol: str
    instrument_name: str
    signal_date: date
    signal: int
    signal_direction: str        # "LONG" or "SHORT"
    close: float
    fast_sma: float
    slow_sma: float
    rsi: float
    recent_trend_summary: str
    stop_loss_level: float
    take_profit_level: float
    risk_reward_ratio: float
    confidence_score: int
    conflicting_indicators: bool
    high_volatility: bool
    news_headlines: list[dict]   # [{title, source, timestamp}]
```

### MarketContext (Section 11 aggregator)

```python
@dataclass
class MarketContext:
    symbol: str
    as_of: datetime
    session_open: bool
    upcoming_events: list[dict]      # high-impact events within 5 days
    news_headlines: list[dict]       # same as SignalContext.news_headlines
    ig_sentiment: IGSentiment | None # None in Phase 1
```

### LLMDecision (Section 11 output)

```python
@dataclass(frozen=True)
class LLMDecision:
    symbol: str
    signal_date: date
    signal: int
    llm_recommendation: str      # "GO", "NO_GO", "UNCERTAIN"
    rationale: str               # 1-3 sentences
    conflicts_with_technical: bool
    generated_at: datetime
    model: str
    cached: bool
```

### SignalRecord (Phase 2 signal store)

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
    deal_id: str | None
```

### OrderRequest (Phase 2 execution)

```python
@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    ig_epic: str
    side: str                    # "BUY" or "SELL"
    size: float
    stop_loss: float             # required; raises ValidationError if absent
    signal_id: str
```

---

## 7. Configuration Design

### instruments.yaml additions (Phase 1 Step 4)

Each instrument entry must add `session_open` and `session_close` (HH:MM in `session_timezone`):
```yaml
- symbol: "GC=F"
  name: Gold Futures
  asset_class: commodity
  timeframe: 1d
  source: yfinance
  session_timezone: America/New_York
  session_open: "18:00"
  session_close: "17:00"
  adjusted_prices: true
  # ig_epic: CS.D.GOLD.CFD.IP   # required for Phase 2
```

### local.yaml additions

```yaml
llm:
  provider: claude              # or: stub
  model: claude-sonnet-4-6
  max_tokens: 500
  timeout_seconds: 30

notifications:
  enabled: false
  # push_url populated from PUSH_NOTIFICATION_URL env var

account:
  capital: 10000

risk:
  daily_loss_limit_pct: 3.0
  max_exposure_pct: 25.0
  max_open_positions: 5
  risk_per_trade_pct: 1.0
  default_stop_pct: 0.02
  correlation_warning_threshold: 0.7

signal_expiry_hours: 24         # Phase 2

ig:
  retry_attempts: 3
  retry_backoff_base: 2
  timeout_seconds: 30
```

---

## 8. Testing Strategy

### Levels

**Unit tests** (`tests/`) — pure functions, no I/O, no network. Run on every commit. Target: 80% line coverage on `src/trading_lab/` excluding `execution/ig.py`.

**Integration tests** (`tests/integration/`) — file I/O permitted, no network. Tagged `@pytest.mark.integration`. Ingest pipeline end-to-end with fixture Parquet. Signal runner with mock filesystem.

**No live network calls in the test suite.** yfinance calls mocked via `unittest.mock.patch`. IG API calls mocked with `responses`. Anthropic API calls use `StubLLMClient`.

### Test data

Synthetic DataFrames in `tests/conftest.py`: small (50–100 rows), programmatically generated, with precisely known properties (e.g. SMA crossover on bar 35, known RSI value on bar 50).

Fixture file for integration tests: `tests/fixtures/gc_1d_yfinance_sample.parquet` — 100 rows of committed Gold data, does not change.

### Coverage target

Phase 1: 80% on `src/trading_lab/` excluding `execution/ig.py`.
Phase 2: 80% on execution adapters with mocked HTTP.
Do not chase 100%. Focus on: calculation paths (metrics, indicators, engine), validation paths (config loader, schema validator, signal validator), LLM cache logic, signal lifecycle transitions.
