"""Streamlit application entry point.

REQ-UI-001: Navigation sidebar with last-refresh timestamp and environment badge.
REQ-OPS-004: Dark mode via .streamlit/config.toml (base = "dark").

Usage::

    streamlit run app/main.py
"""
import sys
from datetime import timezone
from pathlib import Path

import streamlit as st

st.set_page_config(layout="wide")

# Auth gate
if not st.user.is_logged_in:
    st.title("Trading Lab")
    st.button("Log in with Google", on_click=st.login)
    st.stop()

ALLOWED_EMAILS = {"jokikiolu@gmail.com"}
if st.user.email not in ALLOWED_EMAILS:
    st.error("Unauthorized. Access restricted.")
    st.logout()
    st.stop()

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trading_lab.paths import SIGNALS_DATA_DIR

# ---------------------------------------------------------------------------
# Page registry
# ---------------------------------------------------------------------------

SNAPSHOT_PATH = SIGNALS_DATA_DIR / "portfolio_snapshot.parquet"

dashboard = st.Page("pages/dashboard.py", title="Dashboard", icon="📊", default=True)
trade_journal = st.Page("pages/trade_journal.py", title="Trade Journal", icon="📒")
charts = st.Page("pages/charts.py", title="Charts", icon="📈")
backtests = st.Page("pages/backtests.py", title="Backtests", icon="🔬")
settings = st.Page("pages/settings.py", title="Settings", icon="⚙️")

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

pg = st.navigation([dashboard, trade_journal, charts, backtests, settings])

# ---------------------------------------------------------------------------
# Sidebar — REQ-UI-001
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Trading Lab")
    st.button("Logout", on_click=st.logout)

    # Environment badge
    try:
        import yaml
        env_cfg = ROOT / "config" / "environments" / "local.yaml"
        if env_cfg.exists():
            with open(env_cfg) as f:
                env_name = yaml.safe_load(f).get("environment", "local")
        else:
            env_name = "local"
    except Exception:
        env_name = "local"

    badge_colour = "green" if env_name == "production" else "orange" if env_name == "staging" else "blue"
    st.markdown(f":{badge_colour}[**{env_name.upper()}**]")

    st.divider()

    # Last-refresh timestamp
    last_refresh = st.session_state.get("last_refresh", None)
    if last_refresh is None and SNAPSHOT_PATH.exists():
        import pandas as pd
        mtime = SNAPSHOT_PATH.stat().st_mtime
        from datetime import datetime
        last_refresh = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if last_refresh:
        st.caption(f"Last refresh: {last_refresh}")
    else:
        st.caption("Last refresh: never")

pg.run()
