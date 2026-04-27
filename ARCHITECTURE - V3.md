# Trading Lab — Architecture Supplement

**Version:** 3.0
**Date:** 2026-04-26
**Status:** Active supplement to `ARCHITECTURE - V2.md`
**Covers:** Multi-LLM Provider Architecture and Phase 4 Automated Execution Architecture

> V2 remains the primary system architecture reference. This document records two new architectural decisions made on 2026-04-26 in sufficient detail for direct implementation. Do not duplicate V2 content here.

---

## Table of Contents

1. [Multi-LLM Provider Architecture](#1-multi-llm-provider-architecture)
   - 1.1 [Overview and Rationale](#11-overview-and-rationale)
   - 1.2 [Provider Table](#12-provider-table)
   - 1.3 [Component Diagram](#13-component-diagram)
   - 1.4 [File Structure](#14-file-structure)
   - 1.5 [Factory Design](#15-factory-design)
   - 1.6 [Configuration](#16-configuration)
   - 1.7 [Dependencies and Environment Variables](#17-dependencies-and-environment-variables)
   - 1.8 [JSON Output Reliability](#18-json-output-reliability)
   - 1.9 [Migration Notes](#19-migration-notes)
2. [Phase 4 — Automated Execution Architecture](#2-phase-4--automated-execution-architecture)
   - 2.1 [Overview](#21-overview)
   - 2.2 [Pipeline Diagram](#22-pipeline-diagram)
   - 2.3 [LLM Gate Logic](#23-llm-gate-logic)
   - 2.4 [Risk Checks](#24-risk-checks)
   - 2.5 [New Modules](#25-new-modules)
   - 2.6 [Scheduling Design](#26-scheduling-design)
   - 2.7 [Notification Events](#27-notification-events)
   - 2.8 [Audit Trail](#28-audit-trail)
   - 2.9 [Demo Validation Gate](#29-demo-validation-gate)
   - 2.10 [Phase 4 Prerequisites](#210-phase-4-prerequisites)
3. [Impact on Existing Architecture](#3-impact-on-existing-architecture)
   - 3.1 [Unchanged V2 Components](#31-unchanged-v2-components)
   - 3.2 [Extended V2 Components](#32-extended-v2-components)
   - 3.3 [Build Plan Impact](#33-build-plan-impact)
4. [Open Architecture Questions](#4-open-architecture-questions)

---

## 1. Multi-LLM Provider Architecture

### 1.1 Overview and Rationale

The original design used Claude as the sole LLM for the signal advisory gate. This decision replaces that with a configurable, single-provider-per-run system that supports four providers across a cost ladder.

The primary driver is cost reduction during high-volume research and demo phases. Gemini 2.0 Flash is free up to approximately 1,500 requests per day, making it the appropriate default for development and early live running. Paid providers are available as drop-in alternatives via config when their capability or reliability characteristics are warranted.

The design does **not** implement a runtime fallback chain between providers. The provider is selected once at startup. If the selected provider's API call fails at runtime, the system falls back to a `StubLLMClient` result (UNCERTAIN direction, zero confidence) rather than attempting another live provider. This keeps failure modes simple and auditable — a fallback chain would obscure which provider drove a decision in the audit log.

### 1.2 Provider Table

| Provider  | Default Model        | Cost Tier     | API Compatibility        | Primary Use Case              |
|-----------|---------------------|---------------|--------------------------|-------------------------------|
| Gemini    | `gemini-2.0-flash`  | Free (1.5k/d) | Google GenAI SDK         | Default — development & demo  |
| DeepSeek  | `deepseek-chat`     | Low cost      | OpenAI-compatible REST   | Cost-sensitive live running   |
| OpenAI    | `gpt-4o`            | Mid cost      | OpenAI SDK               | Higher reliability requirement|
| Claude    | `claude-sonnet-4-6` | Highest cost  | Anthropic SDK            | Baseline / fallback reference |
| Stub      | n/a                 | Free          | Internal                 | Testing and safe defaults     |

### 1.3 Component Diagram

```
config/local.yaml
  llm.provider: gemini
        |
        v
+---------------------------+
|       factory.py          |
|  create_llm_client(config)|
+---------------------------+
        |
        +---> GeminiClient      (gemini_client.py)   -- google-genai SDK
        |
        +---> DeepSeekClient    (deepseek_client.py) -- openai SDK, custom base_url
        |
        +---> OpenAIClient      (openai_client.py)   -- openai SDK
        |
        +---> ClaudeClient      (claude_client.py)   -- anthropic SDK  [unchanged]
        |
        +---> StubLLMClient     (stub_client.py)     -- internal       [unchanged]
                |
                v
        +---------------------------+
        |       LLMClient ABC       |
        |   complete(prompt) -> str |   (base.py)    [unchanged]
        +---------------------------+
                |
                v
        SignalAdvisor / auto_trader.py
        (calls complete(), then _parse_decision())
```

All five concrete clients expose the same `complete(prompt: str) -> str` interface. The caller has no awareness of which provider is active.

### 1.4 File Structure

Changes are confined to `src/trading_lab/llm/`. No other package directories are modified.

```
src/trading_lab/llm/
    base.py              -- LLMClient ABC              [unchanged]
    claude_client.py     -- Anthropic implementation   [unchanged]
    stub_client.py       -- Test/safe-default stub     [unchanged]
    factory.py           -- NEW: create_llm_client()
    gemini_client.py     -- NEW: Google Gemini
    openai_client.py     -- NEW: OpenAI (gpt-4o)
    deepseek_client.py   -- NEW: DeepSeek via openai compat
```

### 1.5 Factory Design

The factory is the single construction point for all LLM clients. Callers import `create_llm_client` and pass the loaded config dict. No caller constructs a concrete client directly.

```python
# src/trading_lab/llm/factory.py

from trading_lab.llm.base import LLMClient
from trading_lab.llm.claude_client import ClaudeClient
from trading_lab.llm.stub_client import StubLLMClient
from trading_lab.llm.gemini_client import GeminiClient
from trading_lab.llm.openai_client import OpenAIClient
from trading_lab.llm.deepseek_client import DeepSeekClient
from trading_lab.exceptions import ConfigurationError


def create_llm_client(config: dict) -> LLMClient:
    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "gemini")
    model_override = llm_cfg.get("model") or None
    max_tokens = llm_cfg.get("max_tokens", 500)
    timeout = llm_cfg.get("timeout_seconds", 30)

    if provider == "gemini":
        return GeminiClient(
            model=model_override or "gemini-2.0-flash",
            max_tokens=max_tokens,
            timeout=timeout,
        )
    elif provider == "deepseek":
        return DeepSeekClient(
            model=model_override or "deepseek-chat",
            max_tokens=max_tokens,
            timeout=timeout,
        )
    elif provider == "openai":
        return OpenAIClient(
            model=model_override or "gpt-4o",
            max_tokens=max_tokens,
            timeout=timeout,
        )
    elif provider == "claude":
        return ClaudeClient(
            model=model_override or "claude-sonnet-4-6",
            max_tokens=max_tokens,
            timeout=timeout,
        )
    elif provider == "stub":
        return StubLLMClient()
    else:
        raise ConfigurationError(f"Unknown LLM provider: {provider!r}")
```

**DeepSeek implementation note:** `DeepSeekClient` uses the `openai` SDK with `base_url` set to DeepSeek's API endpoint (`https://api.deepseek.com/v1`). It is a thin subclass or wrapper of `OpenAIClient` with a different base URL and API key source. A separate file (`deepseek_client.py`) is used rather than a parameter on `OpenAIClient` to keep the factory branches unambiguous and to isolate the DeepSeek-specific key lookup.

### 1.6 Configuration

Additions to `config/local.yaml`:

```yaml
llm:
  provider: gemini          # gemini | deepseek | openai | claude | stub
  model:                    # optional — overrides the per-provider default
  max_tokens: 500
  timeout_seconds: 30
```

The `model` key accepts an empty value (treated as absent). When absent, the factory applies the default model for the selected provider as listed in Section 1.2. An explicit value overrides the default, enabling pinning to a specific model version without code changes.

### 1.7 Dependencies and Environment Variables

**New Python dependencies (add to `pyproject.toml` or `requirements.txt`):**

| Package       | Purpose                                   |
|---------------|-------------------------------------------|
| `google-genai` | Google Gemini SDK                        |
| `openai`       | OpenAI SDK; also used for DeepSeek compat|

The `anthropic` package (existing) is unchanged.

**Environment variables:**

| Variable           | Provider  | Notes                  |
|--------------------|-----------|------------------------|
| `ANTHROPIC_API_KEY` | Claude   | Existing — unchanged   |
| `GOOGLE_API_KEY`    | Gemini   | New                    |
| `DEEPSEEK_API_KEY`  | DeepSeek | New                    |
| `OPENAI_API_KEY`    | OpenAI   | New                    |

Each client reads only its own key. An absent key for the active provider should raise `ConfigurationError` at startup, not at first API call. Keys for inactive providers are ignored.

Add new keys to `.env.example` with placeholder values. Do not document actual keys anywhere in the repository.

### 1.8 JSON Output Reliability

The DECISION_PROMPT expects a JSON object with `direction`, `confidence_score`, and `recommendation` fields. All four providers can produce this format, but output consistency varies across providers and prompt phrasings.

The existing `_parse_decision` logic must remain in place for all providers without modification:

1. Strip markdown code fences if present.
2. Scan for the first `{` and last `}` to extract the JSON substring.
3. Attempt `json.loads()`.
4. On any parse failure, return UNCERTAIN direction with zero confidence.

No provider-specific post-processing is permitted. If a provider consistently fails to return valid JSON, the remedy is prompt tuning or provider switch — not branching parse logic per provider.

### 1.9 Migration Notes

- `ClaudeClient` and `StubLLMClient` are not modified.
- Existing cached LLM decisions and explanations stored in `data/` are not invalidated — they carry no provider tag, which is acceptable for historical research outputs.
- Any code that currently instantiates `ClaudeClient` directly must be updated to call `create_llm_client(config)` instead. This is the only required change to existing callers.
- The `stub` provider remains the correct setting for CI environments and unit tests where no live API key is available.

---

## 2. Phase 4 — Automated Execution Architecture

### 2.1 Overview

Phases 2 and 3 gate every order on explicit human approval: the operator reviews signals in the dashboard and clicks to approve or reject before any order is submitted. Phase 4 removes this gate and replaces it with a programmatic LLM advisory gate and a pre-submission risk check sequence. The system runs on a schedule and submits orders without operator interaction.

This is a material increase in operational risk. The architecture responds with layered safeguards: a confidence threshold, a risk check sequence, a kill switch, a demo validation gate, and a complete audit trail. None of these safeguards depend on the operator being online.

### 2.2 Pipeline Diagram

```
                        run_auto_trade.py (scheduled)
                                |
                        +-------v--------+
                        |  Data Ingest   |  fetch_ohlcv() for each instrument
                        +-------+--------+
                                |
                        +-------v--------+
                        | Signal Engine  |  compute indicators, emit SignalEvent
                        +-------+--------+
                                |
                        +-------v--------+
                        |   LLM Gate     |  complete(DECISION_PROMPT) -> parse_decision()
                        +-------+--------+
                                |
               +----------------+----------------+
               |  confidence < threshold         |
               |  OR recommendation != "GO"      |
               v                                 v
     [Suppress — log to audit.log]     +--------+--------+
     [Send suppression notification]   |  Risk Checks    |
                                       | (see 2.4)       |
                                       +--------+--------+
                                                |
                               +----------------+----------------+
                               | Any check fails                 |
                               v                                 v
                    [Suppress — log to audit.log]    +----------+---------+
                    [Send suppression notification]  | Position Sizing    |
                                                     +----------+---------+
                                                                |
                                                     +----------+---------+
                                                     | Order Submission   |  IG adapter
                                                     +----------+---------+
                                                                |
                                                     +----------+---------+
                                                     |  Notify — order    |
                                                     |  placed            |
                                                     +--------------------+
```

Every path through the pipeline writes to `logs/audit.log`. The pipeline is designed to be safe to interrupt at any point — no intermediate mutable state persists between runs.

### 2.3 LLM Gate Logic

The LLM gate replaces human approval. It applies two conditions, both of which must be true for the pipeline to continue:

1. `confidence_score >= auto_trade.threshold` (default: 70, range: 0–100)
2. `llm_recommendation == "GO"`

If either condition is false, the pipeline stops for that instrument and records a suppression event. No partial state (pending order, position reservation) is created.

The threshold is configurable per instrument via `config/instruments/<symbol>.yaml` or globally via `config/local.yaml`:

```yaml
auto_trade:
  threshold: 70           # minimum confidence score to proceed
  live_enabled: false     # master switch — see Section 2.9
```

An instrument-level override takes precedence over the global value, enabling tighter thresholds for volatile instruments.

### 2.4 Risk Checks

Risk checks run after the LLM gate passes. They execute in the order listed. The sequence stops at the first failure and records the failing check in the audit log.

| # | Check                        | Data Source                      | Failure Action          |
|---|------------------------------|----------------------------------|-------------------------|
| 1 | Kill switch not active       | `config/local.yaml` or env var   | Suppress, log, notify   |
| 2 | Market session is OPEN       | Instrument config + system clock | Suppress, log           |
| 3 | No existing open position    | IG position API                  | Suppress, log           |
| 4 | Daily loss limit not breached| `data/journal/` entries          | Suppress, log, notify   |
| 5 | Max open positions not exceeded | IG position API               | Suppress, log           |

**Check 1 — Kill switch:** Checked first because it represents an operator override of the entire system. The kill switch can be a file (`KILL_SWITCH` in the repo root) or an environment variable (`TRADING_KILL_SWITCH=1`). The file-based switch is preferred for Windows compatibility.

**Check 3 — Duplicate guard:** Prevents double-entry when `run_auto_trade.py` is invoked more than once within a session. Queries the live IG position list and skips submission if an open position for the instrument already exists in the same direction. This is the primary mechanism that makes the script idempotent.

**Check 4 — Daily loss limit:** Reads realised P&L from the trade journal entries written during the current calendar day (broker timezone). If cumulative loss exceeds the configured limit, the pipeline halts for all remaining instruments in the current run.

All thresholds for checks 4 and 5 are configured in `config/local.yaml` under `risk:`.

Risk checks are implemented in `src/trading_lab/execution/risk_checks.py` and are also called from the Phase 3 manual approval flow to maintain a consistent enforcement surface.

### 2.5 New Modules

**`src/trading_lab/execution/auto_trader.py`**

Orchestrates the full automated pipeline for one or more instruments. Entry point called by `scripts/run_auto_trade.py`. Responsibilities:
- Load config and initialise all dependencies (LLM client via factory, IG adapter, notifier).
- Iterate over configured instruments.
- For each instrument: fetch data, compute signals, call LLM gate, call risk checks, call position sizing, submit order.
- Write audit record after each instrument regardless of outcome.
- Catch and log any unhandled exception per instrument; continue to the next instrument rather than aborting the run.
- Emit daily summary notification at end of run.

**`src/trading_lab/execution/risk_checks.py`**

Implements the five pre-submission risk checks as discrete, testable functions. Shared between the auto-trader pipeline and the Phase 3 manual approval flow. Each function returns a `RiskCheckResult` (dataclass with `passed: bool`, `check_name: str`, `reason: str`). A convenience function `run_all_checks(context) -> list[RiskCheckResult]` executes them in order and returns early on first failure.

**`src/trading_lab/notifications.py`**

Sends push notifications for the events listed in Section 2.7. Supports ntfy.sh (default, no account required) and Pushover as backend providers, selected via `config/local.yaml`:

```yaml
notifications:
  provider: ntfy           # ntfy | pushover | none
  ntfy_topic: trading-lab  # ntfy.sh topic name (keep private)
  pushover_token:          # read from env: PUSHOVER_TOKEN
  pushover_user:           # read from env: PUSHOVER_USER
```

Notification failures must never abort the trading pipeline. All notification calls are wrapped in try/except; failures are logged at WARNING level only.

**`scripts/run_auto_trade.py`**

Entry point for scheduled execution. Loads config, calls `auto_trader.run(config)`, exits with code 0 on clean completion (including suppressed signals) and code 1 on unrecoverable initialisation failure. Does not contain business logic — it is wiring only.

### 2.6 Scheduling Design

`run_auto_trade.py` is driven by an external scheduler. No in-process scheduler (APScheduler, Celery) is introduced at this stage.

**Linux / WSL:** cron job targeting the appropriate time after daily bar close and data availability. Example for a 22:00 UTC daily run:

```
0 22 * * 1-5 /home/jimi/.venv/bin/python /mnt/c/Dev/trading-lab/scripts/run_auto_trade.py >> /mnt/c/Dev/trading-lab/logs/auto_trade_cron.log 2>&1
```

**Windows native:** Windows Task Scheduler task, set to run the Python interpreter with the script path. Trigger: daily, time-based.

The script is idempotent (duplicate guard in check 3) so accidental double-runs do not cause double-entry. A lock file (`logs/auto_trade.lock`) should be written at startup and removed at exit to prevent concurrent runs from the same scheduler if a previous run hangs.

### 2.7 Notification Events

The notifier sends push notifications for the following events. All notifications include the instrument symbol and UTC timestamp.

| Event                         | Fields included                                              |
|-------------------------------|--------------------------------------------------------------|
| Order placed                  | Instrument, direction, size, entry price, stop, take-profit  |
| Signal suppressed — LLM gate  | Instrument, direction, confidence score, recommendation      |
| Signal suppressed — risk check| Instrument, direction, failing check name, reason            |
| Daily summary                 | Instruments reviewed, orders placed, suppressed count, P&L (if available) |
| Pipeline error                | Script, error type, message (truncated to 200 chars)         |

Notifications are best-effort. The pipeline must not block on notification delivery.

### 2.8 Audit Trail

Every automated run writes structured entries to `logs/audit.log`. Each entry is one JSON object per line (JSONL format) for straightforward parsing and grep.

Required fields per entry:

| Field               | Type    | Description                                            |
|---------------------|---------|--------------------------------------------------------|
| `ts`                | string  | ISO 8601 UTC timestamp                                 |
| `run_id`            | string  | UUID generated per script invocation                   |
| `symbol`            | string  | Instrument identifier                                  |
| `signal_direction`  | string  | LONG / SHORT / FLAT                                    |
| `confidence_score`  | int     | 0–100 from LLM response                                |
| `llm_recommendation`| string  | GO / NO-GO / UNCERTAIN                                 |
| `llm_provider`      | string  | Active provider name (gemini, deepseek, etc.)          |
| `risk_checks`       | array   | List of `{check, passed, reason}` objects              |
| `outcome`           | string  | ORDER_PLACED / SUPPRESSED_LLM / SUPPRESSED_RISK / ERROR|
| `order_ref`         | string  | Broker order reference if placed, else null            |
| `suppression_reason`| string  | Human-readable reason if suppressed, else null         |

The audit log is append-only. Do not rotate or truncate it during live operation. Archive monthly to `logs/archive/`.

### 2.9 Demo Validation Gate

Live auto-trading is locked behind a config flag that defaults to `false`:

```yaml
auto_trade:
  live_enabled: false
```

When `live_enabled: false`, `run_auto_trade.py` runs the full pipeline (ingest, signals, LLM gate, risk checks) but skips order submission and logs `DEMO_RUN` as the outcome. Notifications are sent as if real, tagged with `[DEMO]` in the message body, so the operator sees realistic output without capital at risk.

The flag must be manually changed to `true` to enable live submission. There is no automatic promotion. The intended validation period before enabling live trading is 30 calendar days of demo runs with consistent signal quality.

A future check may enforce a minimum number of demo audit entries before allowing `live_enabled: true`, but this is not implemented in Phase 4.

### 2.10 Phase 4 Prerequisites

Phase 4 must not be activated until both of the following are satisfied:

1. **Phase 3 is complete and stable.** The manual approval flow (dashboard, IG adapter, order submission, position monitoring) must have been exercised on the demo account without defects. Risk checks introduced in Phase 4 reuse Phase 3 components — they must be correct first.

2. **30-day demo validation period is complete.** `run_auto_trade.py` must have run daily for at least 30 days with `live_enabled: false`, generating an audit log that can be reviewed for signal quality, LLM gate calibration, and pipeline reliability.

After both conditions are met, `live_enabled: true` may be set with appropriate position size limits configured conservatively.

---

## 3. Impact on Existing Architecture

### 3.1 Unchanged V2 Components

The following V2 components are not modified by these decisions:

- `src/trading_lab/llm/base.py` — LLMClient ABC
- `src/trading_lab/llm/claude_client.py` — Anthropic implementation
- `src/trading_lab/llm/stub_client.py` — test stub
- `src/trading_lab/data/` — all ingestion and normalisation modules
- `src/trading_lab/strategies/` — all signal logic
- `src/trading_lab/backtesting/` — simulation engine
- `src/trading_lab/execution/ig_adapter.py` — IG broker adapter
- `config/` schema — additions only, no breaking changes
- `ARCHITECTURE - V2.md` — remains the primary reference

### 3.2 Extended V2 Components

| Component                          | Change                                                             |
|------------------------------------|--------------------------------------------------------------------|
| `src/trading_lab/execution/`       | Two new modules added: `auto_trader.py`, `risk_checks.py`         |
| `src/trading_lab/llm/`             | Three new concrete clients added; new `factory.py`                |
| `src/trading_lab/` (package root)  | New `notifications.py` module                                     |
| `config/local.yaml`                | New `llm`, `auto_trade`, `risk`, `notifications` sections         |
| `.env.example`                     | New keys: `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`  |
| `scripts/`                         | New `run_auto_trade.py` entry point                               |
| `logs/`                            | New `audit.log` (JSONL) and `auto_trade_cron.log`                 |
| `pyproject.toml` / `requirements`  | New dependencies: `google-genai`, `openai`                        |

Any existing caller that instantiates `ClaudeClient` directly must be updated to call `create_llm_client(config)`. This is the only breaking change to existing code.

### 3.3 Build Plan Impact

The following build plan steps from V2 are directly affected:

- **Phase 2 / Phase 3 — LLM advisory gate:** Callers must be updated to use the factory. No logic changes required — only the construction call.
- **Phase 3 — pre-submission checks:** The `risk_checks.py` module introduced in Phase 4 should be written during Phase 3 completion so it is proven before Phase 4 activates it in the automated path.
- **Phase 4 (new):** Not present in V2 build plan. Add a Phase 4 milestone covering: multi-provider LLM (this document Section 1), automated pipeline (Section 2), demo validation period, and live enablement gate.

---

## 4. Open Architecture Questions

The following questions have provisional answers recorded here. They remain open for revision as the system matures.

**Should the factory support runtime provider switching?**
Current decision: No. The provider is selected once at startup and held for the lifetime of the process. Runtime switching would make audit records ambiguous (which provider produced which decision?) and adds complexity with no current operational need. Revisit if multi-provider A/B testing becomes a research goal.

**Should DeepSeek use its own SDK or the OpenAI compatibility layer?**
Current decision: OpenAI compatibility layer (`openai` SDK with `base_url` override). DeepSeek's REST API is documented as OpenAI-compatible and the `openai` package is already a dependency for the OpenAI provider. A separate native DeepSeek SDK would add a dependency for marginal benefit. Revisit only if the compatibility layer proves unreliable for specific response formats.

**Auto-trade scheduling: external scheduler vs in-process scheduler?**
Current decision: External scheduler (cron / Windows Task Scheduler). An in-process scheduler (APScheduler, Celery Beat) introduces a long-running process that must be monitored, restarted on failure, and deployed carefully. The current single-operator context does not justify this. The external scheduler is more transparent and debuggable. Revisit if scheduling requirements become complex (e.g., intraday bars, multiple independent schedules).

**Notification provider: ntfy.sh vs Pushover?**
Current decision: ntfy.sh as default. It requires no account for self-hosted topics and no per-message cost. Pushover is supported as a configured alternative for operators who prefer it. Neither is mandatory — `provider: none` disables notifications without affecting the pipeline. Revisit if notification reliability becomes a concern in live operation.
