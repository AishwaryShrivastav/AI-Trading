"""Broker factory — returns a live or paper broker based on TRADING_MODE.

Centralises broker construction so callers don't hard-code ``UpstoxBroker``.
In ``paper`` mode (the default) it returns a :class:`PaperBroker` that composes
a real :class:`UpstoxBroker` for price reads when a token is available.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from ...config import get_settings
from .base import BrokerBase
from .paper import PaperBroker
from .upstox import UpstoxBroker

logger = logging.getLogger(__name__)


def _build_upstox(settings) -> UpstoxBroker:
    return UpstoxBroker(
        api_key=settings.upstox_api_key,
        api_secret=settings.upstox_api_secret,
        redirect_uri=settings.upstox_redirect_uri,
    )


def _load_tokens(broker: UpstoxBroker, db: Optional[Session]) -> None:
    """Best-effort load of stored Upstox tokens onto a broker instance."""
    if db is None:
        return
    try:
        from ...database import Setting

        access = db.query(Setting).filter(Setting.key == "upstox_access_token").first()
        refresh = db.query(Setting).filter(Setting.key == "upstox_refresh_token").first()
        if access and access.value:
            broker.access_token = access.value
        if refresh and refresh.value:
            broker.refresh_token = refresh.value
    except Exception as e:  # pragma: no cover
        logger.warning(f"Could not load Upstox tokens: {e}")


def get_broker(db: Optional[Session] = None, settings=None) -> BrokerBase:
    """Return the broker for the configured trading mode.

    Args:
        db: optional DB session, used to load stored Upstox tokens.
        settings: optional settings override (defaults to global settings).
    """
    settings = settings or get_settings()
    mode = (settings.trading_mode or "paper").lower()

    if mode == "live":
        broker = _build_upstox(settings)
        _load_tokens(broker, db)
        return broker

    # paper (default): simulate fills, but read live prices when possible.
    live = _build_upstox(settings)
    _load_tokens(live, db)
    if not getattr(live, "access_token", None):
        live = None  # no token → fully offline paper fills
    return PaperBroker(
        live_broker=live,
        slippage_bps=getattr(settings, "paper_slippage_bps", 5.0),
    )
