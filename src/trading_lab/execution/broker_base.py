from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: str
    quantity: float


class BrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, order: OrderRequest) -> str:
        """Submit an order and return a broker reference."""
