"""HIL relay endpoints (TradeHarness Step 6).

Provides:
  GET  /api/hil/stream              — SSE stream (real-time push to browser)
  GET  /api/hil/status              — system snapshot (risk state, mode, pending count)
  GET  /api/hil/cards               — list PENDING trade cards
  POST /api/hil/cards/{id}/approve  — approve + paper-execute at full size
  POST /api/hil/cards/{id}/half     — approve + paper-execute at half size
  POST /api/hil/cards/{id}/reject   — reject without executing
  POST /api/hil/halt                — emergency halt (set HALTED state)
  POST /api/hil/resume              — resume from HALTED
"""
import asyncio
import json
import logging
import math
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db, Setting, TradeCardV2
from ..services.notifier import Notifier, CARD_APPROVED, CARD_REJECTED, RISK_ALERT
from ..services.risk_governor import RiskGovernor

router = APIRouter(prefix="/api/hil", tags=["hil"])
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ SSE stream

@router.get("/stream")
async def sse_stream(request: Request):
    """Server-Sent Events stream — subscribe for real-time HIL notifications."""
    notifier = Notifier.get()

    async def generate():
        q = notifier.subscribe()
        try:
            # Immediately confirm connection
            yield f"data: {json.dumps({'type': 'connected', 'data': {}})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"  # prevent proxy timeout
        finally:
            notifier.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------ status

@router.get("/status")
async def hil_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """System snapshot: risk state, trading mode, pending cards, SSE subscribers."""
    from ..config import get_settings
    settings = get_settings()

    gov = RiskGovernor(db)
    risk_state = gov.get_state()
    pending = db.query(TradeCardV2).filter(TradeCardV2.status == "PENDING").count()

    mw = db.query(Setting).filter(Setting.key == "market_window_open").first()
    briefing = db.query(Setting).filter(Setting.key == "morning_briefing").first()
    eod = db.query(Setting).filter(Setting.key == "last_eod_report").first()

    return {
        "trading_mode": settings.trading_mode,
        "risk_state": risk_state.get("state", "ACTIVE"),
        "drawdown_pct": risk_state.get("drawdown_pct", 0),
        "resume_required": risk_state.get("resume_required", False),
        "pending_approvals": pending,
        "market_window_open": bool(mw.value) if mw else False,
        "morning_briefing": briefing.value if briefing else None,
        "last_eod_report": eod.value if eod else None,
        "sse_subscribers": Notifier.get().subscriber_count,
    }


# ------------------------------------------------------------------ cards list

@router.get("/cards")
async def pending_cards(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Return all PENDING trade cards in reverse-chronological order."""
    cards = (
        db.query(TradeCardV2)
        .filter(TradeCardV2.status == "PENDING")
        .order_by(TradeCardV2.created_at.desc())
        .all()
    )
    return {
        "cards": [
            {
                "id": c.id,
                "symbol": c.symbol,
                "direction": c.direction,
                "quantity": c.quantity,
                "entry_price": c.entry_price,
                "stop_loss": c.stop_loss,
                "take_profit": c.take_profit,
                "confidence": c.confidence,
                "strategy": c.strategy,
                "thesis": c.thesis,
                "risk_reward": c.risk_reward_ratio,
                "edge_pct": c.edge,
                "created_at": str(c.created_at),
            }
            for c in cards
        ]
    }


# ------------------------------------------------------------------ approve

@router.post("/cards/{card_id}/approve")
async def approve_card(
    card_id: int,
    user_id: str = Query(default="hil_user"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Approve a PENDING card at full quantity and paper-execute it."""
    return await _approve_and_execute(card_id, user_id, db, size_factor=1.0)


# ------------------------------------------------------------------ half-size

@router.post("/cards/{card_id}/half")
async def half_size_approve(
    card_id: int,
    user_id: str = Query(default="hil_user"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Approve a PENDING card at half the original quantity and paper-execute it."""
    return await _approve_and_execute(card_id, user_id, db, size_factor=0.5)


# ------------------------------------------------------------------ reject

@router.post("/cards/{card_id}/reject")
async def reject_card(
    card_id: int,
    reason: str = Query(default="Manual rejection via HIL"),
    user_id: str = Query(default="hil_user"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Reject a PENDING card without executing it."""
    card = _get_pending_card(card_id, db)
    card.status = "REJECTED"
    card.rejection_reason = reason
    card.rejected_at = datetime.utcnow()
    db.commit()

    await Notifier.get().send(CARD_REJECTED, {
        "card_id": card_id, "symbol": card.symbol, "reason": reason,
    })
    logger.info("[HIL] Card %d (%s) rejected: %s", card_id, card.symbol, reason)
    return {"status": "rejected", "card_id": card_id, "symbol": card.symbol}


# ------------------------------------------------------------------ halt / resume

@router.post("/halt")
async def hil_halt(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Emergency stop: force HALTED state (no new entries, paper mode)."""
    from ..config import get_settings
    state = {
        "state": "HALTED",
        "reason": "Manual HALT via HIL relay",
        "resume_required": True,
        "halted_at": datetime.utcnow().isoformat(),
        "forced_paper": True,
    }
    row = db.query(Setting).filter(Setting.key == "system_state").first()
    if row:
        row.value = state
    else:
        db.add(Setting(key="system_state", value=state, description="Risk state"))
    db.commit()

    settings = get_settings()
    settings.trading_mode = "paper"

    await Notifier.get().send(RISK_ALERT, {"level": "HALTED", "reason": "Manual HALT via HIL"})
    logger.warning("[HIL] EMERGENCY HALT issued via HIL relay")
    return {"status": "halted", "state": state}


@router.post("/resume")
async def hil_resume(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Resume trading after a HALTED state."""
    gov = RiskGovernor(db)
    result = gov.resume()
    if result.get("resumed"):
        await Notifier.get().send(RISK_ALERT, {"level": "ACTIVE", "reason": "Manual RESUME via HIL"})
        logger.info("[HIL] RESUME issued via HIL relay")
    return result


# ------------------------------------------------------------------ helpers

def _get_pending_card(card_id: int, db: Session) -> TradeCardV2:
    card = db.query(TradeCardV2).filter(TradeCardV2.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    if card.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Card status is {card.status!r}, expected PENDING")
    return card


async def _approve_and_execute(
    card_id: int, user_id: str, db: Session, size_factor: float
) -> Dict[str, Any]:
    """Shared logic for approve / half-size approve."""
    from ..services.paper_execution import paper_execute_card_v2
    from ..config import get_settings

    card = _get_pending_card(card_id, db)
    original_qty = card.quantity

    if size_factor != 1.0:
        card.quantity = max(1, math.ceil(original_qty * size_factor))
    card.approved_by = user_id
    db.commit()

    settings = get_settings()
    order = await paper_execute_card_v2(db, card, settings=settings)

    await Notifier.get().send(CARD_APPROVED, {
        "card_id": card_id,
        "symbol": card.symbol,
        "direction": card.direction,
        "quantity": card.quantity,
        "original_quantity": original_qty,
        "half_size": size_factor < 1.0,
    })
    logger.info(
        "[HIL] Card %d (%s %s×%d) approved%s and executed",
        card_id, card.direction, card.symbol, card.quantity,
        " at half size" if size_factor < 1.0 else "",
    )
    return {
        "status": "executed",
        "card_id": card_id,
        "symbol": card.symbol,
        "quantity": card.quantity,
        "original_quantity": original_qty,
        "half_size": size_factor < 1.0,
        "order_id": getattr(order, "id", None),
        "broker_order_id": getattr(order, "broker_order_id", None),
    }
