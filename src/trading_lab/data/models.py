from dataclasses import dataclass


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str
    period: str = "6mo"
    interval: str = "1d"
    adjusted: bool = True
    source: str = "yfinance"
