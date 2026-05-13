"""Charts page — OHLC candlestick, SMA/RSI/MACD overlays, signal markers.

Requirements covered:
  REQ-UI-004  symbol-selector dropdown and lookback period control
  REQ-UI-005  signal entry/exit markers on price chart
  REQ-CTX-003 indicator overlays: fast SMA, slow SMA, RSI, MACD
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trading_lab.features.indicators import macd as compute_macd
from trading_lab.paths import CURATED_DATA_DIR, INSTRUMENTS_CONFIG, STRATEGIES_CONFIG_DIR
from trading_lab.strategies.loader import load_strategy

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOOKBACK_OPTIONS = ["3M", "6M", "1Y", "2Y", "All"]
DEFAULT_LOOKBACK = "1Y"
DEFAULT_STRATEGY = STRATEGIES_CONFIG_DIR / "sma_cross.yaml"

# ---------------------------------------------------------------------------
# Pure functions (tested in tests/test_charts_logic.py)
# ---------------------------------------------------------------------------


def load_instruments(config_path: Path) -> list[dict]:
    """Load instrument list from instruments.yaml."""
    with open(config_path) as f:
        return yaml.safe_load(f).get("instruments", [])


def curated_path(symbol: str, timeframe: str, source: str) -> Path:
    """Return curated parquet path for an instrument."""
    return CURATED_DATA_DIR / f"{symbol.lower()}_{timeframe}_{source}.parquet"


def load_curated_bars(symbol: str, timeframe: str, source: str) -> pd.DataFrame | None:
    """Load curated OHLCV bars from disk. Returns None if file absent."""
    path = curated_path(symbol, timeframe, source)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def apply_lookback(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Slice df to the requested lookback period. 'All' returns df unchanged."""
    if df is None or df.empty or period == "All":
        return df
    offsets = {
        "3M": pd.DateOffset(months=3),
        "6M": pd.DateOffset(months=6),
        "1Y": pd.DateOffset(years=1),
        "2Y": pd.DateOffset(years=2),
    }
    cutoff = pd.Timestamp.now(tz="UTC") - offsets[period]
    return df[df.index >= cutoff]


