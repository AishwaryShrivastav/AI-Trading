"""Paper execution for v2 trade cards (TradeHarness Step 2c).

Executes a ``TradeCardV2`` in paper mode: a PaperBroker computes a simulated
fill (real LTP when a token exists, else the card's entry price ± slippage),
and we persist an ``OrderV2`` and ``PositionV2`` flagged ``is_paper=True`` so the
multi-account pipeline, positions and reporting all work unchanged.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..database import OrderV2, PositionV2, TradeCardV2
from .broker import get_broker

logger = logging.getLogger(__name__)


async def paper_execute_card_v2(db: Session, card: TradeCardV2, settings=None) -> OrderV2:
    """Simulate execution of a v2 trade card. Returns the created OrderV2."""
    txn = "BUY" if (card.direction or "LONG").upper() in ("LONG", "BUY") else "SELL"
    broker = get_broker(db, settings=settings)

    resp = await broker.place_order(
        symbol=card.symbol,
        transaction_type=txn,
        quantity=card.quantity,
        order_type="LIMIT",
        price=card.entry_price,
        exchange=card.exchange or "NSE",
        product="D",
    )
    data = resp.get("data", {}) if isinstance(resp, dict) else {}
    fill_price = data.get("average_price") or card.entry_price

    order = OrderV2(
        trade_card_id=card.id,
        account_id=card.account_id,
        broker_order_id=data.get("order_id"),
        order_category="ENTRY",
        symbol=card.symbol,
        exchange=card.exchange or "NSE",
        order_type="LIMIT",
        transaction_type=txn,
        product="D",
        quantity=card.quantity,
        price=card.entry_price,
        status="complete",
        filled_quantity=card.quantity,
        average_price=fill_price,
        is_paper=True,
        filled_at=datetime.utcnow(),
    )
    db.add(order)

    position = PositionV2(
        account_id=card.account_id,
        trade_card_id=card.id,
        symbol=card.symbol,
        exchange=card.exchange or "NSE",
        direction=card.direction,
        quantity=card.quantity,
        average_entry_price=fill_price,
        current_price=fill_price,
        stop_loss=card.stop_loss,
        take_profit=card.take_profit,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        risk_amount=card.risk_amount,
        reward_potential=card.reward_amount,
        is_paper=True,
    )
    db.add(position)

    card.status = "EXECUTED"
    db.commit()
    db.refresh(order)
    logger.info(f"[PAPER] Executed v2 card {card.id} ({card.symbol}) @ {fill_price}")
    return order
