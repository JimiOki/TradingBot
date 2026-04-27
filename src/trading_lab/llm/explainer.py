"""ExplanationService — cache-first LLM signal explanation generator.

REQ-LLM-001: Explanations are generated once per signal and cached to disk.
REQ-LLM-004: If LLM fails, return EXPLANATION_UNAVAILABLE constant.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from trading_lab.audit import AuditAction, log_event
from trading_lab.exceptions import LLMError, LLMTimeoutError
from trading_lab.llm.base import LLMClient
from trading_lab.llm.context import SignalContext
from trading_lab.llm.prompts import build_explanation_prompt
from trading_lab.paths import EXPLANATIONS_DIR

logger = logging.getLogger(__name__)

EXPLANATION_UNAVAILABLE = "Explanation unavailable."
_MAX_EXPLANATION_CHARS = 2500


@dataclass(frozen=True)
class SignalExplanation:
    """Cached output of a single explanation request."""
    symbol: str
    signal_date: date
    signal: int
    explanation: str
    generated_at: datetime
    model: str
    cached: bool


class ExplanationService:
    """Generates and caches LLM explanations for trading signals."""

    def __init__(self, client: LLMClient, cache_dir: Path = EXPLANATIONS_DIR) -> None:
        self._client = client
        self._cache_dir = cache_dir

    def get_or_generate(self, context: SignalContext) -> SignalExplanation:
        """Return a cached explanation or generate a new one via the LLM.

        Cache path: <cache_dir>/<symbol>_<date>.json
        """
        cache_path = self._cache_dir / f"{context.symbol}_{context.signal_date}.json"

        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    data = json.load(f)
                log_event(
                    AuditAction.LLM_CALL_CACHED,
                    instrument=context.symbol,
                    values={"signal_date": str(context.signal_date)},
                )
                return SignalExplanation(
                    symbol=data["symbol"],
                    signal_date=date.fromisoformat(data["signal_date"]),
                    signal=data["signal"],
                    explanation=data["explanation"],
                    generated_at=datetime.fromisoformat(data["generated_at"]),
                    model=data["model"],
                    cached=True,
                )
            except (KeyError, ValueError, OSError) as exc:
                logger.warning("Cache read failed for %s: %s", cache_path, exc)

        # Cache miss — call LLM
        prompt = build_explanation_prompt(context)
        try:
            explanation = self._client.complete(prompt)
            if not explanation or len(explanation) > _MAX_EXPLANATION_CHARS:
                raise LLMError(
                    f"Explanation validation failed: length={len(explanation or '')}"
                )
        except (LLMError, LLMTimeoutError) as exc:
            logger.warning("LLM call failed for %s: %s", context.symbol, exc)
            log_event(
                AuditAction.LLM_CALL_FAILED,
                instrument=context.symbol,
                values={"signal_date": str(context.signal_date), "error": str(exc)},
            )
            return SignalExplanation(
                symbol=context.symbol,
                signal_date=context.signal_date,
                signal=context.signal,
                explanation=EXPLANATION_UNAVAILABLE,
                generated_at=datetime.now(timezone.utc),
                model=getattr(self._client, "model", "stub"),
                cached=False,
            )

        generated_at = datetime.now(timezone.utc)
        result = SignalExplanation(
            symbol=context.symbol,
            signal_date=context.signal_date,
            signal=context.signal,
            explanation=explanation,
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
                "explanation": result.explanation,
                "generated_at": result.generated_at.isoformat(),
                "model": result.model,
            }
            cache_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Cache write failed for %s: %s", cache_path, exc)

        log_event(
            AuditAction.LLM_CALL_MADE,
            instrument=context.symbol,
            values={"signal_date": str(context.signal_date), "model": result.model},
        )
        return result
