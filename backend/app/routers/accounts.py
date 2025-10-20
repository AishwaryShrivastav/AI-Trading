"""Account management router - Multi-account AI Trader."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import logging

from ..database import (
    get_db, Account, Mandate, FundingPlan, 
    CapitalTransaction, TradeCardV2, PositionV2
)
from ..schemas import (
    AccountCreate, AccountUpdate, AccountResponse, AccountSummary,
    MandateCreate, MandateUpdate, MandateResponse,
    FundingPlanCreate, FundingPlanUpdate, FundingPlanResponse,
    CapitalTransactionCreate, CapitalTransactionResponse,
    IntakeSessionCreate, IntakeSessionResponse, IntakeAnswer,
    IntakeSessionComplete
)
from ..services.intake_agent import intake_agent

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
logger = logging.getLogger(__name__)


# ============================================================================
# ACCOUNT CRUD
# ============================================================================

@router.post("/", response_model=AccountResponse)
async def create_account(
    account: AccountCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new trading account.
    
    An account is a logical bucket for capital allocation (e.g., "SIP—Aggressive").
    After creating, use the intake agent to set up mandate and funding plan.
    """
    try:
        # Check for duplicate name
        existing = db.query(Account).filter(
            Account.user_id == account.user_id,
            Account.name == account.name
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Account with name '{account.name}' already exists"
            )
        
        db_account = Account(
            user_id=account.user_id,
            name=account.name,
            account_type=account.account_type.value,
            description=account.description,
            status="ACTIVE"
        )
        
        db.add(db_account)
        db.commit()
        db.refresh(db_account)
        
        logger.info(f"Created account: {account.name} (ID: {db_account.id})")
        
        return db_account
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating account: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[AccountResponse])
async def list_accounts(
    user_id: str = Query("default_user"),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    List all accounts for a user.
    
    Query Parameters:
    - user_id: Filter by user (default: "default_user")
    - status: Filter by status (ACTIVE, PAUSED, CLOSED)
    """
    query = db.query(Account).filter(Account.user_id == user_id)
    
    if status:
        query = query.filter(Account.status == status)
    
    accounts = query.order_by(Account.created_at.desc()).all()
    return accounts


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific account by ID."""
    account = db.query(Account).filter(Account.id == account_id).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    return account


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    updates: AccountUpdate,
    db: Session = Depends(get_db)
):
    """Update account details (name, status, description)."""
    account = db.query(Account).filter(Account.id == account_id).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    if updates.name is not None:
        account.name = updates.name
    if updates.status is not None:
        account.status = updates.status.value
    if updates.description is not None:
        account.description = updates.description
    
    account.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(account)
    
    logger.info(f"Updated account {account_id}")
    return account


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete (close) an account.
    
    Actually sets status to CLOSED rather than deleting for audit trail.
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check for open positions
    open_positions = db.query(PositionV2).filter(
        PositionV2.account_id == account_id,
        PositionV2.closed_at.is_(None)
    ).count()
    
    if open_positions > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot close account with {open_positions} open positions"
        )
    
    account.status = "CLOSED"
    account.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"Closed account {account_id}")
    return {"status": "closed", "account_id": account_id}


