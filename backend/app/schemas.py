"""Pydantic schemas for API request/response validation."""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# Enums
class TradeType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeCardStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PLACED = "placed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETE = "complete"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


# Trade Card Schemas
class TradeCardBase(BaseModel):
    symbol: str
    exchange: str = "NSE"
    entry_price: float
    quantity: int
    stop_loss: float
    take_profit: float
    trade_type: TradeType
    strategy: Optional[str] = None
    horizon_days: int = 3
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    evidence: Optional[str] = None
    risks: Optional[str] = None


class TradeCardCreate(TradeCardBase):
    model_version: Optional[str] = None


class TradeCardUpdate(BaseModel):
    entry_price: Optional[float] = None
    quantity: Optional[int] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: Optional[TradeCardStatus] = None


class TradeCardResponse(TradeCardBase):
    id: int
    status: str
    liquidity_check: bool
    position_size_check: bool
    exposure_check: bool
    event_window_check: bool
    risk_warnings: Optional[List[str]] = None
    model_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class TradeCardApproval(BaseModel):
    trade_card_id: int
    user_id: str = "default_user"
    notes: Optional[str] = None


class TradeCardRejection(BaseModel):
    trade_card_id: int
    reason: str
    user_id: str = "default_user"


# Order Schemas
class OrderBase(BaseModel):
    symbol: str
    exchange: str = "NSE"
    order_type: OrderType
    transaction_type: TradeType
    quantity: int
    price: Optional[float] = None
    trigger_price: Optional[float] = None


class OrderCreate(OrderBase):
    trade_card_id: int


class OrderResponse(OrderBase):
    id: int
    trade_card_id: int
    broker_order_id: Optional[str] = None
    status: str
    status_message: Optional[str] = None
    filled_quantity: int = 0
    average_price: Optional[float] = None
    placed_at: datetime
    updated_at: datetime
    filled_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Market Data Schemas