def build_chart(
    df: pd.DataFrame,
    symbol: str,
    name: str,
    rsi_overbought: float = 70.0,
    rsi_oversold: float = 30.0,
) -> go.Figure:
    """Build a three-panel Plotly chart: price+SMAs+signals | RSI | MACD.

    df must contain: open, high, low, close.
    Optional columns used when present: fast_sma, slow_sma, rsi, signal,
    position_change, stop_loss_level, take_profit_level,
    macd_line, signal_line, histogram.
    """
    has_macd = "macd_line" in df.columns

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.60, 0.20, 0.20],
        vertical_spacing=0.03,
        subplot_titles=(f"{symbol} — {name}", "RSI", "MACD"),
    )

    x = df.index

    # --- Row 1: Candlestick ---
    fig.add_trace(
        go.Candlestick(
            x=x,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    # --- Row 1: SMAs ---
    if "fast_sma" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["fast_sma"],
                name="Fast SMA",
                line=dict(color="#f59e0b", width=1.5),
            ),
            row=1,
            col=1,
        )
    if "slow_sma" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["slow_sma"],
                name="Slow SMA",
                line=dict(color="#818cf8", width=1.5),
            ),
            row=1,
            col=1,
        )

    # --- Row 1: Signal entry/exit markers ---
    if "position_change" in df.columns and "signal" in df.columns:
        long_entries = df[(df["position_change"] > 0) & (df["signal"] == 1)]
        if not long_entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=long_entries.index,
                    y=long_entries["low"] * 0.998,
                    mode="markers",
                    name="Buy",
                    marker=dict(
                        symbol="triangle-up",
                        color="#22c55e",
                        size=12,
                        line=dict(width=1, color="#15803d"),
                    ),
                ),
                row=1,
                col=1,
            )

        short_entries = df[(df["position_change"] < 0) & (df["signal"] == -1)]
        if not short_entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=short_entries.index,
                    y=short_entries["high"] * 1.002,
                    mode="markers",
                    name="Sell",
                    marker=dict(
                        symbol="triangle-down",
                        color="#ef4444",
                        size=12,
                        line=dict(width=1, color="#b91c1c"),
                    ),
                ),
                row=1,
                col=1,
            )

        exits = df[(df["position_change"] != 0) & (df["signal"] == 0)]
        if not exits.empty:
            fig.add_trace(
                go.Scatter(
                    x=exits.index,
                    y=exits["close"],
                    mode="markers",
                    name="Exit",
                    marker=dict(symbol="x", color="#94a3b8", size=10),
                ),
                row=1,
                col=1,
            )

    # --- Row 1: Stop loss / take profit for current active signal ---
    last = df.iloc[-1]
    last_signal = last.get("signal")
    if pd.notna(last_signal) and int(last_signal) in (1, -1):
        sl = last.get("stop_loss_level")
        tp = last.get("take_profit_level")
        x_start = df.index[max(0, len(df) - 30)]
        x_end = df.index[-1]
        for level, label, color in [
            (sl, "Stop Loss", "#ef4444"),
            (tp, "Take Profit", "#22c55e"),
        ]:
            if level is not None and pd.notna(level):
                fig.add_shape(
                    type="line",
                    x0=x_start,
                    x1=x_end,
                    y0=level,
                    y1=level,
                    line=dict(color=color, width=1, dash="dash"),
                    row=1,
                    col=1,
                )
                fig.add_annotation(
                    x=x_end,
                    y=level,
                    text=f"  {label}: {level:.4f}",
                    showarrow=False,
                    xanchor="left",
                    font=dict(color=color, size=10),
                    row=1,
                    col=1,
                )

    # --- Row 2: RSI ---
    if "rsi" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["rsi"],
                name="RSI",
                line=dict(color="#a78bfa", width=1.5),
            ),
            row=2,
            col=1,
        )
        fig.add_hrect(
            y0=rsi_overbought,
            y1=100,
            fillcolor="rgba(239,68,68,0.10)",
            line_width=0,
            row=2,
            col=1,
        )
        fig.add_hrect(
            y0=0,
            y1=rsi_oversold,
            fillcolor="rgba(34,197,94,0.10)",
            line_width=0,
            row=2,
            col=1,
        )
        for level, color in [
            (rsi_overbought, "#ef4444"),
            (rsi_oversold, "#22c55e"),
            (50, "#64748b"),
        ]:
            fig.add_hline(
                y=level,
                line=dict(color=color, width=0.8, dash="dot"),
                row=2,
                col=1,
            )

    # --- Row 3: MACD ---
    if has_macd:
        hist_colors = [
            "#22c55e" if v >= 0 else "#ef4444"
            for v in df["histogram"].fillna(0)
        ]
        fig.add_trace(
            go.Bar(
                x=x,
                y=df["histogram"],
                name="Histogram",
                marker_color=hist_colors,
                opacity=0.6,
                showlegend=False,
            ),
            row=3,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["macd_line"],
                name="MACD",
                line=dict(color="#60a5fa", width=1.5),
            ),
            row=3,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["signal_line"],
                name="Signal",
                line=dict(color="#f59e0b", width=1.5),
            ),
            row=3,
            col=1,
        )

    # --- Layout ---
    fig.update_layout(
        template="plotly_dark",
        height=700,
        margin=dict(l=50, r=100, t=40, b=20),
        legend=dict(orientation="h", y=1.02, x=0),
        xaxis_rangeslider_visible=False,
    )
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")

    return fig


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("Charts")

    # Load instruments
    try:
        instruments = load_instruments(INSTRUMENTS_CONFIG)
    except Exception as exc:
        st.error(f"Could not load instruments config: {exc}")
        return

    if not instruments:
        st.warning("No instruments configured.")
        return

    # Controls
    col_sym, col_period = st.columns([3, 1])
    options = {
        f"{i['symbol']} — {i.get('name', i['symbol'])}": i for i in instruments
    }
    selected_label = col_sym.selectbox("Instrument", list(options.keys()))
    period = col_period.selectbox(
        "Lookback", LOOKBACK_OPTIONS, index=LOOKBACK_OPTIONS.index(DEFAULT_LOOKBACK)
    )

    instrument = options[selected_label]
    symbol = instrument["symbol"]
    name = instrument.get("name", symbol)
    timeframe = instrument.get("timeframe", "1d")
    source = instrument.get("source", "yfinance")

    # Load curated bars
    bars = load_curated_bars(symbol, timeframe, source)
    if bars is None:
        st.warning(
            f"No curated data found for **{symbol}**. "
            "Run **Refresh Data** on the Dashboard first."
        )
        return

    # Load strategy
    try:
        strategy = load_strategy(DEFAULT_STRATEGY)
    except Exception as exc:
        st.error(f"Could not load strategy config: {exc}")
        return

    # Generate signals
    with st.spinner("Computing indicators…"):
        try:
            df = strategy.generate_signals(bars)
        except Exception as exc:
            st.error(f"Signal generation failed: {exc}")
            return

    # Add MACD columns
    macd_df = compute_macd(df["close"])
    df = df.join(macd_df)

    # Apply lookback slice
    df_sliced = apply_lookback(df, period)
    if df_sliced is None or df_sliced.empty:
        st.warning(f"No data in the selected lookback period ({period}).")
        return

    # Render chart
    rsi_overbought = getattr(strategy, "rsi_overbought", 70.0)
    rsi_oversold = getattr(strategy, "rsi_oversold", 30.0)
    fig = build_chart(
        df_sliced,
        symbol,
        name,
        rsi_overbought=rsi_overbought,
        rsi_oversold=rsi_oversold,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Summary metrics below chart (use full df for last-bar values)
    last = df.iloc[-1]

    last_signal = last.get("signal")
    signal_int = int(last_signal) if pd.notna(last_signal) else 0
    signal_text = {1: "LONG", -1: "SHORT", 0: "Flat"}.get(signal_int, "Flat")

    last_rsi = last.get("rsi")
    rsi_str = f"{last_rsi:.1f}" if pd.notna(last_rsi) else "—"

    last_macd = last.get("macd_line")
    macd_str = f"{last_macd:.4f}" if pd.notna(last_macd) else "—"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last Close", f"{last['close']:.4f}")
    c2.metric("RSI", rsi_str)
    c3.metric("Signal", signal_text)
    c4.metric("MACD", macd_str)


main()
