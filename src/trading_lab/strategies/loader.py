"""Strategy loader — instantiate a Strategy from a YAML config file.

REQ-SIG-002: Strategy parameters must be loadable from a YAML file in
config/strategies/, with no parameter values hardcoded in strategy classes.

Usage::

    strategy = load_strategy(Path("config/strategies/sma_cross.yaml"))
    signals = strategy.generate_signals(bars_df)
"""
from pathlib import Path
from typing import Any

import yaml

from trading_lab.exceptions import ConfigValidationError
from trading_lab.strategies.base import Strategy
from trading_lab.strategies.sma_cross import SmaCrossStrategy

# Registry maps strategy name → class.
# Add new strategy classes here when they are implemented.
_STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "sma_cross": SmaCrossStrategy,
}

# Minimum required params for each strategy.
# A missing required param raises ConfigValidationError at load time.
_REQUIRED_PARAMS: dict[str, set[str]] = {
    "sma_cross": {"fast_window", "slow_window"},
}


def load_strategy(config_path: Path) -> Strategy:
    """Load and instantiate a strategy from a YAML config file.

    Args:
        config_path: Path to the strategy YAML file (e.g. config/strategies/sma_cross.yaml).

    Returns:
        A fully constructed Strategy instance with all parameters applied.

    Raises:
        ConfigValidationError: If the strategy name is unknown, or a required
            parameter is absent from the YAML file.
        FileNotFoundError: If config_path does not exist.
    """
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    strategy_name: str = raw.get("strategy", "")
    if not strategy_name:
        raise ConfigValidationError(
            f"Config file {config_path} is missing the 'strategy' key."
        )

    strategy_cls = _STRATEGY_REGISTRY.get(strategy_name)
    if strategy_cls is None:
        known = sorted(_STRATEGY_REGISTRY)
        raise ConfigValidationError(
            f"Unknown strategy '{strategy_name}' in {config_path}. "
            f"Known strategies: {known}"
        )

    params: dict[str, Any] = raw.get("params", {}) or {}

    required = _REQUIRED_PARAMS.get(strategy_name, set())
    missing = required - params.keys()
    if missing:
        raise ConfigValidationError(
            f"Strategy '{strategy_name}' in {config_path} is missing required "
            f"parameter(s): {sorted(missing)}"
        )

    try:
        return strategy_cls(**params)
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(
            f"Failed to instantiate strategy '{strategy_name}' from {config_path}: {exc}"
        ) from exc


def strategy_name_from_config(config_path: Path) -> str:
    """Return the strategy name declared in a YAML config file."""
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return raw.get("strategy", "")
