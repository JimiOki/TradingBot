"""Trade Journal page — full execution history view with filters and performance stats."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trading_lab.paths import SIGNALS_DATA_DIR

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

EXECUTION_LOG_PATH = SIGNALS_DATA_DIR / "execution_log.parquet"


def load_execution_log() -> pd.DataFrame | None:
    """Load the full execution log. Returns None if file absent or empty."""
    if not EXECUTION_LOG_PATH.exists():
        return None
    try:
        df = pd.read_parquet(EXECUTION_LOG_PATH)
        if df.empty:
            return None
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("Trade Journal")

    df = load_execution_log()

    if df is None:
        st.info("No execution history yet. Run execute_trades.py to start logging.")
        return

    # ------------------------------------------------------------------
    # Filters (sidebar)
    # ------------------------------------------------------------------
    st.sidebar.header("Filters")

    # Date range
    min_date = df["timestamp"].min().date()
    max_date = df["timestamp"].max().date()
    default_start = max(min_date, max_date - pd.Timedelta(days=7))

    date_range = st.sidebar.date_input(
        "Date range",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    # Handle single-date selection gracefully
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = date_range[0] if isinstance(date_range, tuple) else date_range
        end_date = max_date

    # Symbol multiselect
    all_symbols = sorted(df["symbol"].dropna().unique().tolist())
    selected_symbols = st.sidebar.multiselect(
        "Symbols", options=all_symbols, default=all_symbols
    )

    # Action filter
    all_actions = sorted(df["action"].dropna().unique().tolist())
    default_actions = [a for a in ["PLACED", "HELD", "ADJUSTED", "CLOSED", "SKIPPED", "FAILED"] if a in all_actions]
    if not default_actions:
        default_actions = all_actions
    selected_actions = st.sidebar.multiselect(
        "Actions", options=all_actions, default=default_actions
    )

    # ------------------------------------------------------------------
    # Apply filters
    # ------------------------------------------------------------------
    filtered = df[
        (df["timestamp"].dt.date >= start_date)
        & (df["timestamp"].dt.date <= end_date)
        & (df["symbol"].isin(selected_symbols))
        & (df["action"].isin(selected_actions))
    ].copy()

    if filtered.empty:
        st.info("No trades match the current filters.")
        return

    # ------------------------------------------------------------------
    # Performance Stats
    # ------------------------------------------------------------------
    placed = filtered[filtered["action"] == "PLACED"]
    closed = filtered[filtered["action"] == "CLOSED"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Placed", len(placed))
    col2.metric("Closed Trades", len(closed))

    if len(closed) > 0 and "unrealised_pnl" in closed.columns:
        wins = closed["unrealised_pnl"].dropna()
        win_count = (wins > 0).sum()
        win_rate = f"{(win_count / len(wins) * 100):.1f}%" if len(wins) > 0 else "N/A"
        net_pnl = wins.sum()
    else:
        win_rate = "N/A"
        net_pnl = 0.0

    col3.metric("Win Rate", win_rate)
    col4.metric("Net P&L", f"{net_pnl:+.2f}")

    st.divider()

    # ------------------------------------------------------------------
    # P&L Chart (cumulative, CLOSED trades only)
    # ------------------------------------------------------------------
    if len(closed) > 0 and "unrealised_pnl" in closed.columns:
        st.subheader("Cumulative P&L")
        pnl_series = (
            closed[["timestamp", "unrealised_pnl"]]
            .dropna(subset=["unrealised_pnl"])
            .sort_values("timestamp")
            .copy()
        )
        if not pnl_series.empty:
            pnl_series["cumulative_pnl"] = pnl_series["unrealised_pnl"].cumsum()
            chart_data = pnl_series.set_index("timestamp")[["cumulative_pnl"]]
            st.area_chart(chart_data)

        st.divider()

    # ------------------------------------------------------------------
    # Session Breakdown
    # ------------------------------------------------------------------
    if "session" in filtered.columns:
        st.subheader("Session Breakdown")
        session_counts = filtered["session"].value_counts()
        sessions = ["00:00", "07:00", "13:30", "manual"]
        cols = st.columns(len(sessions))
        for i, sess in enumerate(sessions):
            count = int(session_counts.get(sess, 0))
            cols[i].metric(sess, count)

        st.divider()

    # ------------------------------------------------------------------
    # Full History Table
    # ------------------------------------------------------------------
    st.subheader("Full History")

    display_cols = [
        "timestamp", "session", "symbol", "action", "direction",
        "entry_level", "current_price", "unrealised_pnl",
        "llm_recommendation", "rationale",
    ]
    available_cols = [c for c in display_cols if c in filtered.columns]

    table_data = filtered[available_cols].sort_values("timestamp", ascending=False)
    st.dataframe(table_data, use_container_width=True, height=500)


main()
