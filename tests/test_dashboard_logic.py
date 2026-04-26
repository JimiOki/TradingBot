"""Tests for pure logic functions in app/pages/dashboard.py."""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "app"))

dashboard = pytest.importorskip("pages.dashboard", reason="dashboard page not yet written")


# ---------------------------------------------------------------------------
# get_signal_label
# ---------------------------------------------------------------------------

class TestGetSignalLabel:
    def test_buy(self):
        assert dashboard.get_signal_label(1) == "Buy"

    def test_sell(self):
        assert dashboard.get_signal_label(-1) == "Sell"

    def test_neutral(self):
        assert dashboard.get_signal_label(0) == "Neutral"

    def test_none_returns_data_missing(self):
        assert dashboard.get_signal_label(None) == "Data Missing"


# ---------------------------------------------------------------------------
# get_signal_age_days
# ---------------------------------------------------------------------------

class TestGetSignalAgeDays:
    def test_today_returns_zero(self):
        today = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = dashboard.get_signal_age_days(today)
        assert result == 0

    def test_five_days_ago(self):
        five_days_ago = datetime.now(tz=timezone.utc) - timedelta(days=5)
        result = dashboard.get_signal_age_days(five_days_ago)
        assert result == 5

    def test_none_returns_none(self):
        assert dashboard.get_signal_age_days(None) is None

    def test_nat_returns_none(self):
        assert dashboard.get_signal_age_days(pd.NaT) is None


# ---------------------------------------------------------------------------
# is_data_stale
# ---------------------------------------------------------------------------

class TestIsDataStale:
    def test_now_is_not_stale(self):
        now = datetime.now(tz=timezone.utc)
        assert dashboard.is_data_stale(now) is False

    def test_25_hours_ago_is_stale_with_default_threshold(self):
        old = datetime.now(tz=timezone.utc) - timedelta(hours=25)
        assert dashboard.is_data_stale(old) is True

    def test_none_is_stale(self):
        assert dashboard.is_data_stale(None) is True

    def test_custom_threshold_not_stale(self):
        two_hours_ago = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        assert dashboard.is_data_stale(two_hours_ago, threshold_hours=3) is False

    def test_custom_threshold_stale(self):
        four_hours_ago = datetime.now(tz=timezone.utc) - timedelta(hours=4)
        assert dashboard.is_data_stale(four_hours_ago, threshold_hours=3) is True


# ---------------------------------------------------------------------------
# compute_portfolio_summary
# ---------------------------------------------------------------------------

class TestComputePortfolioSummary:
    def _make_df(self, rows):
        """Build a minimal portfolio snapshot DataFrame from a list of dicts."""
        return pd.DataFrame(rows)

    def test_mixed_statuses(self):
        df = self._make_df([
            {"signal": 1,  "status": "ok"},
            {"signal": 1,  "status": "ok"},
            {"signal": -1, "status": "ok"},
            {"signal": 0,  "status": "ok"},
            {"signal": None, "status": "data_missing"},
            {"signal": None, "status": "data_missing"},
        ])
        result = dashboard.compute_portfolio_summary(df)
        assert result["buy"] == 2
        assert result["sell"] == 1
        assert result["neutral"] == 1
        assert result["missing"] == 2

    def test_empty_dataframe_returns_all_zeros(self):
        df = pd.DataFrame(columns=["signal", "status"])
        result = dashboard.compute_portfolio_summary(df)
        assert result["buy"] == 0
        assert result["sell"] == 0
        assert result["neutral"] == 0
        assert result["missing"] == 0

    def test_all_buy(self):
        df = self._make_df([
            {"signal": 1, "status": "ok"},
            {"signal": 1, "status": "ok"},
            {"signal": 1, "status": "ok"},
        ])
        result = dashboard.compute_portfolio_summary(df)
        assert result["buy"] == 3
        assert result["sell"] == 0
        assert result["neutral"] == 0
        assert result["missing"] == 0

    def test_all_missing(self):
        df = self._make_df([
            {"signal": None, "status": "data_missing"},
            {"signal": None, "status": "data_missing"},
        ])
        result = dashboard.compute_portfolio_summary(df)
        assert result["buy"] == 0
        assert result["sell"] == 0
        assert result["neutral"] == 0
        assert result["missing"] == 2


