from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OrderRequest:
    symbol: str        # yfinance symbol, e.g. "GC=F"
    side: str          # "BUY" or "SELL"
    size: float        # £/point for spreadbets
    epic: str = ""     # IG epic, e.g. "CS.D.CFDGOLD.CFD.IP"
    stop_distance: float = 0.0   # points from entry
    limit_distance: float = 0.0  # points from entry
    order_type: str = "MARKET"   # "MARKET" or "LIMIT"
    level: float | None = None   # required for LIMIT orders — the entry price


class BrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, order: OrderRequest) -> str:
        """Submit an order and return a broker reference."""
