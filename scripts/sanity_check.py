import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BASE_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    from trading_lab.data.models import MarketDataRequest
    from trading_lab.data.yfinance_ingest import ingest_yfinance_daily

    request = MarketDataRequest(symbol="SPY", period="6mo", interval="1d", adjusted=True)
    raw_file, curated_file, curated_df = ingest_yfinance_daily(request)

    print("Downloaded rows:", len(curated_df))
    print("Columns:", list(curated_df.columns))
    print("Raw saved to:", raw_file)
    print("Curated saved to:", curated_file)
    print(curated_df.tail())


if __name__ == "__main__":
    main()