class OHLCVData(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    metadata: Optional[Dict[str, Any]] = None


class MarketDataRequest(BaseModel):
    symbols: List[str]
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    interval: str = "1D"


# Signal Schemas
class SignalCandidate(BaseModel):
    symbol: str
    strategy: str
    score: float
    entry_price: float
    suggested_sl: Optional[float] = None
    suggested_tp: Optional[float] = None
    reasoning: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SignalGenerationRequest(BaseModel):
    strategies: Optional[List[str]] = None  # If None, run all
    symbols: Optional[List[str]] = None  # If None, scan universe
    force_refresh: bool = False


class SignalGenerationResponse(BaseModel):
    candidates_found: int
    trade_cards_created: int
    timestamp: datetime
    strategies_run: List[str]


# Position Schemas
class PositionResponse(BaseModel):
    id: int
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: float = 0.0
    opened_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Report Schemas
class EODReportResponse(BaseModel):
    date: str
    total_trades: int
    open_positions: int
    closed_positions: int
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    win_rate: float
    guardrail_hits: Dict[str, int]
    top_performers: List[Dict[str, Any]]
    worst_performers: List[Dict[str, Any]]
    upcoming_events: List[Dict[str, Any]]


class MonthlyReportResponse(BaseModel):
    month: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: Optional[float] = None
    strategy_performance: Dict[str, Dict[str, Any]]
    compliance_summary: Dict[str, int]
    best_trade: Optional[Dict[str, Any]] = None
    worst_trade: Optional[Dict[str, Any]] = None


# Audit Log Schemas
class AuditLogCreate(BaseModel):
    action_type: str
    user_id: str = "system"
    trade_card_id: Optional[int] = None
    order_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    meta_data: Optional[Dict[str, Any]] = None
    model_version: Optional[str] = None
    strategy_version: Optional[str] = None


class AuditLogResponse(BaseModel):
    id: int
    action_type: str
    user_id: str
    trade_card_id: Optional[int] = None
    order_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    meta_data: Optional[Dict[str, Any]] = None
    timestamp: datetime
    
    class Config:
        from_attributes = True


# Authentication Schemas
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None


# Settings Schemas
class SettingResponse(BaseModel):
    key: str
    value: Any
    description: Optional[str] = None
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Health Check
class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str = "1.0.0"
    database: str
    broker: str
    llm_provider: str


# ============================================================================
# MULTI-ACCOUNT AI TRADER SCHEMAS
# ============================================================================

# Enums for Multi-Account System
class AccountType(str, Enum):
    SIP = "SIP"
    LUMP_SUM = "LUMP_SUM"
    EVENT_TACTICAL = "EVENT_TACTICAL"
    HYBRID = "HYBRID"


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class Objective(str, Enum):
    MAX_PROFIT = "MAX_PROFIT"
    RISK_MINIMIZED = "RISK_MINIMIZED"
    BALANCED = "BALANCED"


class FundingType(str, Enum):
    SIP = "SIP"
    LUMP_SUM = "LUMP_SUM"
    HYBRID = "HYBRID"


class SIPFrequency(str, Enum):
    MONTHLY = "MONTHLY"
    WEEKLY = "WEEKLY"
    FORTNIGHTLY = "FORTNIGHTLY"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


# Account Schemas
class AccountBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    account_type: AccountType
    description: Optional[str] = None


class AccountCreate(AccountBase):
    user_id: str = "default_user"


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[AccountStatus] = None
    description: Optional[str] = None


class AccountResponse(AccountBase):
    id: int
    user_id: str
    status: AccountStatus
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Mandate Schemas
class MandateBase(BaseModel):
    objective: Objective
    risk_per_trade_percent: float = Field(..., ge=0.1, le=5.0)
    max_positions: int = Field(..., ge=1, le=50)
    max_sector_exposure_percent: float = Field(..., ge=10.0, le=100.0)
    horizon_min_days: int = Field(..., ge=1, le=30)
    horizon_max_days: int = Field(..., ge=1, le=365)
    banned_sectors: Optional[List[str]] = []
    earnings_blackout_days: int = Field(2, ge=0, le=7)
    liquidity_floor_adv: Optional[float] = 1000000.0
    min_market_cap: Optional[float] = 100.0  # In crores
    allowed_strategies: Optional[List[str]] = ["momentum", "mean_reversion"]
    sl_multiplier: float = Field(2.0, ge=1.0, le=5.0)
    tp_multiplier: float = Field(4.0, ge=1.5, le=10.0)
    trailing_stop_enabled: bool = False


class MandateCreate(MandateBase):
    account_id: int
    assumption_log: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None


class MandateUpdate(BaseModel):
    objective: Optional[Objective] = None
    risk_per_trade_percent: Optional[float] = Field(None, ge=0.1, le=5.0)
    max_positions: Optional[int] = Field(None, ge=1, le=50)
    max_sector_exposure_percent: Optional[float] = Field(None, ge=10.0, le=100.0)
    banned_sectors: Optional[List[str]] = None
    allowed_strategies: Optional[List[str]] = None
    sl_multiplier: Optional[float] = Field(None, ge=1.0, le=5.0)
    tp_multiplier: Optional[float] = Field(None, ge=1.5, le=10.0)
    trailing_stop_enabled: Optional[bool] = None


class MandateResponse(MandateBase):
    id: int
    account_id: int
    version: int
    assumption_log: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True


# Funding Plan Schemas
class FundingPlanBase(BaseModel):
    funding_type: FundingType
    # SIP fields
    sip_amount: Optional[float] = Field(None, ge=500.0)
    sip_frequency: Optional[SIPFrequency] = None
    sip_start_date: Optional[datetime] = None
    sip_duration_months: Optional[int] = Field(None, ge=1, le=600)
    # Lump sum fields
    lump_sum_amount: Optional[float] = Field(None, ge=1000.0)
    lump_sum_date: Optional[datetime] = None
    tranche_plan: Optional[List[Dict[str, Any]]] = None
    # Capital rules
    carry_forward_enabled: bool = True
    max_carry_forward_percent: float = Field(20.0, ge=0.0, le=100.0)
    emergency_buffer_percent: float = Field(5.0, ge=0.0, le=50.0)


class FundingPlanCreate(FundingPlanBase):
    account_id: int


class FundingPlanUpdate(BaseModel):
    sip_amount: Optional[float] = Field(None, ge=500.0)
    sip_frequency: Optional[SIPFrequency] = None
    lump_sum_amount: Optional[float] = Field(None, ge=1000.0)
    tranche_plan: Optional[List[Dict[str, Any]]] = None
    carry_forward_enabled: Optional[bool] = None
    max_carry_forward_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    available_cash: Optional[float] = None


class FundingPlanResponse(FundingPlanBase):
    id: int
    account_id: int
    total_deployed: float
    available_cash: float
    reserved_cash: float
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Capital Transaction Schemas
class CapitalTransactionBase(BaseModel):
    transaction_type: str  # DEPOSIT, WITHDRAWAL, TRANSFER_IN, TRANSFER_OUT
    amount: float = Field(..., gt=0.0)
    reason: Optional[str] = None


class CapitalTransactionCreate(CapitalTransactionBase):
    account_id: int
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    approved_by: str = "default_user"


class CapitalTransactionResponse(CapitalTransactionBase):
    id: int
    account_id: int
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    approved_by: str
    timestamp: datetime
    
    class Config:
        from_attributes = True


# Enhanced Trade Card V2 Schemas
class TradeCardV2Base(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    exchange: str = "NSE"
    direction: Direction
    entry_price: float = Field(..., gt=0.0)
    quantity: int = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0.0)
    take_profit: float = Field(..., gt=0.0)
    strategy: str
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    edge: Optional[float] = None
    horizon_days: int = Field(3, ge=1, le=30)


class TradeCardV2Create(TradeCardV2Base):
    account_id: int
    signal_id: Optional[int] = None
    thesis: Optional[str] = None
    evidence_links: Optional[List[Dict[str, Any]]] = None
    risks: Optional[str] = None
    trailing_stop_config: Optional[Dict[str, Any]] = None
    tranche_config: Optional[List[Dict[str, Any]]] = None
    playbook_id: Optional[int] = None
    playbook_overrides: Optional[Dict[str, Any]] = None
    model_version: Optional[str] = None


class TradeCardV2Update(BaseModel):
    entry_price: Optional[float] = Field(None, gt=0.0)
    quantity: Optional[int] = Field(None, gt=0)
    stop_loss: Optional[float] = Field(None, gt=0.0)
    take_profit: Optional[float] = Field(None, gt=0.0)
    status: Optional[str] = None
    priority: Optional[int] = None


class TradeCardV2Response(TradeCardV2Base):
    id: int
    account_id: int
    signal_id: Optional[int] = None
    position_size_rupees: Optional[float] = None
    thesis: Optional[str] = None
    evidence_links: Optional[List[Dict[str, Any]]] = None
    risks: Optional[str] = None
    risk_amount: Optional[float] = None
    reward_amount: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    # Guardrails
    liquidity_check: bool
    position_size_check: bool
    exposure_check: bool
    event_window_check: bool
    regime_check: bool
    catalyst_freshness_check: bool
    risk_warnings: Optional[List[str]] = None
    # Status
    status: str
    priority: int
    model_version: Optional[str] = None
    judge_rationale: Optional[str] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


# Intake Agent Schemas (for conversational mandate capture)
class IntakeQuestion(BaseModel):
    question_id: str
    question_text: str
    field_name: str
    options: Optional[List[str]] = None
    validation_type: str = "text"  # text, number, choice, boolean
    default_value: Optional[Any] = None


class IntakeAnswer(BaseModel):
    question_id: str
    answer: Any


class IntakeSessionCreate(BaseModel):
    account_name: str
    account_type: AccountType
    user_id: str = "default_user"


class IntakeSessionResponse(BaseModel):
    session_id: str
    account_name: str
    account_type: AccountType
    current_question: IntakeQuestion
    answers_collected: int
    total_questions: int
    is_complete: bool


class IntakeSessionComplete(BaseModel):
    mandate: MandateResponse
    funding_plan: FundingPlanResponse
    summary: str


# Account Summary (dashboard view)
class AccountSummary(BaseModel):
    account: AccountResponse
    mandate: Optional[MandateResponse] = None
    funding_plan: Optional[FundingPlanResponse] = None
    stats: Dict[str, Any] = {
        "open_positions": 0,
        "pending_cards": 0,
        "total_pnl": 0.0,
        "utilization_percent": 0.0
    }

