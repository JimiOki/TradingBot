"""Google Gemini API client."""
import logging
import os
import time

from google import genai
from google.genai import types as genai_types

from trading_lab.exceptions import ConfigurationError, LLMError, LLMTimeoutError
from trading_lab.llm.base import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_TOKENS = 65536


class GeminiClient(LLMClient):
    """LLM client backed by the Google Gemini API (google-genai SDK v1+).

    Uses JSON response mode and captures thinking separately so the model's
    reasoning chain doesn't corrupt the structured JSON output.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "GOOGLE_API_KEY environment variable is not set. "
                "Set it or use StubLLMClient for offline operation."
            )
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._client = genai.Client(api_key=api_key)
        self.last_thinking: str | None = None  # captured reasoning from last call

    def complete(self, prompt: str, json_mode: bool = False, max_retries: int = 2) -> str:
        """Send a prompt to Gemini and return the completion text.

        Retries up to max_retries times on failure (free model, no cost).
        When json_mode=True, uses JSON response mode so the model returns
        valid JSON. Thinking is always enabled — the model's reasoning
        is captured in self.last_thinking.
        """
        last_exc: Exception | None = None
        self.last_thinking = None
        for attempt in range(1, max_retries + 1):
            start = time.monotonic()
            try:
                config_kwargs = {
                    "max_output_tokens": self.max_tokens,
                    "thinking_config": genai_types.ThinkingConfig(
                        include_thoughts=True,
                        thinking_budget=1024,
                    ),
                }
                if json_mode:
                    config_kwargs["response_mime_type"] = "application/json"

                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(**config_kwargs),
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)

                # Extract thinking and output from response parts
                thinking_parts = []
                output_parts = []
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "thought") and part.thought:
                        thinking_parts.append(part.text)
                    else:
                        output_parts.append(part.text)

                self.last_thinking = "\n".join(thinking_parts) if thinking_parts else None
                output = "\n".join(output_parts) if output_parts else response.text

                if self.last_thinking:
                    logger.debug(
                        "LLM thinking (%d chars): %.200s...",
                        len(self.last_thinking), self.last_thinking,
                    )
                logger.debug(
                    "LLM call complete: model=%s elapsed_ms=%d attempt=%d",
                    self.model, elapsed_ms, attempt,
                )
                return output
            except Exception as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                last_exc = exc
                if "timeout" in str(exc).lower() or "deadline" in str(exc).lower():
                    logger.warning(
                        "LLM timeout: model=%s elapsed_ms=%d attempt=%d error=%s",
                        self.model, elapsed_ms, attempt, exc,
                    )
                    if attempt == max_retries:
                        raise LLMTimeoutError(f"Gemini API timed out after {self.timeout}s") from exc
                else:
                    logger.warning(
                        "LLM API error: model=%s elapsed_ms=%d attempt=%d error=%s",
                        self.model, elapsed_ms, attempt, exc,
                    )
                    if attempt == max_retries:
                        raise LLMError(f"Gemini API error: {exc}") from exc
                # Brief pause before retry
                time.sleep(1)

        raise LLMError(f"Gemini API failed after {max_retries} attempts: {last_exc}")
