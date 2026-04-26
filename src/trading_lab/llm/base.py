"""Abstract base class for LLM clients."""
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Abstract LLM client. All concrete clients must implement complete()."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send a prompt and return the completion text.

        Args:
            prompt: The full prompt string to send to the LLM.

        Returns:
            The completion text as a plain string.

        Raises:
            LLMTimeoutError: If the request exceeds the configured timeout.
            LLMError: On any other API or network failure.
        """
