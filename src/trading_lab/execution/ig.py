from trading_lab.execution.broker_base import BrokerAdapter, OrderRequest


class IgBrokerAdapter(BrokerAdapter):
    def place_order(self, order: OrderRequest) -> str:
        raise NotImplementedError("IG execution is intentionally not enabled yet.")
