from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
CURATED_DATA_DIR = DATA_DIR / "curated"
FEATURES_DATA_DIR = DATA_DIR / "features"
BACKTEST_DATA_DIR = DATA_DIR / "backtests"


def ensure_data_dirs() -> None:
    """Create the standard data directories used by the project."""
    for path in (DATA_DIR, RAW_DATA_DIR, CURATED_DATA_DIR, FEATURES_DATA_DIR, BACKTEST_DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)
