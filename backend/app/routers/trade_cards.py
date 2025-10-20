"""Trade card management router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import logging

from ..database import get_db, TradeCard, Order
from ..schemas import (
    TradeCardResponse,
    TradeCardApproval,
    TradeCardRejection,
    OrderResponse
)
from ..services.broker import UpstoxBroker
from ..services.audit import AuditLogger
from ..services.risk_checks import RiskChecker
from ..config import get_settings

router = APIRouter(prefix="/api/trade-cards", tags=["trade-cards"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/pending", response_model=List[TradeCardResponse])
async def get_pending_trade_cards(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get pending trade cards awaiting approval."""
    trade_cards = db.query(TradeCard).filter(
        TradeCard.status == "pending_approval"
    ).order_by(
        TradeCard.confidence.desc(),
        TradeCard.created_at.desc()
    ).limit(limit).all()
    
    return trade_cards


@router.get("/{trade_card_id}", response_model=TradeCardResponse)
async def get_trade_card(
    trade_card_id: int,
    db: Session = Depends(get_db)
):
    """Get specific trade card by ID."""
    trade_card = db.query(TradeCard).filter(TradeCard.id == trade_card_id).first()
    
    if not trade_card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    return trade_card


@router.get("/", response_model=List[TradeCardResponse])
async def get_trade_cards(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get trade cards with optional filters."""
    query = db.query(TradeCard)
    
    if status:
        query = query.filter(TradeCard.status == status)
    
    if symbol:
        query = query.filter(TradeCard.symbol == symbol)
    
    if strategy:
        query = query.filter(TradeCard.strategy == strategy)
    
    trade_cards = query.order_by(TradeCard.created_at.desc()).limit(limit).all()
    
    return trade_cards


@router.post("/{trade_card_id}/approve", response_model=OrderResponse)
async def approve_trade_card(
    trade_card_id: int,
    approval: TradeCardApproval,
    db: Session = Depends(get_db)
):
    """
    Approve a trade card and place order with broker.
    """
    # Get trade card
    trade_card = db.query(TradeCard).filter(TradeCard.id == trade_card_id).first()
    
    if not trade_card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    if trade_card.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Trade card status is {trade_card.status}, cannot approve"
        )
    
    try:
        # Initialize services
        audit_logger = AuditLogger(db)
        
        # Create trade card snapshot for audit
        trade_card_snapshot = {
            "id": trade_card.id,
            "symbol": trade_card.symbol,
            "entry_price": trade_card.entry_price,
            "quantity": trade_card.quantity,
            "stop_loss": trade_card.stop_loss,
            "take_profit": trade_card.take_profit,
            "trade_type": trade_card.trade_type,
            "confidence": trade_card.confidence
        }
        
        # Log approval
        audit_logger.log_trade_card_approved(
            trade_card_id=trade_card.id,
            user_id=approval.user_id,
            trade_card_snapshot=trade_card_snapshot,
            notes=approval.notes
        )
        
        # Update trade card status
        trade_card.status = "approved"
        trade_card.approved_at = datetime.utcnow()
        
        # Initialize broker
        broker = UpstoxBroker(
            api_key=settings.upstox_api_key,
            api_secret=settings.upstox_api_secret,
            redirect_uri=settings.upstox_redirect_uri
        )
        
        # Load tokens from database
        from ..database import Setting
        access_token = db.query(Setting).filter(
            Setting.key == "upstox_access_token"
        ).first()
        
        if access_token:
            broker.access_token = access_token.value
        else:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated with broker. Please login first."
            )
        
        # Place order
        order_response = await broker.place_order(
            symbol=trade_card.symbol,
            transaction_type=trade_card.trade_type,
            quantity=trade_card.quantity,
            order_type="LIMIT",  # Use limit order at entry price
            price=trade_card.entry_price,
            exchange="NSE",
            product="D"  # Delivery
        )
        
        broker_order_id = order_response.get("data", {}).get("order_id")
        
        # Create order record
        order = Order(
            trade_card_id=trade_card.id,
            broker_order_id=broker_order_id,
            symbol=trade_card.symbol,
            exchange="NSE",
            order_type="LIMIT",
            transaction_type=trade_card.trade_type,
            quantity=trade_card.quantity,
            price=trade_card.entry_price,
            status="placed"
        )
        
        db.add(order)
        trade_card.status = "executed"
        db.commit()
        db.refresh(order)
        
        # Log order placement
        audit_logger.log_order_placed(
            order_id=order.id,
            trade_card_id=trade_card.id,
            order_payload={
                "symbol": trade_card.symbol,
                "quantity": trade_card.quantity,
                "price": trade_card.entry_price
            },
            broker_response=order_response
        )
        
        logger.info(f"Order placed for trade card {trade_card.id}: {broker_order_id}")
        
        return order
        
    except Exception as e:
        logger.error(f"Error approving trade card: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{trade_card_id}/reject")
async def reject_trade_card(
    trade_card_id: int,
    rejection: TradeCardRejection,
    db: Session = Depends(get_db)
):
    """Reject a trade card."""
    # Get trade card
    trade_card = db.query(TradeCard).filter(TradeCard.id == trade_card_id).first()
    
    if not trade_card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    if trade_card.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Trade card status is {trade_card.status}, cannot reject"
        )
    
    try:
        # Initialize audit logger
        audit_logger = AuditLogger(db)
        
        # Create snapshot
        trade_card_snapshot = {
            "id": trade_card.id,
            "symbol": trade_card.symbol,
            "confidence": trade_card.confidence
        }
        
        # Log rejection
        audit_logger.log_trade_card_rejected(
            trade_card_id=trade_card.id,
            user_id=rejection.user_id,
            reason=rejection.reason,
            trade_card_snapshot=trade_card_snapshot
        )
        
        # Update trade card
        trade_card.status = "rejected"
        trade_card.rejected_at = datetime.utcnow()
        trade_card.rejection_reason = rejection.reason
        
        db.commit()
        
        logger.info(f"Trade card {trade_card.id} rejected: {rejection.reason}")
        
        return {"status": "rejected", "trade_card_id": trade_card.id}
        
    except Exception as e:
        logger.error(f"Error rejecting trade card: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{trade_card_id}/risk-summary")
async def get_risk_summary(
    trade_card_id: int,
    db: Session = Depends(get_db)
):
    """Get risk summary for a trade card."""
    trade_card = db.query(TradeCard).filter(TradeCard.id == trade_card_id).first()
    
    if not trade_card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    risk_checker = RiskChecker(db)
    risk_summary = risk_checker.get_risk_summary(trade_card)
    
    return risk_summary

