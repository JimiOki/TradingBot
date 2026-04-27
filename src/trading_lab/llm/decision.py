"""DecisionService — cache-first LLM go/no-go judgment for trading signals.

REQ-LLMDEC-001: LLM decision is a structured GO/NO_GO/UNCERTAIN recommendation.
REQ-GUARD-001: NO_GO and UNCERTAIN are first-class outcomes; prompt must not force GO.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from trading_lab.audit import AuditAction, log_event
from trading_lab.exceptions import LLMError, LLMTimeoutError
from trading_lab.llm.base import LLMClient
from trading_lab.llm.context import SignalContext
from trading_lab.llm.prompts import build_decision_prompt
from trading_lab.paths import DATA_DIR

logger = logging.getLogger(__name__)

DECISIONS_DIR = DATA_DIR / "signals" / "decisions"
DECISION_UNAVAILABLE = "Decision unavailable."
_VALID_RECOMMENDATIONS = {"GO", "NO_GO", "UNCERTAIN"}


@dataclass(frozen=True)
class LLMDecision:
    """Structured go/no-go judgment from the LLM layer."""
    symbol: str
    signal_date: date
    signal: int
    llm_recommendation: str      # "GO", "NO_GO", or "UNCERTAIN"
    direction: str | None        # "LONG", "SHORT", or None
    rationale: str               # 1-3 sentences
    conflicts_with_technical: bool
    generated_at: datetime
    model: str
    cached: bool


class DecisionService:
    """Generates and caches LLM go/no-go decisions for trading signals."""

    def __init__(self, client: LLMClient, cache_dir: Path = DECISIONS_DIR) -> None:
        self._client = client
        self._cache_dir = cache_dir

    def get_or_generate(self, context: SignalContext) -> LLMDecision:
        """Return a cached decision or generate a new one via the LLM."""
        cache_path = self._cache_dir / f"{context.symbol}_{context.signal_date}.json"

        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    data = json.load(f)
                log_event(
                    AuditAction.LLM_CALL_CACHED,
                    instrument=context.symbol,
                    values={"signal_date": str(context.signal_date), "type": "decision"},
                )
                return LLMDecision(
                    symbol=data["symbol"],
                    signal_date=date.fromisoformat(data["signal_date"]),
                    signal=data["signal"],
                    llm_recommendation=data["llm_recommendation"],
                    direction=data.get("direction"),
                    rationale=data["rationale"],
                    conflicts_with_technical=data["conflicts_with_technical"],
                    generated_at=datetime.fromisoformat(data["generated_at"]),
                    model=data["model"],
                    cached=True,
                )
            except (KeyError, ValueError, OSError) as exc:
                logger.warning("Decision cache read failed for %s: %s", cache_path, exc)

        # Cache miss — call LLM
        prompt = build_decision_prompt(context)
        try:
            raw = self._client.complete(prompt)
            decision = self._parse_decision(raw)
        except (LLMError, LLMTimeoutError, ValueError) as exc:
            logger.warning("LLM decision failed for %s: %s", context.symbol, exc)
            log_event(
                AuditAction.LLM_CALL_FAILED,
                instrument=context.symbol,
                values={"signal_date": str(context.signal_date), "error": str(exc), "type": "decision"},
            )
            return LLMDecision(
                symbol=context.symbol,
                signal_date=context.signal_date,
                signal=context.signal,
                llm_recommendation="UNCERTAIN",
                direction=None,
                rationale=DECISION_UNAVAILABLE,
                conflicts_with_technical=False,
                generated_at=datetime.now(timezone.utc),
                model=getattr(self._client, "model", "stub"),
                cached=False,
            )

        generated_at = datetime.now(timezone.utc)
        result = LLMDecision(
            symbol=context.symbol,
            signal_date=context.signal_date,
            signal=context.signal,
            llm_recommendation=decision["recommendation"],
            direction=decision.get("direction"),
            rationale=decision["rationale"],
            conflicts_with_technical=bool(decision.get("conflicts_with_technical", False)),
            generated_at=generated_at,
            model=getattr(self._client, "model", "stub"),
            cached=False,
        )

        # Persist to cache
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "symbol": result.symbol,
                "signal_date": str(result.signal_date),
                "signal": result.signal,
                "llm_recommendation": result.llm_recommendation,
                "direction": result.direction,
                "rationale": result.rationale,
                "conflicts_with_technical": result.conflicts_with_technical,
                "generated_at": result.generated_at.isoformat(),
                "model": result.model,
            }
            cache_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Decision cache write failed for %s: %s", cache_path, exc)

        log_event(
            AuditAction.LLM_CALL_MADE,
            instrument=context.symbol,
            values={"signal_date": str(context.signal_date), "model": result.model, "type": "decision"},
        )
        return result

    def _parse_decision(self, raw: str) -> dict:
        """Parse LLM JSON response into a decision dict.

        Falls back to UNCERTAIN on any parse failure.
        Raises ValueError if the JSON is invalid or recommendation is unrecognised.
        """
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM response is not valid JSON: {exc}") from exc

        recommendation = data.get("recommendation", "").upper()
        if recommendation not in _VALID_RECOMMENDATIONS:
            raise ValueError(f"Unrecognised recommendation '{recommendation}'")

        raw_direction = data.get("direction")
        if raw_direction is not None:
            raw_direction = str(raw_direction).upper()
            if raw_direction not in {"LONG", "SHORT"}:
                raw_direction = None
        # Enforce: direction must be null when recommendation is not GO
        if recommendation != "GO":
            raw_direction = None

        return {
            "recommendation": recommendation,
            "direction": raw_direction,
            "rationale": str(data.get("rationale", DECISION_UNAVAILABLE)),
            "conflicts_with_technical": bool(data.get("conflicts_with_technical", False)),
        }
