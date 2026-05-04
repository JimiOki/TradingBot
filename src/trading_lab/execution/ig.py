"""IG broker adapter — authentication, order placement, and client sentiment.

Supports demo and live accounts.  By default the adapter connects to the DEMO
account (for trade execution).  Pass ``live=True`` to connect to the LIVE
account (for market-data fetching such as sentiment and prices).

Usage::

    adapter = IgBrokerAdapter()            # demo — trade execution
    adapter = IgBrokerAdapter(live=True)   # live — data fetching

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

import requests

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
    """Create and authenticate an IGService instance (DEMO) from environment variables."""
    from trading_ig import IGService

    api_key = os.environ.get("IG_API_KEY", "")
    username = os.environ.get("IG_USERNAME", "")
    password = os.environ.get("IG_PASSWORD", "")
    acc_type = "DEMO" if os.environ.get("IG_DEMO", "").lower() == "true" else "LIVE"

    if not all([api_key, username, password]):
        raise RuntimeError(
            "IG credentials missing. Set IG_API_KEY, IG_USERNAME, IG_PASSWORD in .env"
        )

    acc_number = os.environ.get("IG_ACCOUNT_ID", "")
    ig = IGService(username, password, api_key, acc_type, acc_number=acc_number)
    ig.create_session(version="3")
    logger.info("IG session created (account_type=%s, version=3)", acc_type)
    return ig


def _build_ig_service_live():
    """Create and authenticate an IGService instance for the LIVE account.

    Reads IG_LIVE_* environment variables.  Used for market-data fetching
    (sentiment, prices) where the demo API returns incomplete data.
    """
    from trading_ig import IGService

    api_key = os.environ.get("IG_LIVE_API_KEY", "")
    username = os.environ.get("IG_LIVE_USERNAME", "")
    password = os.environ.get("IG_LIVE_PASSWORD", "")

    if not all([api_key, username, password]):
        raise RuntimeError(
            "Live IG credentials missing. Set IG_LIVE_API_KEY, IG_LIVE_USERNAME, "
            "IG_LIVE_PASSWORD in .env"
        )

    acc_number = os.environ.get("IG_LIVE_ACCOUNT_ID", "")
    ig = IGService(username, password, api_key, "LIVE", acc_number=acc_number)
    ig.create_session(version="3")
    logger.info("IG LIVE session created for data fetching (version=3)")
    return ig


class IgBrokerAdapter(BrokerAdapter):
    """IG REST API adapter for order placement and client sentiment.

    Args:
        live: If True, connect to the LIVE account using IG_LIVE_* env vars.
              Default False connects to demo for trade execution.
    """

    def __init__(self, live: bool = False) -> None:
        self._ig = None  # lazy — only connect when needed
        self._live = live

    def _session(self):
        """Return an authenticated IGService, creating one if needed."""
        if self._ig is None:
            if self._live:
                self._ig = _build_ig_service_live()
            else:
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

                    # Stop / limit levels (may be absent or NaN)
                    stop_level = row.get("stopLevel") or row.get("stop_level")
                    limit_level = row.get("limitLevel") or row.get("limit_level")

                    try:
                        stop_level = float(stop_level) if stop_level not in (None, "", "nan") else None
                    except (TypeError, ValueError):
                        stop_level = None
                    try:
                        limit_level = float(limit_level) if limit_level not in (None, "", "nan") else None
                    except (TypeError, ValueError):
                        limit_level = None

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
                            "stop_level": stop_level,
                            "limit_level": limit_level,
                        }
                    )
                except Exception as row_exc:
                    logger.warning("Skipping malformed position row: %s", row_exc)

            return positions

        except Exception as exc:
            logger.warning("fetch_positions failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Account balance
    # ------------------------------------------------------------------

    def fetch_balance(self) -> float:
        """Return available balance (cash minus margin) for the active account.

        Uses ``IGService.fetch_accounts()`` which returns a DataFrame with
        one row per account.  Finds the row matching the configured account
        ID and returns the ``available`` column value (GBP for spreadbet
        accounts).

        Raises RuntimeError if the balance cannot be determined.
        """
        try:
            ig = self._session()
            df = ig.fetch_accounts()
            if df is None or (hasattr(df, "empty") and df.empty):
                raise RuntimeError("IG returned no accounts")

            # Try to match configured account ID
            acc_id = os.environ.get(
                "IG_LIVE_ACCOUNT_ID" if self._live else "IG_ACCOUNT_ID", ""
            )
            if acc_id and "accountId" in df.columns:
                match = df[df["accountId"] == acc_id]
                if not match.empty:
                    df = match

            # Take the first (or only) matching account
            row = df.iloc[0]
            available = float(row.get("available", 0) or 0)
            logger.info(
                "IG account %s balance: available=%.2f",
                row.get("accountId", "?"),
                available,
            )
            return available
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Could not fetch IG account balance: {exc}") from exc

    # ------------------------------------------------------------------
    # Position close
    # ------------------------------------------------------------------

    def close_position(self, deal_id: str, direction: str, size: float) -> str:
        """Close an open IG position by deal ID.

        Posts to ``/positions/otc`` with a ``_method: DELETE`` header override
        (IG's documented close-position mechanism).

        Args:
            deal_id: The IG deal ID of the open position.
            direction: The direction of the *open* position ("BUY" or "SELL").
                       The close order is placed in the opposite direction.
            size: Position size to close.

        Returns:
            IG deal reference string.

        Raises:
            RuntimeError: if IG rejects the close request.
        """
        ig = self._session()

        close_direction = "SELL" if direction.upper() == "BUY" else "BUY"

        logger.info(
            "Closing IG position: deal_id=%s open_direction=%s close_direction=%s size=%s",
            deal_id, direction, close_direction, size,
        )

        body = {
            "dealId": deal_id,
            "direction": close_direction,
            "size": size,
            "orderType": "MARKET",
            "timeInForce": "FILL_OR_KILL",
        }

        headers = dict(ig.session.headers)
        headers["Version"] = "1"
        headers["Content-Type"] = "application/json; charset=UTF-8"
        headers["Accept"] = "application/json; charset=UTF-8"
        headers["_method"] = "DELETE"

        resp = requests.post(
            f"{ig.BASE_URL}/positions/otc",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        result = resp.json()

        deal_ref = result.get("dealReference", "")
        if not deal_ref:
            raise RuntimeError(f"IG returned no deal reference on close: {result}")

        # Fetch deal confirmation to verify the close was accepted.
        try:
            confirm = ig.fetch_deal_by_deal_reference(deal_ref)
            deal_status = confirm.get("dealStatus", "UNKNOWN")
            reason = confirm.get("reason", "")
            if deal_status != "ACCEPTED":
                raise RuntimeError(
                    f"IG rejected close {deal_ref}: status={deal_status} reason={reason}"
                )
            logger.info("IG position closed — deal_reference=%s", deal_ref)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning(
                "Could not fetch confirm for close %s: %s — treating as closed",
                deal_ref, exc,
            )

        return deal_ref

    # ------------------------------------------------------------------
    # Position update (stop / limit)
    # ------------------------------------------------------------------

    def update_position(self, deal_id: str, stop_level: float | None = None, limit_level: float | None = None) -> str:
        """Update stop and/or limit on an existing IG position.

        Uses PUT /positions/otc/{dealId} (v2).

        Args:
            deal_id: The IG deal ID.
            stop_level: New absolute stop level, or None to leave unchanged.
            limit_level: New absolute limit/target level, or None to leave unchanged.

        Returns:
            IG deal reference string.

        Raises:
            RuntimeError: if IG rejects the update.
        """
        ig = self._session()

        body = {}
        if stop_level is not None:
            body["stopLevel"] = stop_level
        if limit_level is not None:
            body["limitLevel"] = limit_level

        if not body:
            logger.info("update_position called with no changes for deal_id=%s", deal_id)
            return ""

        # IG requires trailingStop fields even when not using trailing stops
        body["trailingStop"] = False

        logger.info(
            "Updating IG position: deal_id=%s stop=%s limit=%s",
            deal_id, stop_level, limit_level,
        )

        headers = dict(ig.session.headers)
        headers["Version"] = "2"
        headers["Content-Type"] = "application/json; charset=UTF-8"
        headers["Accept"] = "application/json; charset=UTF-8"

        resp = requests.put(
            f"{ig.BASE_URL}/positions/otc/{deal_id}",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        result = resp.json()

        deal_ref = result.get("dealReference", "")
        if not deal_ref:
            raise RuntimeError(f"IG returned no deal reference on update: {result}")

        # Confirm
        try:
            confirm = ig.fetch_deal_by_deal_reference(deal_ref)
            deal_status = confirm.get("dealStatus", "UNKNOWN")
            reason = confirm.get("reason", "")
            if deal_status != "ACCEPTED":
                raise RuntimeError(
                    f"IG rejected position update {deal_ref}: status={deal_status} reason={reason}"
                )
            logger.info("IG position updated — deal_reference=%s", deal_ref)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning("Could not fetch confirm for update %s: %s — treating as updated", deal_ref, exc)

        return deal_ref

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

        logger.info(
            "Placing IG order: epic=%s side=%s size=%s stop_dist=%s limit_dist=%s order_type=%s level=%s",
            order.epic, order.side, order.size, order.stop_distance, order.limit_distance,
            order.order_type, order.level,
        )

        # Build a clean request body — no null fields.  The trading_ig
        # library's create_open_position() sends null fields that IG's
        # spreadbet engine rejects (REJECT_CFD_ORDER_ON_SPREADBET_ACCOUNT).

        # Use the library's authenticated session headers (OAuth Bearer token)
        # and POST directly to avoid the library injecting null fields.
        headers = dict(ig.session.headers)
        headers["Version"] = "2"
        headers["Content-Type"] = "application/json; charset=UTF-8"
        headers["Accept"] = "application/json; charset=UTF-8"

        if order.order_type == "LIMIT":
            # LIMIT orders go via the working orders endpoint
            body = {
                "currencyCode": "GBP",
                "direction": order.side,
                "epic": order.epic,
                "expiry": "DFB",
                "forceOpen": True,
                "guaranteedStop": False,
                "level": order.level,
                "size": order.size,
                "stopDistance": order.stop_distance,
                "limitDistance": order.limit_distance,
                "timeInForce": "GOOD_TILL_CANCELLED",
                "type": "LIMIT",
            }
            resp = requests.post(
                f"{ig.BASE_URL}/workingorders/otc",
                json=body,
                headers=headers,
            )
        else:
            # MARKET orders go via positions endpoint
            body = {
                "currencyCode": "GBP",
                "direction": order.side,
                "epic": order.epic,
                "expiry": "DFB",
                "forceOpen": True,
                "guaranteedStop": False,
                "orderType": "MARKET",
                "size": order.size,
                "stopDistance": order.stop_distance,
                "limitDistance": order.limit_distance,
            }
            resp = requests.post(
                f"{ig.BASE_URL}/positions/otc",
                json=body,
                headers=headers,
            )

        resp.raise_for_status()
        result = resp.json()

        deal_ref = result.get("dealReference", "")
        if not deal_ref:
            raise RuntimeError(f"IG returned no deal reference: {result}")

        # Fetch deal confirmation to verify acceptance.
        try:
            confirm = ig.fetch_deal_by_deal_reference(deal_ref)
            deal_status = confirm.get("dealStatus", "UNKNOWN")
            reason = confirm.get("reason", "")
            if deal_status != "ACCEPTED":
                raise RuntimeError(
                    f"IG rejected order {deal_ref}: status={deal_status} reason={reason}"
                )
            logger.info("IG order ACCEPTED — deal_reference=%s", deal_ref)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning("Could not fetch confirm for %s: %s — treating as placed", deal_ref, exc)

        return deal_ref
