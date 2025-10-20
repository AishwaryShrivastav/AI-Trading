"""AI Trader API - Multi-account trading desk endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging

from ..database import get_db, TradeCardV2
from ..services.trade_card_pipeline_v2 import TradeCardPipelineV2
from ..services.ingestion.ingestion_manager import IngestionManager
from ..services.feature_builder import FeatureBuilder
from ..services.signal_generator import SignalGenerator
from ..services.allocator import Allocator
from ..services.treasury import Treasury
from ..services.risk_monitor import RiskMonitor
from ..services.playbook_manager import PlaybookManager
from ..schemas import TradeCardV2Response

router = APIRouter(prefix="/api/ai-trader", tags=["ai_trader"])
logger = logging.getLogger(__name__)


# Request Models
class GenerateSignalsRequest(BaseModel):
    """Request to generate signals."""
    symbols: List[str]
    user_id: str = "default_user"


class HotPathRequest(BaseModel):
    """Request for hot path processing."""
    event_id: int


# ============================================================================
# PIPELINE ENDPOINTS
# ============================================================================

@router.post("/pipeline/run")
async def run_full_pipeline(
    request: GenerateSignalsRequest,
    db: Session = Depends(get_db)
):
    """
    Run complete AI trading pipeline for all accounts.
    
    Steps:
    1. Ingest latest events
    2. Build features
    3. Generate signals
    4. Apply meta-labels
    5. Allocate per account
    6. Create trade cards
    
    Returns trade cards created per account.
    """
    try:
        pipeline = TradeCardPipelineV2(db)
        
        result = await pipeline.run_full_pipeline(
            symbols=request.symbols,
            user_id=request.user_id
        )
        
        return {
            "status": "success",
            "pipeline_result": result
        }
        
    except Exception as e:
        logger.error(f"Error running pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/hot-path")
async def run_hot_path(
    request: HotPathRequest,
    db: Session = Depends(get_db)
):
    """
    Hot path: Breaking news → cards in seconds.
    
    Processes high-priority event through fast-track pipeline:
    - Event → Signal → Meta-label → Allocate → Cards
    
    Target latency: < 5 seconds
    """
    try:
        pipeline = TradeCardPipelineV2(db)
        
        result = await pipeline.run_hot_path(event_id=request.event_id)
        
        return {
            "status": "success",
            "hot_path_result": result
        }
        
    except Exception as e:
        logger.error(f"Error in hot path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TRADE CARDS V2 (Multi-Account)
# ============================================================================

@router.get("/trade-cards", response_model=List[TradeCardV2Response])
async def get_trade_cards_v2(
    account_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    priority_min: Optional[int] = Query(None),
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db)
):
    """
    Get trade cards with filtering.
    
    Query Parameters:
    - account_id: Filter by account
    - status: Filter by status (PENDING, APPROVED, etc.)
    - priority_min: Minimum priority (for hot path cards)
    - limit: Max results
    """
    query = db.query(TradeCardV2)
    
    if account_id:
        query = query.filter(TradeCardV2.account_id == account_id)
    
    if status:
        query = query.filter(TradeCardV2.status == status)
    
    if priority_min is not None:
        query = query.filter(TradeCardV2.priority >= priority_min)
    
    cards = query.order_by(
        TradeCardV2.priority.desc(),
        TradeCardV2.created_at.desc()
    ).limit(limit).all()
    
    return cards


@router.post("/trade-cards/{card_id}/approve")
async def approve_trade_card_v2(
    card_id: int,
    user_id: str = "default_user",
    db: Session = Depends(get_db)
):
    """
    Approve a trade card and execute.
    
    Flow:
    1. Reserve cash
    2. Place bracket orders
    3. Update position
    4. Mark card as EXECUTED
    """
    card = db.query(TradeCardV2).filter(TradeCardV2.id == card_id).first()
    
    if not card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    if card.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Card is {card.status}, not pending"
        )
    
    try:
        # Reserve cash
        treasury = Treasury(db)
        reserved = await treasury.reserve_cash(
            account_id=card.account_id,
            amount=card.position_size_rupees
        )
        
        if not reserved:
            raise HTTPException(
                status_code=400,
                detail="Insufficient cash to reserve"
            )
        
        # Mark as approved
        card.status = "APPROVED"
        card.approved_at = datetime.utcnow()
        card.approved_by = user_id
        
        db.commit()
        db.refresh(card)
        
        logger.info(f"Approved trade card {card_id}")
        
        return {
            "status": "approved",
            "card_id": card_id,
            "symbol": card.symbol,
            "message": "Trade card approved. Execute via execution endpoint."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error approving card {card_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade-cards/{card_id}/reject")
async def reject_trade_card_v2(
    card_id: int,
    reason: str,
    user_id: str = "default_user",
    db: Session = Depends(get_db)
):
    """Reject a trade card."""
    card = db.query(TradeCardV2).filter(TradeCardV2.id == card_id).first()
    
    if not card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    card.status = "REJECTED"
    card.rejected_at = datetime.utcnow()
    card.rejection_reason = reason
    
    db.commit()
    
    logger.info(f"Rejected trade card {card_id}: {reason}")
    
    return {
        "status": "rejected",
        "card_id": card_id,
        "reason": reason
    }


# ============================================================================
# RISK MONITORING
# ============================================================================

@router.get("/risk/snapshot")
async def get_risk_snapshot(
    account_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get current risk snapshot.
    
    If account_id is provided, returns account-specific snapshot.
    Otherwise, returns portfolio-wide snapshot.
    """
    try:
        monitor = RiskMonitor(db)
        snapshot = await monitor.capture_snapshot(account_id)
        
        return {
            "status": "success",
            "snapshot": {
                "account_id": snapshot.account_id,
                "total_open_risk": snapshot.total_open_risk,
                "total_unrealized_pnl": snapshot.total_unrealized_pnl,
                "open_positions_count": snapshot.open_positions_count,
                "daily_pnl": snapshot.daily_realized_pnl + snapshot.total_unrealized_pnl,
                "timestamp": snapshot.timestamp.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error capturing risk snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk/check-kill-switches")
async def check_kill_switches(
    account_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Check kill switches and trigger if needed.
    
    Returns list of triggered switches.
    """
    try:
        monitor = RiskMonitor(db)
        triggered = await monitor.check_kill_switches(account_id)
        
        return {
            "status": "success",
            "triggered_count": len(triggered),
            "triggered_switches": triggered
        }
        
    except Exception as e:
        logger.error(f"Error checking kill switches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk/metrics")
async def get_risk_metrics(
    account_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive risk metrics.
    
    Includes:
    - Current risk exposure
    - P&L
    - Kill switch status
    - Position counts
    """
    try:
        monitor = RiskMonitor(db)
        metrics = await monitor.get_risk_metrics(account_id)
        
        return {
            "status": "success",
            "metrics": metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting risk metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TREASURY OPERATIONS
# ============================================================================

@router.get("/treasury/summary")
async def get_treasury_summary(
    db: Session = Depends(get_db)
):
    """
    Get portfolio-wide capital summary.
    
    Shows:
    - Total capital across all accounts
    - Deployed vs available
    - Utilization %
    """
    try:
        treasury = Treasury(db)
        summary = await treasury.get_portfolio_summary()
        
        return {
            "status": "success",
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error getting treasury summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/treasury/process-sip/{account_id}")
async def process_sip_installment(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Process SIP installment for an account.
    
    Adds monthly/weekly SIP amount to available cash.
    """
    try:
        treasury = Treasury(db)
        result = await treasury.process_sip_installment(account_id)
        
        return {
            "status": "success",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error processing SIP: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PLAYBOOKS
# ============================================================================

@router.get("/playbooks")
async def list_playbooks(
    event_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    List all playbooks.
    
    Optionally filter by event_type.
    """
    from ..database import Playbook
    
    query = db.query(Playbook).filter(Playbook.is_active == True)
    
    if event_type:
        query = query.filter(Playbook.event_type == event_type)
    
    playbooks = query.all()
    
    return {
        "status": "success",
        "count": len(playbooks),
        "playbooks": [
            {
                "id": pb.id,
                "name": pb.name,
                "event_type": pb.event_type,
                "priority_boost": pb.priority_boost,
                "sl_multiplier": pb.sl_multiplier_override,
                "tp_multiplier": pb.tp_multiplier_override
            }
            for pb in playbooks
        ]
    }

