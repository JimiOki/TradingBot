"""LLM provider factory — returns the configured LLMClient subclass."""
import logging

from trading_lab.exceptions import ConfigurationError
from trading_lab.llm.base import LLMClient

logger = logging.getLogger(__name__)


def create_llm_client(config: dict) -> LLMClient:
    """Read config and return the appropriate LLMClient subclass.

    Reads ``config["llm"]`` for provider, model, max_tokens, timeout_seconds,
    and enabled. Falls back to StubLLMClient when LLM is disabled or an API
    key is missing; raises ConfigurationError for unrecognised providers.
    """
    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "gemini")
    model_override = llm_cfg.get("model")  # None → use provider default
    max_tokens = llm_cfg.get("max_tokens", 500)
    timeout = llm_cfg.get("timeout_seconds", 30.0)
    enabled = llm_cfg.get("enabled", True)

    if not enabled:
        logger.info("LLM disabled in config — using StubLLMClient")
        from trading_lab.llm.stub_client import StubLLMClient
        return StubLLMClient()

    try:
        if provider == "gemini":
            from trading_lab.llm.gemini_client import GeminiClient
            kwargs = {"max_tokens": max_tokens, "timeout": timeout}
            if model_override:
                kwargs["model"] = model_override
            return GeminiClient(**kwargs)

        elif provider == "openai":
            from trading_lab.llm.openai_client import OpenAIClient
            kwargs = {"max_tokens": max_tokens, "timeout": timeout}
            if model_override:
                kwargs["model"] = model_override
            return OpenAIClient(**kwargs)

        elif provider == "deepseek":
            from trading_lab.llm.deepseek_client import DeepSeekClient
            kwargs = {"max_tokens": max_tokens, "timeout": timeout}
            if model_override:
                kwargs["model"] = model_override
            return DeepSeekClient(**kwargs)

        elif provider == "claude":
            from trading_lab.llm.claude_client import ClaudeClient
            kwargs = {"max_tokens": max_tokens, "timeout": timeout}
            if model_override:
                kwargs["model"] = model_override
            return ClaudeClient(**kwargs)

        elif provider == "stub":
            from trading_lab.llm.stub_client import StubLLMClient
            return StubLLMClient()

        else:
            raise ConfigurationError(
                f"Unknown LLM provider: '{provider}'. Valid: gemini, deepseek, openai, claude, stub"
            )

    except ConfigurationError as exc:
        # Re-raise for unrecognised provider; fall back for missing API key
        if "Unknown LLM provider" in str(exc):
            raise
        logger.warning(
            "LLM provider '%s' has no API key — falling back to StubLLMClient", provider
        )
        from trading_lab.llm.stub_client import StubLLMClient
        return StubLLMClient()
