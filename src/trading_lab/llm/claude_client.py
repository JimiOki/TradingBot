"""Anthropic Claude API client."""
import logging
import os
import time

import anthropic

from trading_lab.exceptions import ConfigurationError, LLMError, LLMTimeoutError
from trading_lab.llm.base import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_TOKENS = 500


class ClaudeClient(LLMClient):
    """LLM client backed by the Anthropic Claude API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Set it or use StubLLMClient for offline operation."
            )
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, prompt: str) -> str:
        """Send a prompt to Claude and return the completion text."""
        start = time.monotonic()
        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=self.timeout,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.debug(
                "LLM call complete: model=%s elapsed_ms=%d", self.model, elapsed_ms
            )
            return message.content[0].text
        except anthropic.APITimeoutError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "LLM timeout: model=%s elapsed_ms=%d error=%s", self.model, elapsed_ms, exc
            )
            raise LLMTimeoutError(f"Claude API timed out after {self.timeout}s") from exc
        except anthropic.APIError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "LLM API error: model=%s elapsed_ms=%d error=%s", self.model, elapsed_ms, exc
            )
            raise LLMError(f"Claude API error: {exc}") from exc
