"""Backtests page — IS/OOS strategy validation and multi-instrument comparison.

Requirements covered:
  REQ-VAL-004  In-sample backtest with parameter locking
  REQ-VAL-005  Out-of-sample threshold validation
  REQ-OPS-005  Backtest comparison across multiple instruments
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trading_lab.backtesting.engine import run_backtest
from trading_lab.backtesting.metrics import compute_all
from trading_lab.backtesting.models import BacktestConfig, BacktestResult
from trading_lab.backtesting.validation import (
    compute_performance_degradation,
    split_in_sample_out_of_sample,
    validate_oos_thresholds,
)
from trading_lab.config.loader import load_instruments
from trading_lab.paths import CURATED_DATA_DIR, INSTRUMENTS_CONFIG, STRATEGIES_CONFIG_DIR
from trading_lab.strategies.loader import load_strategy

OVERFITTING_DEGRADATION_THRESHOLD = 50.0  # %


def _load_instruments() -> list[dict]:
    try:
        return load_instruments(INSTRUMENTS_CONFIG)
    except Exception:
        return []


def _load_strategy_configs() -> list[Path]:
    if not STRATEGIES_CONFIG_DIR.exists():
        return []
    return sorted(STRATEGIES_CONFIG_DIR.glob("*.yaml"))


def _load_curated(symbol: str) -> pd.DataFrame | None:
    matches = list(CURATED_DATA_DIR.glob(f"{symbol.lower()}_*.parquet"))
    if not matches:
        return None
    try:
        df = pd.read_parquet(matches[0])
        if not isinstance(df.index, pd.DatetimeIndex):
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")
        return df
    except Exception:
        return None


def _run_single_backtest(
    symbol: str,
    strategy_path: Path,
    bars: pd.DataFrame,
    mode: str = "full",
) -> tuple[dict, pd.DataFrame] | None:
    try:
        strategy = load_strategy(strategy_path)
        signals = strategy.generate_signals(bars)
        config = BacktestConfig(symbol=symbol, strategy_name=strategy_path.stem, mode=mode)
        result = run_backtest(signals, config)
        metrics = compute_all(result)
        return metrics, result.signals_df
    except Exception as exc:
        st.error(f"Backtest failed for {symbol}: {exc}")
        return None


def _equity_chart(signals_df: pd.DataFrame, title: str, is_split_idx: int | None = None) -> go.Figure:
    df = signals_df.dropna(subset=["equity"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["equity"], mode="lines", name="Equity",
                              line={"color": "royalblue"}))
    if is_split_idx is not None and 0 < is_split_idx < len(df):
        split_date = df.index[is_split_idx]
        fig.add_vrect(x0=df.index[0], x1=split_date,
                      fillcolor="rgba(0,200,100,0.07)", line_width=0,
                      annotation_text="In-Sample", annotation_position="top left")
        fig.add_vrect(x0=split_date, x1=df.index[-1],
                      fillcolor="rgba(255,100,0,0.07)", line_width=0,
                      annotation_text="Out-of-Sample", annotation_position="top right")
    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Equity (£)", height=350)
    return fig


def _metrics_row(metrics: dict) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Return", f"{metrics.get('total_return_pct', 0):.1f}%")
    c2.metric("CAGR", f"{metrics.get('cagr_pct', 0):.1f}%")
    c3.metric("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}")
    c4.metric("Max DD", f"{metrics.get('max_drawdown_pct', 0):.1f}%")
    c5.metric("Win Rate", f"{metrics.get('win_rate_pct', 0):.1f}%")


def _render_validation_tab(instruments: list[dict], strategy_paths: list[Path]) -> None:
    st.subheader("Strategy Validation (IS/OOS)")

    if not instruments:
        st.warning("No instruments found in instruments.yaml.")
        return
    if not strategy_paths:
        st.warning(f"No strategy YAML files found in {STRATEGIES_CONFIG_DIR}.")
        return

    symbol_options = [i["symbol"] for i in instruments]
    col1, col2, col3 = st.columns(3)
    symbol = col1.selectbox("Instrument", symbol_options, key="val_symbol")
    strategy_path = col2.selectbox("Strategy", strategy_paths,
                                    format_func=lambda p: p.stem, key="val_strategy")
    oos_ratio = col3.slider("OOS ratio", 0.1, 0.5, 0.3, 0.05, key="val_oos")

    bars = _load_curated(symbol)
    if bars is None:
        st.warning(f"No curated data found for {symbol}. Run data ingest first.")
        return

    st.caption(f"Loaded {len(bars)} bars for {symbol}.")

    try:
        is_bars, oos_bars = split_in_sample_out_of_sample(bars, oos_ratio=oos_ratio)
    except ValueError as exc:
        st.error(str(exc))
        return

    is_split_idx = len(is_bars)
    col_is, col_oos = st.columns(2)

    with col_is:
        st.markdown("**In-Sample**")
        st.caption(f"{is_bars.index[0].date()} → {is_bars.index[-1].date()} ({len(is_bars)} bars)")
        if st.button("Run In-Sample Backtest", key="run_is"):
            with st.spinner("Running in-sample backtest…"):
                out = _run_single_backtest(symbol, strategy_path, is_bars, mode="in_sample")
            if out:
                st.session_state["is_metrics"], st.session_state["is_signals"] = out
                st.success("In-sample complete.")
        if "is_metrics" in st.session_state:
            _metrics_row(st.session_state["is_metrics"])

    with col_oos:
        st.markdown("**Out-of-Sample**")
        st.caption(f"{oos_bars.index[0].date()} → {oos_bars.index[-1].date()} ({len(oos_bars)} bars)")
        oos_blocked = "is_metrics" not in st.session_state
        if st.button("Run Out-of-Sample Backtest", key="run_oos", disabled=oos_blocked):
            with st.spinner("Running out-of-sample backtest…"):
                out = _run_single_backtest(symbol, strategy_path, oos_bars, mode="out_of_sample")
            if out:
                st.session_state["oos_metrics"], st.session_state["oos_signals"] = out
                st.success("Out-of-sample complete.")
        if oos_blocked:
            st.caption("_Run in-sample first._")
        if "oos_metrics" in st.session_state:
            _metrics_row(st.session_state["oos_metrics"])

    if "is_metrics" in st.session_state and "oos_metrics" in st.session_state:
        st.divider()
        is_cfg = BacktestConfig(symbol=symbol, strategy_name=strategy_path.stem, mode="in_sample")
        oos_cfg = BacktestConfig(symbol=symbol, strategy_name=strategy_path.stem, mode="out_of_sample")
        is_result = BacktestResult(signals_df=st.session_state["is_signals"], config=is_cfg)
        oos_result = BacktestResult(signals_df=st.session_state["oos_signals"], config=oos_cfg)

        vr = validate_oos_thresholds(oos_result)
        degradation = compute_performance_degradation(is_result, oos_result)

        if vr.approved:
            st.success("✅ APPROVED FOR PAPER TRADING")
        else:
            st.error(f"❌ NOT APPROVED — {vr.reason}")

        if degradation is not None:
            if degradation > OVERFITTING_DEGRADATION_THRESHOLD:
                st.warning(f"⚠️ Performance degradation {degradation:.1f}% — possible overfitting")
            else:
                st.info(f"Performance degradation: {degradation:.1f}%")

        is_m = st.session_state["is_metrics"]
        oos_m = st.session_state["oos_metrics"]
        c1, c2 = st.columns(2)
        c1.metric("IS Sharpe", f"{is_m.get('sharpe_ratio', 0):.2f}")
        c2.metric("OOS Sharpe", f"{oos_m.get('sharpe_ratio', 0):.2f}",
                  delta=f"{oos_m.get('sharpe_ratio', 0) - is_m.get('sharpe_ratio', 0):.2f}")

        combined = pd.concat([st.session_state["is_signals"], st.session_state["oos_signals"]])
        st.plotly_chart(_equity_chart(combined, f"{symbol} — IS/OOS Equity Curve", is_split_idx),
                        use_container_width=True)


def _render_comparison_tab(instruments: list[dict], strategy_paths: list[Path]) -> None:
    st.subheader("Compare Instruments")

    if not instruments or not strategy_paths:
        st.warning("No instruments or strategies configured.")
        return

    symbol_options = [i["symbol"] for i in instruments]
    col1, col2 = st.columns(2)
    selected_symbols = col1.multiselect("Select instruments", symbol_options,
                                         default=symbol_options[:2], key="cmp_symbols")
    strategy_path = col2.selectbox("Strategy", strategy_paths,
                                    format_func=lambda p: p.stem, key="cmp_strategy")

    if len(selected_symbols) < 2:
        st.info("Select at least 2 instruments to compare.")
        return

    if st.button("Run Comparison", type="primary", key="run_cmp"):
        rows = []
        equity_curves = {}
        progress = st.progress(0)
        for idx, sym in enumerate(selected_symbols):
            bars = _load_curated(sym)
            if bars is None:
                rows.append({"Symbol": sym, "error": "No data"})
                continue
            out = _run_single_backtest(sym, strategy_path, bars)
            if out:
                m, signals = out
                rows.append({
                    "Symbol": sym,
                    "Total Return %": round(m.get("total_return_pct", 0), 1),
                    "CAGR %": round(m.get("cagr_pct", 0), 1),
                    "Sharpe": round(m.get("sharpe_ratio", 0), 2),
                    "Max DD %": round(m.get("max_drawdown_pct", 0), 1),
                    "Win Rate %": round(m.get("win_rate_pct", 0), 1),
                })
                equity_curves[sym] = signals
            progress.progress((idx + 1) / len(selected_symbols))

        st.session_state["cmp_rows"] = rows
        st.session_state["cmp_equity"] = equity_curves

    if "cmp_rows" in st.session_state and st.session_state["cmp_rows"]:
        results_df = pd.DataFrame(st.session_state["cmp_rows"])
        st.dataframe(results_df, use_container_width=True)

        if "Sharpe" in results_df.columns:
            best_sym = results_df.loc[results_df["Sharpe"].idxmax(), "Symbol"]
            st.success(f"Best performer by Sharpe: **{best_sym}**")

        for sym, signals in st.session_state.get("cmp_equity", {}).items():
            with st.expander(f"{sym} — equity curve"):
                st.plotly_chart(_equity_chart(signals, f"{sym} equity"), use_container_width=True)


def main() -> None:
    st.title("Backtests")
    instruments = _load_instruments()
    strategy_paths = _load_strategy_configs()
    tab1, tab2 = st.tabs(["Strategy Validation", "Compare Instruments"])
    with tab1:
        _render_validation_tab(instruments, strategy_paths)
    with tab2:
        _render_comparison_tab(instruments, strategy_paths)


main()