# ---------------------------------------------------------------------------
# calculate_position_size
# ---------------------------------------------------------------------------

class TestCalculatePositionSize:
    def test_known_value(self):
        # capital=10000, risk_pct=1, stop_distance=10 → risk=100, size=10 units
        result = dashboard.calculate_position_size(10_000.0, 1.0, 10.0, 1900.0)
        assert result["available"] is True
        assert result["position_size_units"] == 10
        assert result["gbp_risk"] == pytest.approx(100.0)

    def test_zero_stop_distance_returns_unavailable(self):
        result = dashboard.calculate_position_size(10_000.0, 1.0, 0.0, 1900.0)
        assert result["available"] is False
        assert result["position_size_units"] == 0

    def test_negative_stop_distance_returns_unavailable(self):
        result = dashboard.calculate_position_size(10_000.0, 1.0, -5.0, 1900.0)
        assert result["available"] is False

    def test_floor_truncation(self):
        # capital=10000, risk=100, stop_dist=3 → 33.33 → floor → 33
        result = dashboard.calculate_position_size(10_000.0, 1.0, 3.0, 1900.0)
        assert result["position_size_units"] == 33


# ---------------------------------------------------------------------------
# compute_correlation_warnings
# ---------------------------------------------------------------------------

class TestComputeCorrelationWarnings:
    def _make_snapshot(self, rows):
        return pd.DataFrame(rows)

    def test_empty_snapshot_returns_empty(self):
        df = pd.DataFrame(columns=["symbol", "signal"])
        result = dashboard.compute_correlation_warnings(df, Path("/nonexistent"))
        assert result == []

    def test_flat_signals_excluded(self):
        df = self._make_snapshot([
            {"symbol": "GC=F", "signal": 0},
            {"symbol": "SI=F", "signal": 0},
        ])
        result = dashboard.compute_correlation_warnings(df, Path("/nonexistent"))
        assert result == []

    def test_opposite_signals_no_warning(self, tmp_path):
        """Pairs with opposite signals are not co-directional — no warning."""
        for sym, prices in [("GC=F", range(100, 160)), ("SI=F", range(100, 160))]:
            df = pd.DataFrame({"close": list(prices)})
            (tmp_path / f"{sym.lower()}_1d_yfinance.parquet").write_bytes(
                df.to_parquet(index=False)
            )
        snapshot = self._make_snapshot([
            {"symbol": "GC=F", "signal": 1},
            {"symbol": "SI=F", "signal": -1},
        ])
        result = dashboard.compute_correlation_warnings(snapshot, tmp_path)
        assert result == []

    def test_correlated_same_direction_triggers_warning(self, tmp_path):
        """Two instruments with r > 0.7 and same signal direction → warning."""
        import numpy as np
        np.random.seed(0)
        prices = 100 + np.cumsum(np.random.randn(60))
        for sym in ["GC=F", "SI=F"]:
            df = pd.DataFrame({"close": prices + np.random.randn(60) * 0.01})
            (tmp_path / f"{sym.lower()}_1d_yfinance.parquet").write_bytes(
                df.to_parquet(index=False)
            )
        snapshot = self._make_snapshot([
            {"symbol": "GC=F", "signal": 1},
            {"symbol": "SI=F", "signal": 1},
        ])
        result = dashboard.compute_correlation_warnings(snapshot, tmp_path)
        assert len(result) == 1
        assert result[0]["symbol_a"] == "GC=F"
        assert result[0]["symbol_b"] == "SI=F"
        assert result[0]["correlation"] > 0.7
