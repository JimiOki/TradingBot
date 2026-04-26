"""Tests for src/trading_lab/config/loader.py"""
import pytest
import yaml

from trading_lab.config.loader import load_instruments
from trading_lab.exceptions import ConfigValidationError


def _write_yaml(tmp_path, instruments: list[dict]) -> object:
    path = tmp_path / "instruments.yaml"
    path.write_text(yaml.dump({"instruments": instruments}))
    return path


VALID_INSTRUMENT = {
    "symbol": "GC=F",
    "name": "Gold",
    "asset_class": "commodity",
    "timeframe": "1d",
    "source": "yfinance",
    "session_timezone": "America/New_York",
    "adjusted_prices": True,
}


def test_load_valid_instrument(tmp_path):
    path = _write_yaml(tmp_path, [VALID_INSTRUMENT])
    result = load_instruments(path)
    assert len(result) == 1
    assert result[0]["symbol"] == "GC=F"


def test_load_multiple_instruments(tmp_path):
    second = {**VALID_INSTRUMENT, "symbol": "CL=F", "name": "Crude Oil"}
    path = _write_yaml(tmp_path, [VALID_INSTRUMENT, second])
    result = load_instruments(path)
    assert len(result) == 2


def test_missing_required_field_raises(tmp_path):
    bad = {k: v for k, v in VALID_INSTRUMENT.items() if k != "asset_class"}
    path = _write_yaml(tmp_path, [bad])
    with pytest.raises(ConfigValidationError, match="asset_class"):
        load_instruments(path)


def test_missing_symbol_raises(tmp_path):
    bad = {k: v for k, v in VALID_INSTRUMENT.items() if k != "symbol"}
    path = _write_yaml(tmp_path, [bad])
    with pytest.raises(ConfigValidationError, match="symbol"):
        load_instruments(path)


def test_invalid_asset_class_raises(tmp_path):
    bad = {**VALID_INSTRUMENT, "asset_class": "crypto"}
    path = _write_yaml(tmp_path, [bad])
    with pytest.raises(ConfigValidationError, match="asset_class"):
        load_instruments(path)


def test_invalid_timeframe_raises(tmp_path):
    bad = {**VALID_INSTRUMENT, "timeframe": "4h"}
    path = _write_yaml(tmp_path, [bad])
    with pytest.raises(ConfigValidationError, match="timeframe"):
        load_instruments(path)


def test_invalid_timezone_raises(tmp_path):
    bad = {**VALID_INSTRUMENT, "session_timezone": "Not/ATimezone"}
    path = _write_yaml(tmp_path, [bad])
    with pytest.raises(ConfigValidationError, match="session_timezone"):
        load_instruments(path)


def test_empty_instruments_list_raises(tmp_path):
    path = tmp_path / "instruments.yaml"
    path.write_text(yaml.dump({"instruments": []}))
    with pytest.raises(ConfigValidationError):
        load_instruments(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_instruments(tmp_path / "nonexistent.yaml")


def test_all_valid_asset_classes_accepted(tmp_path):
    for asset_class in ("commodity", "equity", "index", "fx"):
        entry = {**VALID_INSTRUMENT, "asset_class": asset_class}
        path = _write_yaml(tmp_path, [entry])
        result = load_instruments(path)
        assert result[0]["asset_class"] == asset_class


def test_weekly_timeframe_accepted(tmp_path):
    entry = {**VALID_INSTRUMENT, "timeframe": "1wk"}
    path = _write_yaml(tmp_path, [entry])
    result = load_instruments(path)
    assert result[0]["timeframe"] == "1wk"
