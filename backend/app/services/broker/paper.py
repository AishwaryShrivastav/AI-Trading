"""Paper trading broker — simulated fills, no real orders.

``PaperBroker`` implements the same ``BrokerBase`` contract as ``UpstoxBroker``
so it is a drop-in replacement selected via ``TRADING_MODE=paper`` (the default).

Design (per TradeHarness plan, Step 1):
 - **Reads** (LTP / OHLCV) delegate to a real ``UpstoxBroker`` when one is
   supplied and authenticated, so paper fills can use real market prices.
 - **Writes** (order placement) are simulated: orders fill immediately at the
   requested price (or live LTP) adjusted by a fixed slippage, and a synthetic
   ``PAPER-<uuid>`` order id is returned. No network call is ever made for an
   order, so paper mode works fully offline and never risks real money.
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BrokerBase

logger = logging.getLogger(__name__)


class PaperBroker(BrokerBase):
    """Simulated broker for paper trading."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        redirect_uri: str = "",
        live_broker: Optional[BrokerBase] = None,
        slippage_bps: float = 5.0,
    ):
        super().__init__(api_key, api_secret, redirect_uri)
        self._live = live_broker  # optional real broker used only for price reads
        self.slippage_bps = slippage_bps
        # Always "authenticated" — paper mode needs no broker session.
        self.access_token = "PAPER"
        self._orders: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ auth
    async def authenticate(self, auth_code: str) -> Dict[str, Any]:
        return {"access_token": "PAPER", "paper": True}

    async def refresh_access_token(self) -> Dict[str, Any]:
        return {"access_token": "PAPER", "paper": True}

    def is_token_valid(self) -> bool:  # never expires in paper mode
        return True

    # ------------------------------------------------------------------ reads
    async def get_ltp(self, symbol: str, exchange: str = "NSE") -> float:
        if self._live is not None and getattr(self._live, "access_token", None):
            try:
                return await self._live.get_ltp(symbol, exchange)
            except Exception as e:  # pragma: no cover - network/edge
                logger.warning(f"PaperBroker LTP fallthrough for {symbol}: {e}")
        return 0.0

    async def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1D",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        exchange: str = "NSE",
    ) -> List[Dict[str, Any]]:
        if self._live is not None and getattr(self._live, "access_token", None):
            try:
                return await self._live.get_ohlcv(symbol, interval, from_date, to_date, exchange)
            except Exception as e:  # pragma: no cover
                logger.warning(f"PaperBroker OHLCV fallthrough for {symbol}: {e}")
        return []

    # ------------------------------------------------------------------ fills
    def _apply_slippage(self, price: float, transaction_type: str) -> float:
        """BUY fills slightly higher, SELL slightly lower — adverse to us."""
        factor = self.slippage_bps / 10_000.0
        if transaction_type.upper() == "BUY":
            return round(price * (1 + factor), 2)
        return round(price * (1 - factor), 2)

    async def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        exchange: str = "NSE",
        product: str = "D",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Simulate an immediate fill. Returns an Upstox-shaped response."""
        ref_price = price or trigger_price
        if not ref_price or ref_price <= 0:
            ref_price = await self.get_ltp(symbol, exchange)
        if not ref_price or ref_price <= 0:
            raise ValueError(
                f"PaperBroker cannot determine a fill price for {symbol} "
                f"(no price/trigger and no live LTP available)"
            )

        fill_price = self._apply_slippage(float(ref_price), transaction_type)
        order_id = f"PAPER-{uuid.uuid4().hex[:12]}"
        record = {
            "order_id": order_id,
            "symbol": symbol,
            "exchange": exchange,
            "transaction_type": transaction_type.upper(),
            "order_type": order_type.upper(),
            "quantity": quantity,
            "filled_quantity": quantity,
            "average_price": fill_price,
            "status": "complete",
            "product": product,
            "paper": True,
            "placed_at": datetime.utcnow().isoformat(),
        }
        self._orders[order_id] = record
        logger.info(f"[PAPER] Simulated {transaction_type} {quantity} {symbol} @ {fill_price}")
        return {"status": "success", "data": record}

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        record = self._orders.get(order_id)
        if not record:
            return {"status": "error", "message": "order not found", "data": {}}
        return {"status": "success", "data": record}

    async def get_order_history(self) -> List[Dict[str, Any]]:
        return list(self._orders.values())

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        record = self._orders.get(order_id)
        if record and record["status"] not in ("complete", "cancelled"):
            record["status"] = "cancelled"
        return {"status": "success", "data": {"order_id": order_id, "status": "cancelled", "paper": True}}

    async def get_positions(self) -> List[Dict[str, Any]]:
        # Source of truth for paper positions is the DB (positions table with
        # is_paper=True). The broker keeps only its order log.
        return []

    async def get_funds(self) -> Dict[str, Any]:
        return {"status": "success", "data": {"paper": True}}

    async def get_holdings(self) -> List[Dict[str, Any]]:
        return []
