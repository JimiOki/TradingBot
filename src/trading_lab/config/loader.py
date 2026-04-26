"""Instrument configuration loader and validator.

Reads config/instruments.yaml and validates every entry against the required
schema. Any missing or invalid field raises ConfigValidationError before the
calling code has a chance to use bad data.
"""
from __future__ import annotations

import zoneinfo
from pathlib import Path

import yaml

from trading_lab.exceptions import ConfigValidationError

_REQUIRED_FIELDS = [
    "symbol",
    "name",
    "asset_class",
    "timeframe",
    "source",
    "session_timezone",
    "adjusted_prices",
]

_VALID_ASSET_CLASSES = {"commodity", "equity", "index", "fx"}
_VALID_TIMEFRAMES = {"1d", "1wk"}


def load_instruments(config_path: Path) -> list[dict]:
    """Load and validate instrument definitions from a YAML file.

    Args:
        config_path: Path to instruments.yaml.

    Returns:
        List of validated instrument dicts.

    Raises:
        ConfigValidationError: If any instrument entry fails validation.
        FileNotFoundError: If config_path does not exist.
    """
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    instruments = raw.get("instruments", [])
    if not instruments:
        raise ConfigValidationError(
            f"No instruments found in {config_path}. "
            "The file must contain a top-level 'instruments' list."
        )

    validated = []
    for entry in instruments:
        _validate_instrument(entry, config_path)
        validated.append(entry)

    return validated


def _validate_instrument(entry: dict, config_path: Path) -> None:
    symbol = entry.get("symbol", "<unknown>")

    for field in _REQUIRED_FIELDS:
        if field not in entry or entry[field] is None:
            raise ConfigValidationError(
                f"Instrument '{symbol}' in {config_path} is missing required field '{field}'."
            )

    asset_class = entry["asset_class"]
    if asset_class not in _VALID_ASSET_CLASSES:
        raise ConfigValidationError(
            f"Instrument '{symbol}': invalid asset_class '{asset_class}'. "
            f"Must be one of: {sorted(_VALID_ASSET_CLASSES)}."
        )

    timeframe = entry["timeframe"]
    if timeframe not in _VALID_TIMEFRAMES:
        raise ConfigValidationError(
            f"Instrument '{symbol}': invalid timeframe '{timeframe}'. "
            f"Must be one of: {sorted(_VALID_TIMEFRAMES)}."
        )

    timezone = entry["session_timezone"]
    if timezone not in zoneinfo.available_timezones():
        raise ConfigValidationError(
            f"Instrument '{symbol}': invalid session_timezone '{timezone}'. "
            "Must be a valid IANA timezone identifier."
        )
