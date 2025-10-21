"""Guardrails API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.risk_checks import RiskChecker
from ..database import TradeCardV2


router = APIRouter(prefix="/api/guardrails", tags=["Guardrails"])


class GuardrailCheckRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    account_id: Optional[int] = None
    quantity: int = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    trade_type: str = Field(..., pattern="^(LONG|SHORT)$")
    exchange: str = "NSE"
    sector: Optional[str] = None
    event_id: Optional[int] = None


@router.post("/check")
async def check_guardrails(
    payload: GuardrailCheckRequest,
    db: Session = Depends(get_db)
):
    """Run all guardrails for a potential trade and return structured result."""
    try:
        checker = RiskChecker(db)
        result = await checker.run_all_checks(
            symbol=payload.symbol,
            quantity=payload.quantity,
            entry_price=payload.entry_price,
            stop_loss=payload.stop_loss,
            trade_type=payload.trade_type,
            exchange=payload.exchange,
            account_id=payload.account_id,
            sector=payload.sector,
            event_id=payload.event_id,
        )
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Guardrail check failure: {e}")


@router.get("/explain")
async def explain_guardrails(
    card_id: int,
    db: Session = Depends(get_db)
):
    """Return guardrail booleans and warnings for a given card id."""
    card = db.query(TradeCardV2).filter(TradeCardV2.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    return {
        "card_id": card.id,
        "symbol": card.symbol,
        "liquidity_check": card.liquidity_check,
        "position_size_check": card.position_size_check,
        "exposure_check": card.exposure_check,
        "event_window_check": card.event_window_check,
        "regime_check": card.regime_check,
        "catalyst_freshness_check": card.catalyst_freshness_check,
        "risk_warnings": card.risk_warnings or []
    }


