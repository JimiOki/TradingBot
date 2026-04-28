"""Dashboard page — signal overview, portfolio summary, and data refresh.

Requirements covered:
  REQ-UI-001  navigation / sidebar last-refresh timestamp
  REQ-UI-002  signal table with colour indicators
  REQ-UI-003  data refresh trigger with progress and concurrent-run guard
  REQ-UI-006  portfolio summary panel
  REQ-UI-008  graceful handling of missing/stale data
  REQ-OPS-002 data freshness indicator (24-hour staleness warning)
  REQ-CTX-003 signal age indicator and STALE badge (≥ 5 days)
  REQ-QUAL-001 confidence score display
  REQ-QUAL-002 signal strength % display
  REQ-QUAL-003 conflicting indicators warning
  REQ-QUAL-004 HIGH VOLATILITY badge
  REQ-SL-003  stop loss and take profit columns
  REQ-LLM-007 LLM explanation display (cache-read only; fallback if absent)
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trading_lab.paths import CURATED_DATA_DIR, EXPLANATIONS_DIR, SIGNAL_NEWS_DIR, SIGNALS_DATA_DIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SNAPSHOT_PATH = SIGNALS_DATA_DIR / "portfolio_snapshot.parquet"
STALE_SIGNAL_DAYS = 5       # REQ-CTX-003: signals older than this are STALE
STALE_DATA_HOURS = 24       # REQ-OPS-002: data older than this gets amber warning
EXPLANATION_UNAVAILABLE = "Explanation unavailable."  # REQ-LLM-004

# ---------------------------------------------------------------------------
# Pure functions (side-effect-free; tested in tests/test_dashboard_logic.py)
# ---------------------------------------------------------------------------

def get_signal_label(signal) -> str:
    """Map signal integer to human-readable label."""
    if signal is None or (isinstance(signal, float) and pd.isna(signal)):
        return "Data Missing"
    val = int(signal)
    return {1: "Buy", -1: "Sell", 0: "Neutral"}.get(val, "Data Missing")


def get_signal_age_days(timestamp) -> int | None:
    """Days between timestamp and today (UTC). None if timestamp is None/NaT."""
    if timestamp is None or (isinstance(timestamp, float) and pd.isna(timestamp)):
        return None
    try:
        ts = pd.Timestamp(timestamp)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        delta = datetime.now(timezone.utc).date() - ts.date()
        return delta.days
    except Exception:
        return None


def is_data_stale(timestamp, threshold_hours: int = STALE_DATA_HOURS) -> bool:
    """True if timestamp is more than 2 business days old, or if None.

    Uses business-day counting so weekend gaps (e.g. Friday → Monday) don't
    trigger a false staleness warning. threshold_hours is kept as a parameter
    for backwards compatibility but is no longer the primary check.
    """
    if timestamp is None or (isinstance(timestamp, float) and pd.isna(timestamp)):
        return True
    try:
        ts = pd.Timestamp(timestamp)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        today = pd.Timestamp(datetime.now(timezone.utc).date())
        bar_date = pd.Timestamp(ts.date())
        # Count how many business days (Mon–Fri) have elapsed since the bar date.
        bdays = len(pd.bdate_range(bar_date, today)) - 1  # -1: range is inclusive
        return bdays > 2
    except Exception:
        return True


def compute_portfolio_summary(df: pd.DataFrame) -> dict:
    """Count buy/sell/neutral/missing based on LLM decisions, not raw technical signals."""
    if df is None or df.empty:
        return {"buy": 0, "sell": 0, "neutral": 0, "missing": 0}
    missing = int((df["status"] == "data_missing").sum())
    active = df[df["status"] == "ok"]
    buy = 0
    sell = 0
    neutral = 0
    for _, row in active.iterrows():
        symbol = row.get("symbol", "")
        ts = row.get("timestamp_of_last_bar")
        if ts is None:
            neutral += 1
            continue
        signal_date = pd.Timestamp(ts).date()
        decision = load_decision(symbol, str(signal_date))
        if decision and decision.get("llm_recommendation") == "GO":
            direction = decision.get("direction", "")
            if direction == "LONG":
                buy += 1
            elif direction == "SHORT":
                sell += 1
            else:
                neutral += 1
        else:
            neutral += 1
    return {
        "buy": buy,
        "sell": sell,
        "neutral": neutral,
        "missing": missing,
    }


def load_snapshot() -> pd.DataFrame | None:
    """Read the portfolio snapshot from disk. Returns None if file absent."""
    if not SNAPSHOT_PATH.exists():
        return None
    df = pd.read_parquet(SNAPSHOT_PATH)
    return df


def load_explanation(symbol: str, date_str: str) -> str:
    """Read cached LLM explanation for a symbol+date. Returns fallback if absent/corrupt."""
    path = EXPLANATIONS_DIR / f"{symbol}_{date_str}.json"
    if not path.exists():
        return EXPLANATION_UNAVAILABLE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("explanation", EXPLANATION_UNAVAILABLE) or EXPLANATION_UNAVAILABLE
    except Exception:
        return EXPLANATION_UNAVAILABLE


# --- Correlation warning threshold (REQ-RISK-003) ---
CORRELATION_WARNING_THRESHOLD = 0.7
CORRELATION_LOOKBACK_BARS = 60


def load_news(symbol: str, date_str: str) -> list[dict]:
    """Read persisted news headlines for a symbol+date. Returns [] if absent."""
    path = SIGNAL_NEWS_DIR / f"{symbol}_{date_str}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def load_decision(symbol: str, date_str: str) -> dict | None:
    """Read cached LLM decision for a symbol+date. Returns None if absent/corrupt."""
    from trading_lab.paths import DATA_DIR
    path = DATA_DIR / "signals" / "decisions" / f"{symbol}_{date_str}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return None


def load_session_status(symbol: str, date_str: str) -> bool | None:
    """Read session_open from a persisted MarketContext JSON. Returns None if absent."""
    path = SIGNALS_DATA_DIR / f"market_context_{symbol}_{date_str}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        val = data.get("session_open")
        return bool(val) if val is not None else None
    except Exception:
        return None


def calculate_position_size(
    capital: float,
    risk_pct: float,
    stop_distance: float,
    close_price: float,
) -> dict:
    """Calculate position size based on capital, risk %, and stop distance.

    REQ-RISK-004: position sizing calculator.

    Returns:
        Dict with keys: position_size_units (int), gbp_risk (float), available (bool).
        If stop_distance <= 0: available=False, position_size_units=0, gbp_risk=0.
    """
    if stop_distance <= 0 or close_price <= 0:
        return {"position_size_units": 0, "gbp_risk": 0.0, "available": False}
    gbp_risk = capital * (risk_pct / 100)
    size = gbp_risk / stop_distance
    return {
        "position_size_units": int(size),
        "gbp_risk": round(gbp_risk, 2),
        "available": True,
    }


def compute_correlation_warnings(
    snapshot_df: pd.DataFrame,
    curated_dir: Path,
    lookback: int = CORRELATION_LOOKBACK_BARS,
    threshold: float = CORRELATION_WARNING_THRESHOLD,
) -> list[dict]:
    """Find instrument pairs with high close-price correlation and co-directional signals.

    REQ-RISK-003: Warn when correlation > threshold and both signals same direction.
    """
    if snapshot_df is None or snapshot_df.empty:
        return []

    active = snapshot_df[snapshot_df["signal"].isin([1, -1])].copy()
    if len(active) < 2:
        return []

    close_series: dict[str, pd.Series] = {}
    for _, row in active.iterrows():
        symbol = row["symbol"]
        matches = list(curated_dir.glob(f"{symbol.lower()}_*.parquet"))
        if not matches:
            continue
        try:
            df = pd.read_parquet(matches[0])
            if "close" in df.columns and len(df) >= lookback:
                close_series[symbol] = df["close"].iloc[-lookback:].reset_index(drop=True)
        except Exception:
            continue

    if len(close_series) < 2:
        return []

    warnings_list = []
    symbols = list(close_series.keys())
    signal_map = dict(zip(active["symbol"], active["signal"]))

    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            sym_a, sym_b = symbols[i], symbols[j]
            sig_a = signal_map.get(sym_a)
            sig_b = signal_map.get(sym_b)
            if sig_a != sig_b:
                continue
            try:
                corr = float(close_series[sym_a].corr(close_series[sym_b]))
            except Exception:
                continue
            if corr > threshold:
                direction = "BUY" if sig_a == 1 else "SELL"
                warnings_list.append({
                    "symbol_a": sym_a,
                    "symbol_b": sym_b,
                    "correlation": round(corr, 3),
                    "signal": int(sig_a),
                    "message": (
                        f"{sym_a} and {sym_b} are {corr:.0%} correlated "
                        f"and both show {direction} signals — concentration risk."
                    ),
                })

    return warnings_list


# ---------------------------------------------------------------------------
# Refresh logic
# ---------------------------------------------------------------------------

def _run_refresh() -> tuple[int, int, list[str]]:
    """Run ingest + signal scripts. Returns (ok_count, fail_count, failed_symbols)."""
    scripts = [
        [sys.executable, str(ROOT / "scripts" / "ingest_market_data.py")],
        [sys.executable, str(ROOT / "scripts" / "run_signals.py")],
    ]
    failed: list[str] = []
    for cmd in scripts:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            failed.append(Path(cmd[1]).name)

    if not failed:
        snapshot = load_snapshot()
        if snapshot is not None:
            ok = int((snapshot["status"] == "ok").sum())
            bad = int((snapshot["status"] != "ok").sum())
        else:
            ok, bad = 0, 0
    else:
        ok, bad = 0, len(failed)
    return ok, bad, failed


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _signal_colour(label: str) -> str:
    return {"Buy": "green", "Sell": "red", "Neutral": "grey", "Data Missing": "grey"}.get(label, "grey")


def _fmt_price(val, decimals: int = 4) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    return f"{float(val):.{decimals}f}"


def _fmt_pct(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    return f"{float(val):.2f}%"


def _render_portfolio_summary(summary: dict) -> None:
    """REQ-UI-006: portfolio counts panel."""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Buy signals", summary["buy"])
    col2.metric("Sell signals", summary["sell"])
    col3.metric("Neutral", summary["neutral"])
    col4.metric("Data missing", summary["missing"])


def _render_refresh_section() -> None:
    """REQ-UI-003: refresh button with progress and concurrent-run guard."""
    if st.session_state.get("refresh_running", False):
        st.button("Refresh Data", disabled=True, help="Refresh already in progress.")
        st.info("Refresh in progress — please wait.")
        return

    if st.button("Refresh Data", type="primary"):
        st.session_state["refresh_running"] = True
        with st.spinner("Refreshing market data and regenerating signals…"):
            ok, bad, failed = _run_refresh()
        st.session_state["refresh_running"] = False

        if bad == 0:
            st.session_state["last_refresh"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
            st.success(f"Refresh complete — {ok} instrument(s) updated.")
        else:
            st.warning(
                f"Refresh finished with errors — {ok} succeeded, {bad} failed."
                + (f" Failed: {failed}" if failed else "")
            )
        st.rerun()


def _render_signal_table(df: pd.DataFrame) -> None:
    """REQ-UI-002 + quality/risk overlays — main signal table."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for _, row in df.iterrows():
        symbol = row["symbol"]
        name = row.get("name", symbol)
        status = row.get("status", "ok")

        # Use LLM decision as the primary label, fall back to technical signal
        ts_for_label = row.get("timestamp_of_last_bar")
        label_date_str = (
            str(pd.Timestamp(ts_for_label).date())
            if ts_for_label is not None
            else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        _dec = load_decision(symbol, label_date_str)
        if _dec and _dec.get("llm_recommendation") == "GO":
            _dir = _dec.get("direction", "")
            label = "Buy" if _dir == "LONG" else "Sell" if _dir == "SHORT" else "Neutral"
        elif status == "data_missing":
            label = "Data Missing"
        else:
            label = "Neutral"
        colour = _signal_colour(label)

        # --- Signal age (REQ-CTX-003) ---
        age = get_signal_age_days(row.get("timestamp_of_last_bar"))
        age_str = f"{age} day(s)" if age is not None else "—"
        stale_badge = " 🔴 STALE" if (age is not None and age >= STALE_SIGNAL_DAYS) else ""

        # --- Data staleness (REQ-OPS-002) ---
        stale_data = is_data_stale(row.get("timestamp_of_last_bar"))
        staleness_warn = " ⚠️" if stale_data else ""

        # --- Session status (REQ-CTX-002) ---
        session_open = load_session_status(symbol, today_str)
        if session_open is True:
            session_badge = " :green[OPEN]"
        elif session_open is False:
            session_badge = " :grey[CLOSED]"
        else:
            session_badge = ""

        # --- Build header line ---
        header = (
            f"**{symbol}** — {name} &nbsp;|&nbsp; "
            f":{colour}[**{label}**]"
            f"{session_badge}"
            f"{stale_badge}"
            f"{staleness_warn}"
        )

        with st.expander(header, expanded=(label in ("Buy", "Sell"))):
            if status == "data_missing":
                st.warning("No curated data file found for this instrument.")
                continue

            # Row 1: price + indicators
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Last Price", _fmt_price(row.get("close")))
            c2.metric("Fast SMA", _fmt_price(row.get("fast_sma")))
            c3.metric("Slow SMA", _fmt_price(row.get("slow_sma")))
            c4.metric("RSI", _fmt_price(row.get("rsi"), decimals=1))
            c5.metric("Signal Age", age_str)

            # Row 2: stop/target (REQ-SL-003) + quality (REQ-QUAL-001/002)
            c6, c7, c8, c9, c10 = st.columns(5)
            c6.metric("Stop Loss", _fmt_price(row.get("stop_loss_level")))
            c7.metric("Take Profit", _fmt_price(row.get("take_profit_level")))
            rr = row.get("stop_distance")
            rr_str = "—" if (rr is None or (isinstance(rr, float) and pd.isna(rr))) else "2.0"
            c8.metric("R/R", rr_str)

            conf = row.get("confidence_score")
            conf_str = f"{int(conf)}%" if (conf is not None and not (isinstance(conf, float) and pd.isna(conf))) else "—"
            c9.metric("Confidence", conf_str)  # REQ-QUAL-001

            strength = row.get("signal_strength_pct")
            c10.metric("Strength", _fmt_pct(strength))  # REQ-QUAL-002

            # Conflict + volatility badges (REQ-QUAL-003, REQ-QUAL-004)
            badges: list[str] = []
            if row.get("conflicting_indicators") is True:
                badges.append(":orange[⚠️ Conflicting Indicators]")
            if row.get("high_volatility") is True:
                badges.append(":red[🔴 HIGH VOLATILITY]")
            if badges:
                st.markdown("  &nbsp;".join(badges))

            # Last updated (REQ-OPS-002)
            ts = row.get("timestamp_of_last_bar")
            ts_str = str(pd.Timestamp(ts).date()) if ts is not None else "Never"
            st.caption(
                f"Last refreshed: {ts_str}"
                + (" ⚠️ data over 24 h old" if stale_data else "")
            )

            # LLM Analysis panel (REQ-LLM-007, REQ-LLMDEC-001)
            # Use signal_date (last bar date) not today — cache is keyed on bar date
            ts_for_cache = row.get("timestamp_of_last_bar")
            signal_date_str = (
                str(pd.Timestamp(ts_for_cache).date())
                if ts_for_cache is not None
                else today_str
            )
            explanation = load_explanation(symbol, signal_date_str)
            decision = load_decision(symbol, signal_date_str)
            news_items = load_news(symbol, signal_date_str)

            # --- IG Client Sentiment bar (shown outside LLM expander, always visible) ---
            ig_sentiment_item = next((h for h in news_items if h.get("source") == "IG Client Sentiment"), None)
            if ig_sentiment_item:
                long_pct = float(ig_sentiment_item.get("long_pct", 0))
                short_pct = float(ig_sentiment_item.get("short_pct", 0))
                bias = "LONG-biased" if long_pct > short_pct else "SHORT-biased"
                bias_colour = "green" if long_pct > short_pct else "red"
                scol1, scol2, scol3 = st.columns([2, 2, 1])
                scol1.metric("IG Clients Long", f"{long_pct:.0f}%")
                scol2.metric("IG Clients Short", f"{short_pct:.0f}%")
                scol3.markdown(f":{bias_colour}[**{bias}**]")
                st.progress(long_pct / 100)

            with st.expander("LLM Analysis", expanded=True):
                is_flat = (row.get("signal") == 0 or row.get("signal") is None)

                # --- News ---
                st.markdown("##### News")
                yf_news = [h for h in news_items if h.get("source") != "IG Client Sentiment"]
                if yf_news:
                    for h in yf_news:
                        url = h.get("url", "")
                        title = h.get("title", "")
                        source = h.get("source", "")
                        ts = h.get("timestamp", "")
                        label = f"{title} — *{source}*" if source else title
                        prefix = f"`{ts}` " if ts else ""
                        if url:
                            st.markdown(f"{prefix}[{label}]({url})")
                        else:
                            st.caption(f"{prefix}{label}")
                else:
                    st.caption("_No news available._")

                st.divider()

                # --- Signal Explanation ---
                st.markdown("##### Signal Explanation")
                if explanation != EXPLANATION_UNAVAILABLE:
                    st.markdown(explanation)
                elif is_flat:
                    st.caption("_No directional signal — strategies are split or neutral._")
                else:
                    st.caption("_Explanation unavailable._")

                st.divider()

                # --- Decision ---
                st.markdown("##### Decision")
                if decision:
                    rec = decision.get("llm_recommendation", "UNCERTAIN")
                    llm_direction = decision.get("direction")  # "LONG", "SHORT", or None
                    rationale = decision.get("rationale", "")
                    rec_colour = {"GO": "green", "NO_GO": "red", "UNCERTAIN": "orange"}.get(rec, "grey")
                    conflicts = decision.get("conflicts_with_technical", False)
                    # Build the badge label: "GO LONG" / "GO SHORT" for GO, else just rec
                    if rec == "GO" and llm_direction:
                        dir_colour = "green" if llm_direction == "LONG" else "red"
                        badge_md = f"### :{rec_colour}[GO] :{dir_colour}[{llm_direction}]"
                    else:
                        badge_md = f"### :{rec_colour}[{rec}]"
                    dcol1, dcol2 = st.columns([1, 3])
                    dcol1.markdown(badge_md)
                    with dcol2:
                        # Show technical consensus as context
                        tech_label = get_signal_label(row.get("signal"))
                        if tech_label not in ("Data Missing", "Neutral"):
                            st.caption(f"Technical consensus: **{tech_label.upper()}**")
                        if rationale:
                            st.markdown(rationale)
                        # Only show conflict warning when technical consensus is directional
                        tech_is_directional = row.get("signal") in (1, -1)
                        if conflicts and tech_is_directional:
                            st.warning("LLM direction conflicts with the technical consensus.")

                    # Order parameters for GO decisions
                    if rec == "GO":
                        d_entry = decision.get("entry_level")
                        d_stop = decision.get("stop_loss")
                        d_target = decision.get("take_profit")
                        d_risk = decision.get("risk_pct")
                        if d_entry is not None or d_stop is not None or d_target is not None:
                            oc1, oc2, oc3, oc4 = st.columns(4)
                            oc1.metric("Entry", _fmt_price(d_entry))
                            oc2.metric("Stop Loss", _fmt_price(d_stop))
                            oc3.metric("Target", _fmt_price(d_target))
                            oc4.metric("Risk %", f"{d_risk:.1f}%" if d_risk is not None else "—")
                elif is_flat:
                    st.caption("_No directional signal — LLM analysis only runs for Buy/Sell signals._")
                else:
                    st.caption("_LLM decision unavailable._")

            # Position sizing (REQ-RISK-004) — only for directional signals
            if label in ("Buy", "Sell"):
                stop_dist = row.get("stop_distance")
                close_val = row.get("close")
                if stop_dist and not (isinstance(stop_dist, float) and pd.isna(stop_dist)) and float(stop_dist) > 0:
                    sizing = calculate_position_size(
                        capital=10_000.0,
                        risk_pct=1.0,
                        stop_distance=float(stop_dist),
                        close_price=float(close_val) if close_val else 1.0,
                    )
                    if sizing["available"]:
                        st.caption(
                            f"📐 Position size: **{sizing['position_size_units']} units** "
                            f"| Risk: £{sizing['gbp_risk']:.2f}"
                        )
                else:
                    st.caption("📐 Position size: N/A — stop distance unavailable")




# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Dashboard")

    # --- Snapshot load ---
    df = load_snapshot()

    # --- Portfolio summary (REQ-UI-006) ---
    summary = compute_portfolio_summary(df)
    _render_portfolio_summary(summary)

    st.divider()

    # --- Refresh trigger (REQ-UI-003) ---
    _render_refresh_section()

    st.divider()

    # --- Correlation warnings (REQ-RISK-003) ---
    if df is not None and not df.empty:
        for warning in compute_correlation_warnings(df, CURATED_DATA_DIR):
            st.warning(f"⚠️ Correlation Risk: {warning['message']}")

    # --- Signal table (REQ-UI-002, REQ-UI-008) ---
    if df is None:
        st.info(
            "No signal snapshot found. "
            "Run **Refresh Data** above or execute `scripts/run_signals.py` "
            "to generate the first snapshot."
        )
        return

    if df.empty:
        st.warning("Snapshot file exists but contains no rows.")
        return

    st.subheader(f"Signals — {len(df)} instrument(s)")

    # Sort: GO (Sell/Buy) first, then NO_GO/UNCERTAIN, then data missing
    def _sort_key(row):
        if row.get("status") == "data_missing":
            return 3
        symbol = row.get("symbol", "")
        signal_date = row.get("signal_date", "")
        if hasattr(signal_date, "date"):
            signal_date = signal_date.date()
        decision = load_decision(symbol, str(signal_date))
        if decision and decision.get("llm_recommendation") == "GO":
            return 0 if decision.get("direction") == "SHORT" else 1
        return 2

    df = df.copy()
    df["_sort"] = df.apply(_sort_key, axis=1)
    df = df.sort_values("_sort").drop(columns=["_sort"])

    _render_signal_table(df)


main()
