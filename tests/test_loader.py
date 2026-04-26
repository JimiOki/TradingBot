"""Tests for the strategy YAML loader (REQ-SIG-002)."""
import textwrap
from pathlib import Path

import pytest

from trading_lab.exceptions import ConfigValidationError
from trading_lab.strategies.loader import load_strategy
from trading_lab.strategies.sma_cross import SmaCrossStrategy


def write_yaml(tmp_path: Path, content: str) -> Path:
    """Helper: write a YAML string to a temp file and return its Path."""
    p = tmp_path / "strategy.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------

def test_load_valid_sma_cross(tmp_path):
    """A valid sma_cross YAML returns a SmaCrossStrategy with correct params."""
    cfg = write_yaml(tmp_path, """
        strategy: sma_cross
        params:
          fast_window: 10
          slow_window: 30
    """)
    strategy = load_strategy(cfg)
    assert isinstance(strategy, SmaCrossStrategy)
    assert strategy.fast_window == 10
    assert strategy.slow_window == 30


def test_load_applies_optional_params(tmp_path):
    """Optional params (rsi_window, atr_multiplier, etc.) are forwarded to the constructor."""
    cfg = write_yaml(tmp_path, """
        strategy: sma_cross
        params:
          fast_window: 5
          slow_window: 20
          rsi_window: 21
          atr_multiplier: 2.0
          risk_reward_ratio: 3.0
    """)
    strategy = load_strategy(cfg)
    assert strategy.rsi_window == 21
    assert strategy.atr_multiplier == 2.0
    assert strategy.risk_reward_ratio == 3.0


# ---------------------------------------------------------------------------
# REQ-SIG-002: different YAMLs → different signals for same data
# ---------------------------------------------------------------------------

def test_different_yaml_params_produce_different_signals(tmp_path, sample_bars):
    """Two YAMLs with different SMA windows must produce different signal outputs."""
    cfg_a = write_yaml(tmp_path / "a.yaml" if False else tmp_path, """
        strategy: sma_cross
        params:
          fast_window: 10
          slow_window: 30
    """)
    # Write second config to a different file
    cfg_b = tmp_path / "b.yaml"
    cfg_b.write_text(textwrap.dedent("""
        strategy: sma_cross
        params:
          fast_window: 20
          slow_window: 50
    """))

    strategy_a = load_strategy(cfg_a)
    strategy_b = load_strategy(cfg_b)

    signals_a = strategy_a.generate_signals(sample_bars)
    signals_b = strategy_b.generate_signals(sample_bars)

    # Different windows → different SMA values → different signals
    assert not signals_a["fast_sma"].equals(signals_b["fast_sma"])
    assert not signals_a["signal"].equals(signals_b["signal"])


# ---------------------------------------------------------------------------
# Error cases (REQ-SIG-002)
# ---------------------------------------------------------------------------

def test_missing_required_param_raises(tmp_path):
    """Missing a required param raises ConfigValidationError naming the field and strategy."""
    cfg = write_yaml(tmp_path, """
        strategy: sma_cross
        params:
          fast_window: 10
          # slow_window intentionally omitted
    """)
    with pytest.raises(ConfigValidationError) as exc_info:
        load_strategy(cfg)
    assert "slow_window" in str(exc_info.value)
    assert "sma_cross" in str(exc_info.value)


def test_missing_strategy_key_raises(tmp_path):
    """A YAML without a 'strategy' key raises ConfigValidationError."""
    cfg = write_yaml(tmp_path, """
        params:
          fast_window: 10
          slow_window: 30
    """)
    with pytest.raises(ConfigValidationError):
        load_strategy(cfg)


def test_unknown_strategy_name_raises(tmp_path):
    """An unregistered strategy name raises ConfigValidationError."""
    cfg = write_yaml(tmp_path, """
        strategy: neural_net
        params:
          layers: 3
    """)
    with pytest.raises(ConfigValidationError) as exc_info:
        load_strategy(cfg)
    assert "neural_net" in str(exc_info.value)


def test_invalid_constructor_param_raises(tmp_path):
    """fast_window >= slow_window raises ConfigValidationError (wraps ValueError)."""
    cfg = write_yaml(tmp_path, """
        strategy: sma_cross
        params:
          fast_window: 50
          slow_window: 20
    """)
    with pytest.raises(ConfigValidationError):
        load_strategy(cfg)


def test_missing_file_raises(tmp_path):
    """A non-existent config path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_strategy(tmp_path / "does_not_exist.yaml")
