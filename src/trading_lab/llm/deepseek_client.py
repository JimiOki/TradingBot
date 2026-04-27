"""DeepSeek API client (OpenAI-compatible)."""
import logging
import os
import time

import openai

from trading_lab.exceptions import ConfigurationError, LLMError, LLMTimeoutError
from trading_lab.llm.base import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_TOKENS = 500


class DeepSeekClient(LLMClient):
    """LLM client backed by the DeepSeek API (OpenAI-compatible)."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "DEEPSEEK_API_KEY environment variable is not set. "
                "Set it or use StubLLMClient for offline operation."
            )
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._client = openai.OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def complete(self, prompt: str) -> str:
        """Send a prompt to DeepSeek and return the completion text."""
        start = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.debug(
                "LLM call complete: model=%s elapsed_ms=%d", self.model, elapsed_ms
            )
            return response.choices[0].message.content
        except openai.APITimeoutError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "LLM timeout: model=%s elapsed_ms=%d error=%s", self.model, elapsed_ms, exc
            )
            raise LLMTimeoutError(f"DeepSeek API timed out after {self.timeout}s") from exc
        except openai.APIError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "LLM API error: model=%s elapsed_ms=%d error=%s", self.model, elapsed_ms, exc
            )
            raise LLMError(f"DeepSeek API error: {exc}") from exc
