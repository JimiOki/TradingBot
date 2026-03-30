import pandas as pd


def normalize_yfinance_daily(df: pd.DataFrame, symbol: str, source: str) -> pd.DataFrame:
    """Normalize a yfinance dataframe into the project bar schema."""
    normalized = df.reset_index().rename(
        columns={
            "Date": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )

    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [column for column in columns if column not in normalized.columns]
    if missing:
        raise ValueError(f"Missing expected columns from yfinance payload: {missing}")

    normalized = normalized.loc[:, columns].copy()
    normalized["symbol"] = symbol
    normalized["source"] = source
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)

    return normalized.sort_values("timestamp").reset_index(drop=True)