@router.get("/{account_id}/summary", response_model=AccountSummary)
async def get_account_summary(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Get comprehensive account summary.
    
    Includes:
    - Account details
    - Active mandate
    - Funding plan
    - Stats (positions, pending cards, P&L, utilization)
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Get active mandate
    mandate = db.query(Mandate).filter(
        Mandate.account_id == account_id,
        Mandate.is_active == True
    ).order_by(Mandate.version.desc()).first()
    
    # Get funding plan
    funding_plan = db.query(FundingPlan).filter(
        FundingPlan.account_id == account_id
    ).first()
    
    # Calculate stats
    open_positions = db.query(PositionV2).filter(
        PositionV2.account_id == account_id,
        PositionV2.closed_at.is_(None)
    ).count()
    
    pending_cards = db.query(TradeCardV2).filter(
        TradeCardV2.account_id == account_id,
        TradeCardV2.status == "PENDING"
    ).count()
    
    # Calculate P&L
    positions = db.query(PositionV2).filter(
        PositionV2.account_id == account_id
    ).all()
    
    total_pnl = sum(
        (p.unrealized_pnl or 0) + (p.realized_pnl or 0) 
        for p in positions
    )
    
    # Calculate utilization
    utilization_percent = 0.0
    if funding_plan and funding_plan.available_cash > 0:
        deployed = funding_plan.total_deployed + funding_plan.reserved_cash
        total_capital = deployed + funding_plan.available_cash
        utilization_percent = (deployed / total_capital) * 100 if total_capital > 0 else 0
    
    return AccountSummary(
        account=account,
        mandate=mandate,
        funding_plan=funding_plan,
        stats={
            "open_positions": open_positions,
            "pending_cards": pending_cards,
            "total_pnl": total_pnl,
            "utilization_percent": utilization_percent
        }
    )


# ============================================================================
# MANDATE MANAGEMENT
# ============================================================================

@router.post("/{account_id}/mandate", response_model=MandateResponse)
async def create_mandate(
    account_id: int,
    mandate: MandateCreate,
    db: Session = Depends(get_db)
):
    """
    Create a trading mandate for an account.
    
    If a mandate already exists, this creates a new version and deactivates the old one.
    """
    # Verify account exists
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Deactivate existing mandates
    db.query(Mandate).filter(
        Mandate.account_id == account_id,
        Mandate.is_active == True
    ).update({"is_active": False})
    
    # Get next version number
    latest = db.query(Mandate).filter(
        Mandate.account_id == account_id
    ).order_by(Mandate.version.desc()).first()
    
    next_version = (latest.version + 1) if latest else 1
    
    # Create new mandate
    db_mandate = Mandate(
        account_id=account_id,
        version=next_version,
        objective=mandate.objective.value,
        risk_per_trade_percent=mandate.risk_per_trade_percent,
        max_positions=mandate.max_positions,
        max_sector_exposure_percent=mandate.max_sector_exposure_percent,
        horizon_min_days=mandate.horizon_min_days,
        horizon_max_days=mandate.horizon_max_days,
        banned_sectors=mandate.banned_sectors,
        earnings_blackout_days=mandate.earnings_blackout_days,
        liquidity_floor_adv=mandate.liquidity_floor_adv,
        min_market_cap=mandate.min_market_cap,
        allowed_strategies=mandate.allowed_strategies,
        sl_multiplier=mandate.sl_multiplier,
        tp_multiplier=mandate.tp_multiplier,
        trailing_stop_enabled=mandate.trailing_stop_enabled,
        assumption_log=mandate.assumption_log,
        summary=mandate.summary,
        is_active=True
    )
    
    db.add(db_mandate)
    db.commit()
    db.refresh(db_mandate)
    
    logger.info(f"Created mandate v{next_version} for account {account_id}")
    return db_mandate


@router.get("/{account_id}/mandate", response_model=MandateResponse)
async def get_active_mandate(
    account_id: int,
    db: Session = Depends(get_db)
):
    """Get the active mandate for an account."""
    mandate = db.query(Mandate).filter(
        Mandate.account_id == account_id,
        Mandate.is_active == True
    ).first()
    
    if not mandate:
        raise HTTPException(
            status_code=404,
            detail="No active mandate found. Use intake agent to create one."
        )
    
    return mandate


@router.put("/{account_id}/mandate", response_model=MandateResponse)
async def update_mandate(
    account_id: int,
    updates: MandateUpdate,
    db: Session = Depends(get_db)
):
    """
    Update the active mandate.
    
    Creates a new version with changes.
    """
    # Get current mandate
    current = db.query(Mandate).filter(
        Mandate.account_id == account_id,
        Mandate.is_active == True
    ).first()
    
    if not current:
        raise HTTPException(status_code=404, detail="No active mandate to update")
    
    # Deactivate current
    current.is_active = False
    
    # Create new version with updates
    new_mandate = Mandate(
        account_id=account_id,
        version=current.version + 1,
        objective=updates.objective.value if updates.objective else current.objective,
        risk_per_trade_percent=updates.risk_per_trade_percent if updates.risk_per_trade_percent is not None else current.risk_per_trade_percent,
        max_positions=updates.max_positions if updates.max_positions is not None else current.max_positions,
        max_sector_exposure_percent=updates.max_sector_exposure_percent if updates.max_sector_exposure_percent is not None else current.max_sector_exposure_percent,
        horizon_min_days=current.horizon_min_days,
        horizon_max_days=current.horizon_max_days,
        banned_sectors=updates.banned_sectors if updates.banned_sectors is not None else current.banned_sectors,
        earnings_blackout_days=current.earnings_blackout_days,
        liquidity_floor_adv=current.liquidity_floor_adv,
        min_market_cap=current.min_market_cap,
        allowed_strategies=updates.allowed_strategies if updates.allowed_strategies is not None else current.allowed_strategies,
        sl_multiplier=updates.sl_multiplier if updates.sl_multiplier is not None else current.sl_multiplier,
        tp_multiplier=updates.tp_multiplier if updates.tp_multiplier is not None else current.tp_multiplier,
        trailing_stop_enabled=updates.trailing_stop_enabled if updates.trailing_stop_enabled is not None else current.trailing_stop_enabled,
        assumption_log=current.assumption_log,
        summary=current.summary,
        is_active=True
    )
    
    db.add(new_mandate)
    db.commit()
    db.refresh(new_mandate)
    
    logger.info(f"Updated mandate to v{new_mandate.version} for account {account_id}")
    return new_mandate


# ============================================================================
# FUNDING PLAN MANAGEMENT
# ============================================================================

@router.post("/{account_id}/funding-plan", response_model=FundingPlanResponse)
async def create_funding_plan(
    account_id: int,
    plan: FundingPlanCreate,
    db: Session = Depends(get_db)
):
    """Create a funding plan for an account."""
    # Verify account exists
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check if plan already exists
    existing = db.query(FundingPlan).filter(
        FundingPlan.account_id == account_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Funding plan already exists. Use PUT to update."
        )
    
    db_plan = FundingPlan(
        account_id=account_id,
        funding_type=plan.funding_type.value,
        sip_amount=plan.sip_amount,
        sip_frequency=plan.sip_frequency.value if plan.sip_frequency else None,
        sip_start_date=plan.sip_start_date,
        sip_duration_months=plan.sip_duration_months,
        lump_sum_amount=plan.lump_sum_amount,
        lump_sum_date=plan.lump_sum_date,
        tranche_plan=plan.tranche_plan,
        carry_forward_enabled=plan.carry_forward_enabled,
        max_carry_forward_percent=plan.max_carry_forward_percent,
        emergency_buffer_percent=plan.emergency_buffer_percent,
        total_deployed=0.0,
        available_cash=0.0,
        reserved_cash=0.0
    )
    
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    
    logger.info(f"Created funding plan for account {account_id}")
    return db_plan


@router.get("/{account_id}/funding-plan", response_model=FundingPlanResponse)
async def get_funding_plan(
    account_id: int,
    db: Session = Depends(get_db)
):
    """Get the funding plan for an account."""
    plan = db.query(FundingPlan).filter(
        FundingPlan.account_id == account_id
    ).first()
    
    if not plan:
        raise HTTPException(
            status_code=404,
            detail="No funding plan found. Use intake agent to create one."
        )
    
    return plan


@router.put("/{account_id}/funding-plan", response_model=FundingPlanResponse)
async def update_funding_plan(
    account_id: int,
    updates: FundingPlanUpdate,
    db: Session = Depends(get_db)
):
    """Update funding plan (e.g., adjust SIP amount, update cash)."""
    plan = db.query(FundingPlan).filter(
        FundingPlan.account_id == account_id
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Funding plan not found")
    
    if updates.sip_amount is not None:
        plan.sip_amount = updates.sip_amount
    if updates.sip_frequency is not None:
        plan.sip_frequency = updates.sip_frequency.value
    if updates.lump_sum_amount is not None:
        plan.lump_sum_amount = updates.lump_sum_amount
    if updates.tranche_plan is not None:
        plan.tranche_plan = updates.tranche_plan
    if updates.carry_forward_enabled is not None:
        plan.carry_forward_enabled = updates.carry_forward_enabled
    if updates.max_carry_forward_percent is not None:
        plan.max_carry_forward_percent = updates.max_carry_forward_percent
    if updates.available_cash is not None:
        plan.available_cash = updates.available_cash
    
    plan.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(plan)
    
    logger.info(f"Updated funding plan for account {account_id}")
    return plan


# ============================================================================
# CAPITAL TRANSACTIONS
# ============================================================================

@router.post("/{account_id}/capital", response_model=CapitalTransactionResponse)
async def create_capital_transaction(
    account_id: int,
    transaction: CapitalTransactionCreate,
    db: Session = Depends(get_db)
):
    """
    Record a capital transaction (deposit, withdrawal, transfer).
    
    Types:
    - DEPOSIT: Add capital to account
    - WITHDRAWAL: Remove capital from account  
    - TRANSFER_IN/TRANSFER_OUT: Inter-account transfers
    """
    # Verify account exists
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Get funding plan
    funding_plan = db.query(FundingPlan).filter(
        FundingPlan.account_id == account_id
    ).first()
    
    if not funding_plan:
        raise HTTPException(status_code=404, detail="Funding plan not found")
    
    # Create transaction
    db_transaction = CapitalTransaction(
        account_id=account_id,
        transaction_type=transaction.transaction_type,
        amount=transaction.amount,
        from_account_id=transaction.from_account_id,
        to_account_id=transaction.to_account_id,
        reason=transaction.reason,
        approved_by=transaction.approved_by
    )
    
    # Update funding plan cash
    if transaction.transaction_type == "DEPOSIT":
        funding_plan.available_cash += transaction.amount
    elif transaction.transaction_type == "WITHDRAWAL":
        if funding_plan.available_cash < transaction.amount:
            raise HTTPException(
                status_code=400,
                detail="Insufficient available cash"
            )
        funding_plan.available_cash -= transaction.amount
    
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    
    logger.info(f"Capital transaction {transaction.transaction_type}: ₹{transaction.amount} for account {account_id}")
    return db_transaction


@router.get("/{account_id}/capital", response_model=List[CapitalTransactionResponse])
async def get_capital_transactions(
    account_id: int,
    limit: int = Query(50, le=1000),
    db: Session = Depends(get_db)
):
    """Get capital transaction history for an account."""
    transactions = db.query(CapitalTransaction).filter(
        CapitalTransaction.account_id == account_id
    ).order_by(CapitalTransaction.timestamp.desc()).limit(limit).all()
    
    return transactions


# ============================================================================
# INTAKE AGENT (Conversational Mandate Capture)
# ============================================================================

@router.post("/intake/start", response_model=IntakeSessionResponse)
async def start_intake_session(
    session_req: IntakeSessionCreate
):
    """
    Start a conversational intake session to capture mandate and funding plan.
    
    Returns the first question to ask the user.
    """
    try:
        response = intake_agent.start_session(
            account_name=session_req.account_name,
            account_type=session_req.account_type,
            user_id=session_req.user_id
        )
        
        logger.info(f"Started intake session: {response.session_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error starting intake session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/intake/{session_id}/answer", response_model=IntakeSessionResponse)
async def answer_intake_question(
    session_id: str,
    answer: IntakeAnswer
):
    """
    Submit an answer to the current intake question.
    
    Returns the next question or completion status.
    """
    try:
        response = intake_agent.answer_question(session_id, answer)
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing intake answer: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/intake/{session_id}/complete", response_model=IntakeSessionComplete)
async def complete_intake_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Complete the intake session and create account, mandate, and funding plan.
    
    Returns the created mandate, funding plan, and summary for confirmation.
    """
    try:
        # Generate mandate and plan from intake
        result = intake_agent.generate_mandate_and_plan(session_id)
        session = intake_agent.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Create account
        account = Account(
            user_id=session["user_id"],
            name=session["account_name"],
            account_type=session["account_type"].value,
            status="ACTIVE"
        )
        db.add(account)
        db.flush()  # Get account ID
        
        # Create mandate
        mandate_data = result["mandate_data"]
        mandate = Mandate(
            account_id=account.id,
            version=1,
            **{k: v for k, v in mandate_data.items() if k not in ["assumption_log", "summary"]},
            assumption_log=mandate_data.get("assumption_log"),
            summary=mandate_data.get("summary"),
            is_active=True
        )
        db.add(mandate)
        db.flush()
        
        # Create funding plan
        plan_data = result["funding_plan_data"]
        funding_plan = FundingPlan(
            account_id=account.id,
            **plan_data
        )
        db.add(funding_plan)
        
        db.commit()
        db.refresh(mandate)
        db.refresh(funding_plan)
        
        # Clear session
        intake_agent.clear_session(session_id)
        
        logger.info(f"Completed intake session {session_id}: Created account {account.id}")
        
        return IntakeSessionComplete(
            mandate=mandate,
            funding_plan=funding_plan,
            summary=result["summary"]
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error completing intake session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

