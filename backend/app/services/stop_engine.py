"""Trailing & time stop-loss engine (TradeHarness Step 4b).

Pure helpers (testable in isolation) plus a DB routine that ratchets stop-losses
on open paper positions. The trailing stop is ratchet-only: it never loosens, so
running it periodically locks in gains as price advances.

The actual intraday force-exit at the cutoff is *detected* here; executing the
exit is wired to the market-aware scheduler (Step 5).
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import PositionV2

logger = logging.getLogger(__name__)


def trailing_stop(
    entry: float,
    current_price: float,
    side: str = "LONG",
    current_sl: Optional[float] = None,
    activate_pct: float = 2.0,
    lock_fraction: float = 0.5,
) -> Optional[float]:
    """Return the (possibly raised) trailing stop. Ratchet-only.

    Activates only after the position is up ``activate_pct``; then locks
    ``lock_fraction`` of the open gain. Never loosens an existing stop.
    """
    if not entry or entry <= 0 or not current_price or current_price <= 0:
        return current_sl
    side = side.upper()
    if side in ("LONG", "BUY"):
        gain_pct = (current_price - entry) / entry * 100.0
        if gain_pct < activate_pct:
            return current_sl
        locked = entry + (current_price - entry) * lock_fraction
        return max(locked, current_sl) if current_sl is not None else locked
    else:  # SHORT
        gain_pct = (entry - current_price) / entry * 100.0
        if gain_pct < activate_pct:
            return current_sl
        locked = entry - (entry - current_price) * lock_fraction
        return min(locked, current_sl) if current_sl is not None else locked


def is_time_exit(now: datetime, cutoff: str = "15:10") -> bool:
    """True if ``now`` is at/after the intraday cutoff (HH:MM)."""
    try:
        hh, mm = (int(x) for x in cutoff.split(":"))
    except Exception:
        return False
    return (now.hour, now.minute) >= (hh, mm)


def manage_trailing_stops(db: Session, settings=None) -> List[Dict[str, Any]]:
    """Ratchet stop-losses on open paper positions using current_price.

    Returns a list of {position_id, symbol, old_sl, new_sl} for stops moved.
    """
    settings = settings or get_settings()
    updates: List[Dict[str, Any]] = []
    positions = (
        db.query(PositionV2)
        .filter(PositionV2.closed_at.is_(None), PositionV2.is_paper == True)  # noqa: E712
        .all()
    )
    for p in positions:
        if not p.current_price or not p.average_entry_price:
            continue
        new_sl = trailing_stop(
            entry=p.average_entry_price, current_price=p.current_price,
            side=p.direction or "LONG", current_sl=p.stop_loss,
            activate_pct=settings.trail_activate_pct, lock_fraction=settings.trail_lock_fraction,
        )
        # trailing_stop is ratchet-only, so any change is a favourable move.
        if new_sl is not None and (p.stop_loss is None or round(float(new_sl), 2) != round(float(p.stop_loss), 2)):
            old = p.stop_loss
            p.stop_loss = round(float(new_sl), 2)
            updates.append({"position_id": p.id, "symbol": p.symbol, "old_sl": old, "new_sl": p.stop_loss})
    if updates:
        db.commit()
        logger.info(f"Trailing stops ratcheted on {len(updates)} position(s).")
    return updates
