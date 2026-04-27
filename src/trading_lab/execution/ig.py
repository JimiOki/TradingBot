"""IG broker adapter — authentication, order placement, and client sentiment.

Supports demo and live accounts via IG_DEMO environment variable.

Usage::

    adapter = IgBrokerAdapter()
    sentiment = adapter.fetch_sentiment("CS.D.CFDGOLD.CFD.IP")
    deal_ref = adapter.place_order(OrderRequest(
        symbol="GC=F",
        epic="CS.D.CFDGOLD.CFD.IP",
        side="SELL",
        size=1.0,
        stop_distance=10.0,
        limit_distance=20.0,
    ))
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from trading_lab.execution.broker_base import BrokerAdapter, OrderRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IgSentiment:
    """Client sentiment from IG for a single market."""
    market_id: str
    long_pct: float
    short_pct: float

    def as_context_str(self) -> str:
        """Return a human-readable string for inclusion in LLM context."""
        bias = "LONG-biased" if self.long_pct > self.short_pct else "SHORT-biased"
        return (
            f"IG client sentiment: {self.long_pct:.0f}% long / "
            f"{self.short_pct:.0f}% short ({bias})"
        )


def _build_ig_service():
    """Create and authenticate an IGService instance from environment variables."""
    from trading_ig import IGService
    from trading_ig.rest import ApiExceededException

    api_key = os.environ.get("IG_API_KEY", "")
    username = os.environ.get("IG_USERNAME", "")
    password = os.environ.get("IG_PASSWORD", "")
    acc_type = "DEMO" if os.environ.get("IG_DEMO", "").lower() == "true" else "LIVE"

    if not all([api_key, username, password]):
        raise RuntimeError(
            "IG credentials missing. Set IG_API_KEY, IG_USERNAME, IG_PASSWORD in .env"
        )

    ig = IGService(username, password, api_key, acc_type)
    ig.create_session()
    logger.info("IG session created (account_type=%s)", acc_type)
    return ig


class IgBrokerAdapter(BrokerAdapter):
    """IG REST API adapter for order placement and client sentiment."""

    def __init__(self) -> None:
        self._ig = None  # lazy — only connect when needed

    def _session(self):
        """Return an authenticated IGService, creating one if needed."""
        if self._ig is None:
            self._ig = _build_ig_service()
        return self._ig

    # ------------------------------------------------------------------
    # Sentiment (no account ID needed — public-ish endpoint)
    # ------------------------------------------------------------------

    def fetch_sentiment(self, market_id: str) -> IgSentiment | None:
        """Fetch IG client sentiment for a market.

        Args:
            market_id: IG market identifier, e.g. "GOLD" or numeric ID.
                       Can also pass the epic and IG will resolve it.

        Returns:
            IgSentiment or None if the call fails.
        """
        try:
            ig = self._session()
            # Returns a Munch object directly with longPositionPercentage / shortPositionPercentage
            data = ig.fetch_client_sentiment_by_instrument(market_id)
            if not data:
                logger.debug("No sentiment data returned for market_id=%s", market_id)
                return None
            return IgSentiment(
                market_id=market_id,
                long_pct=float(data.get("longPositionPercentage", 0)),
                short_pct=float(data.get("shortPositionPercentage", 0)),
            )
        except Exception as exc:
            logger.warning("IG sentiment fetch failed for %s: %s", market_id, exc)
            return None

    # ------------------------------------------------------------------
    # Open positions
    # ------------------------------------------------------------------

    def fetch_positions(self) -> list[dict]:
        """Return all open positions for the active IG account.

        Calls ``IGService.fetch_open_positions()`` which returns a DataFrame
        (v2 API) with one row per position.  Each row's columns come from
        two nested objects in the IG response:

        * ``position``: dealId, size, direction, level, currency, …
        * ``market``:   epic, instrumentName, bid, offer, …

        The current market price is taken as the midpoint of bid/offer.
        Unrealised P&L (``upl``) is not exposed by the trading-ig library's
        column flattening so it is computed locally as::

            pnl = (current_level - open_level) * size   # BUY
            pnl = (open_level - current_level) * size   # SELL

        Returns:
            List of position dicts.  Returns ``[]`` on any failure.
        """
        try:
            ig = self._session()
            df = ig.fetch_open_positions()

            # Empty account — library returns an empty DataFrame
            if df is None or (hasattr(df, "empty") and df.empty):
                return []

            positions: list[dict] = []
            for _, row in df.iterrows():
                try:
                    epic: str = str(row.get("epic", "") or "")
                    deal_id: str = str(row.get("dealId", "") or "")
                    direction: str = str(row.get("direction", "") or "").upper()
                    size: float = float(row.get("size", 0) or 0)
                    open_level: float = float(row.get("level", 0) or 0)
                    currency: str = str(row.get("currency", "") or "")
                    instrument_name: str = str(row.get("instrumentName", "") or "")

                    # Current price: midpoint of bid/offer when available
                    bid = row.get("bid")
                    offer = row.get("offer")
                    if bid not in (None, "") and offer not in (None, ""):
                        current_level = (float(bid) + float(offer)) / 2.0
                    else:
                        current_level = open_level  # fallback — no live price

                    # Approximate unrealised P&L
                    if direction == "BUY":
                        pnl = (current_level - open_level) * size
                    else:
                        pnl = (open_level - current_level) * size

                    positions.append(
                        {
                            "deal_id": deal_id,
                            "epic": epic,
                            "symbol": epic,  # epic is the canonical identifier; callers may remap
                            "direction": direction,
                            "size": size,
                            "open_level": open_level,
                            "current_level": current_level,
                            "pnl": round(pnl, 2),
                            "currency": currency,
                            "instrument_name": instrument_name,
                        }
                    )
                except Exception as row_exc:
                    logger.warning("Skipping malformed position row: %s", row_exc)

            return positions

        except Exception as exc:
            logger.warning("fetch_positions failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_order(self, order: OrderRequest) -> str:
        """Place a spreadbet position on IG.

        Args:
            order: OrderRequest with epic, side, size, stop_distance,
                   limit_distance populated.

        Returns:
            IG deal reference string.

        Raises:
            ValueError: if the order is missing required IG fields.
            RuntimeError: if IG rejects the order.
        """
        if not order.epic:
            raise ValueError(f"OrderRequest for {order.symbol} has no epic — check instruments.yaml")

        ig = self._session()
        account_id = os.environ.get("IG_ACCOUNT_ID", "")

        logger.info(
            "Placing IG order: epic=%s side=%s size=%s stop_dist=%s limit_dist=%s",
            order.epic, order.side, order.size, order.stop_distance, order.limit_distance,
        )

        response = ig.create_open_position(
            currency_code="GBP",
            direction=order.side,          # "BUY" or "SELL"
            epic=order.epic,
            expiry="-",                    # undated spreadbet
            force_open=True,
            guaranteed_stop=False,
            level=None,
            limit_distance=order.limit_distance,
            limit_level=None,
            order_type="MARKET",
            quote_id=None,
            size=order.size,
            stop_distance=order.stop_distance,
            stop_level=None,
            trailing_stop=False,
            trailing_stop_increment=None,
        )

        deal_ref = response.get("dealReference", "")
        if not deal_ref:
            raise RuntimeError(f"IG returned no deal reference: {response}")

        logger.info("IG order placed — deal_reference=%s", deal_ref)
        return deal_ref
