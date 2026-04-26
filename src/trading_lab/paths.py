"""Central path definitions for the trading-lab project.

All code that needs a file path should import from here.
Never construct paths ad-hoc in scripts or modules.
"""
from pathlib import Path

# Project root — two levels up from this file (src/trading_lab/paths.py)
ROOT_DIR = Path(__file__).resolve().parents[2]

# Top-level directories
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
SCRIPTS_DIR = ROOT_DIR / "scripts"
APP_DIR = ROOT_DIR / "app"

# Data subdirectories
RAW_DATA_DIR = DATA_DIR / "raw"
CURATED_DATA_DIR = DATA_DIR / "curated"
FEATURES_DATA_DIR = DATA_DIR / "features"
SIGNALS_DATA_DIR = DATA_DIR / "signals"
EXPLANATIONS_DIR = DATA_DIR / "signals" / "explanations"
DECISIONS_DIR = DATA_DIR / "signals" / "decisions"
BACKTEST_DATA_DIR = DATA_DIR / "backtests"
JOURNAL_DIR = DATA_DIR / "journal"
CALENDAR_DIR = DATA_DIR / "calendar"
NEWS_DIR = DATA_DIR / "news"
RISK_DIR = DATA_DIR / "risk"
LIVE_DATA_DIR = DATA_DIR / "live"

# Config files
INSTRUMENTS_CONFIG = CONFIG_DIR / "instruments.yaml"
LOCAL_ENV_CONFIG = CONFIG_DIR / "environments" / "local.yaml"
STRATEGIES_CONFIG_DIR = CONFIG_DIR / "strategies"

# All directories that must exist at runtime
_REQUIRED_DIRS = [
    RAW_DATA_DIR,
    CURATED_DATA_DIR,
    FEATURES_DATA_DIR,
    SIGNALS_DATA_DIR,
    EXPLANATIONS_DIR,
    DECISIONS_DIR,
    BACKTEST_DATA_DIR,
    JOURNAL_DIR,
    CALENDAR_DIR,
    NEWS_DIR,
    RISK_DIR,
    LIVE_DATA_DIR,
    LOGS_DIR,
]


def ensure_data_dirs() -> None:
    """Create all required data directories if they do not exist."""
    for directory in _REQUIRED_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
