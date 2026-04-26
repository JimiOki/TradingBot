"""Unit tests for pure functions in app/pages/charts.py.

Covers:
  - apply_lookback(df, period)
  - build_chart(df, symbol, name, rsi_overbought, rsi_oversold)

I/O-dependent functions (load_instruments, load_curated_bars, curated_path)
are excluded and belong in integration tests.
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import pytest
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Path injection — add ROOT/app to sys.path so "pages.charts" is importable.
# ROOT is the repo root, one level above the tests directory.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
_app_path = str(ROOT / "app")
if _app_path not in sys.path:
    sys.path.insert(0, _app_path)

# Also inject ROOT/src so that trading_lab imports inside charts.py resolve.
_src_path = str(ROOT / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# Skip the entire module gracefully if charts.py cannot be imported
# (e.g. missing optional dependencies in a minimal CI environment).
charts = pytest.importorskip("pages.charts", reason="app/pages/charts.py not found")

apply_lookback = charts.apply_lookback
build_chart = charts.build_chart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlc_df(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Return a minimal OHLC DataFrame for the given DatetimeIndex."""
    n = len(index)
    close = np.linspace(100.0, 110.0, n)
    open_ = close * 0.999
    high = close * 1.002
    low = close * 0.997
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=index,
    )


def _trace_names(fig: go.Figure) -> list[str]:
    """Return the list of trace names from a Figure."""
    return [t.name for t in fig.data]


# ---------------------------------------------------------------------------
# apply_lookback tests
# ---------------------------------------------------------------------------


class TestApplyLookback:
    """Tests for apply_lookback(df, period)."""

    def _make_span_df(self, years: int) -> pd.DataFrame:
        """Create a tz-aware daily DataFrame spanning `years` years up to today."""
        end = pd.Timestamp.now(tz="UTC").normalize()
        start = end - pd.DateOffset(years=years)
        index = pd.date_range(start, end, freq="D", tz="UTC")
        return _make_ohlc_df(index)

    def test_apply_lookback_all_returns_full_df(self):
        """period='All' should return the DataFrame unchanged (same length)."""
        df = self._make_span_df(2)
        result = apply_lookback(df, "All")
        assert len(result) == len(df)

    def test_apply_lookback_3m_filters_old_rows(self):
        """period='3M' on a 2-year span should keep only the last ~3 months."""
        df = self._make_span_df(2)
        result = apply_lookback(df, "3M")
        # Must be strictly fewer rows than the full DataFrame
        assert len(result) < len(df)
        # The earliest row in the result should be within 3 months + 2-day buffer
        cutoff = pd.Timestamp.now(tz="UTC") - pd.DateOffset(months=3)
        assert result.index.min() >= cutoff - pd.Timedelta(days=2)

    def test_apply_lookback_1y_filters_correctly(self):
        """period='1Y' on a 3-year span keeps approximately the last year."""
        df = self._make_span_df(3)
        result_1y = apply_lookback(df, "1Y")
        result_all = apply_lookback(df, "All")
        assert len(result_1y) < len(result_all)
        cutoff = pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=1)
        assert result_1y.index.min() >= cutoff - pd.Timedelta(days=2)

    def test_apply_lookback_empty_df_returns_empty(self):
        """An empty DataFrame should be returned as-is for any period."""
        empty = pd.DataFrame(
            columns=["open", "high", "low", "close"],
            index=pd.DatetimeIndex([], tz="UTC"),
        )
        for period in ["3M", "6M", "1Y", "2Y", "All"]:
            result = apply_lookback(empty, period)
            assert result.empty, f"Expected empty df for period={period}"

    def test_apply_lookback_2y_returns_subset(self):
        """period='2Y' on a 3-year span returns fewer rows than 'All'."""
        df = self._make_span_df(3)
        result_2y = apply_lookback(df, "2Y")
        result_all = apply_lookback(df, "All")
        assert len(result_2y) < len(result_all)


# ---------------------------------------------------------------------------
# build_chart tests
# ---------------------------------------------------------------------------


class TestBuildChart:
    """Tests for build_chart(df, symbol, name, rsi_overbought, rsi_oversold)."""

    def _minimal_df(self, sample_bars: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame with only OHLC columns."""
        return sample_bars[["open", "high", "low", "close"]].copy()

    def test_build_chart_returns_figure(self, sample_bars):
        """A minimal OHLC-only DataFrame should produce a go.Figure."""
        df = self._minimal_df(sample_bars)
        fig = build_chart(df, "GC=F", "Gold")
        assert isinstance(fig, go.Figure)

    def test_build_chart_with_sma_adds_traces(self, sample_bars):
        """Adding fast_sma and slow_sma columns should add at least two extra traces."""
        df_no_sma = self._minimal_df(sample_bars)
        fig_no_sma = build_chart(df_no_sma, "GC=F", "Gold")
        traces_without = len(fig_no_sma.data)

        df_sma = df_no_sma.copy()
        df_sma["fast_sma"] = df_sma["close"].rolling(10, min_periods=1).mean()
        df_sma["slow_sma"] = df_sma["close"].rolling(30, min_periods=1).mean()
        fig_sma = build_chart(df_sma, "GC=F", "Gold")
        traces_with = len(fig_sma.data)

        assert traces_with > traces_without
        names = _trace_names(fig_sma)
        assert "Fast SMA" in names
        assert "Slow SMA" in names

    def test_build_chart_with_signals_adds_markers(self, sample_bars):
        """A df with a buy entry signal should produce a 'Buy' trace."""
        df = self._minimal_df(sample_bars).copy()

        # Default everything to flat / no change
        df["signal"] = 0
        df["position_change"] = 0

        # Plant one buy entry in the middle of the DataFrame
        buy_idx = len(df) // 2
        df.iloc[buy_idx, df.columns.get_loc("signal")] = 1
        df.iloc[buy_idx, df.columns.get_loc("position_change")] = 1

        fig = build_chart(df, "GC=F", "Gold")
        names = _trace_names(fig)
        assert "Buy" in names, f"Expected 'Buy' trace; got: {names}"

    def test_build_chart_with_macd_adds_macd_traces(self, sample_bars):
        """df with macd_line/signal_line/histogram should include a 'MACD' trace."""
        df = self._minimal_df(sample_bars).copy()

        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd_line"] = ema12 - ema26
        df["signal_line"] = df["macd_line"].ewm(span=9, adjust=False).mean()
        df["histogram"] = df["macd_line"] - df["signal_line"]

        fig = build_chart(df, "GC=F", "Gold")
        names = _trace_names(fig)
        assert "MACD" in names, f"Expected 'MACD' trace; got: {names}"

    def test_build_chart_missing_optional_cols_does_not_raise(self, sample_bars):
        """build_chart with only OHLC columns should not raise any exception."""
        df = self._minimal_df(sample_bars)
        try:
            fig = build_chart(df, "SI=F", "Silver", rsi_overbought=75.0, rsi_oversold=25.0)
        except Exception as exc:
            pytest.fail(f"build_chart raised unexpectedly: {exc}")
        assert isinstance(fig, go.Figure)
