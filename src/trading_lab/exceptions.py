"""Project-wide exception types.

All custom exceptions should be defined here so they can be imported
without creating circular dependencies between modules.
"""


class ConfigValidationError(Exception):
    """Raised when a config file fails validation.

    The message must identify the offending field and config file path.
    """


class DataQualityError(Exception):
    """Raised when ingested data fails quality checks.

    The message must include the symbol, the check that failed, and
    enough context to diagnose the problem without re-running the ingest.
    """


class SignalValidationError(Exception):
    """Raised when strategy signal output fails validation.

    The message must identify the column or value that failed.
    """


class BacktestError(Exception):
    """Raised when a backtest run cannot be completed.

    Covers insufficient data, invalid config, and engine failures.
    """


class DataSplitError(Exception):
    """Raised when the IS/OOS data split produces an invalid result.

    Typically because the out-of-sample period is too short.
    """


class ValidationOrderError(Exception):
    """Raised when OOS evaluation is attempted before IS parameters are locked."""


class ParameterDriftError(Exception):
    """Raised when strategy parameters change after the IS run is complete."""


class LLMError(Exception):
    """Raised when an LLM API call fails after exhausting retries."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM API call exceeds the configured timeout."""


class ConfigurationError(Exception):
    """Raised when a required environment variable or config value is absent."""
