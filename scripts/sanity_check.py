from pathlib import Path
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

ticker = "SPY"
df = yf.download(ticker, period="6mo", interval="1d", auto_adjust=True)

if df.empty:
    raise RuntimeError("No data downloaded.")

output_file = DATA_DIR / f"{ticker.lower()}_daily.parquet"
df.to_parquet(output_file)

print("Downloaded rows:", len(df))
print("Columns:", list(df.columns))
print("Saved to:", output_file)
print(df.tail())
