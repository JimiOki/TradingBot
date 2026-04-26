"""Stub LLM client for testing and environments without an API key."""
from trading_lab.llm.base import LLMClient

STUB_RESPONSE = "[Stub explanation — LLM not configured]"


class StubLLMClient(LLMClient):
    """Returns a fixed string without making any API calls."""

    def complete(self, prompt: str) -> str:
        return STUB_RESPONSE
