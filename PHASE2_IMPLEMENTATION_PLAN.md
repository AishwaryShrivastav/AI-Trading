# Phase 2 Implementation Plan - Production Ready

## Executive Summary

Complete Phase 2 implementation with production-grade requirements: real data sources, comprehensive error handling, observability, security, and extensive testing. Zero mocks in production paths.

**Timeline:** 32 days (6-7 weeks)  
**Effort:** ~240 engineering hours  
**Risk Level:** Medium (multiple external dependencies)

---

## 🧭 1. PRIORITY ROADMAP

| Priority | Title | Why Now | Impact | Risks | Dependencies | Timeline |
|----------|-------|---------|--------|-------|--------------|----------|
| **P1** | Foundations & Guardrails | Safety before expansion | ✅ Trust, prevent bad trades | Low | Existing pipeline & DB | Days 1-3 |
| **P1** | Derivatives & Options | Missing major alpha signals | 🚀 Real-world alpha, hedging | Medium | Upstox/NSE APIs | Days 4-9 |
| **P1** | Flows & Policy Awareness | Institutional context needed | 🔍 Macro + smart money insight | Medium | NSDL, RBI, PIB APIs | Days 10-14 |
| **P1** | Playbooks v2 + Agents | Explainability & automation | 📝 Transparency, dynamic rules | Medium | LLM provider | Days 15-20 |
| **P2** | Portfolio Brain | Capital optimization | 💼 Full portfolio intelligence | High | Risk monitor, positions | Days 21-25 |
| **P2** | Treasury Choreography | Capital efficiency | 💸 Higher ROI, controlled flow | Medium | Treasury, allocator | Days 26-28 |
| **P3** | Learning Loop & Observability | Adaptive improvement | 📊 Visibility, self-improvement | Low | Metrics layer | Days 29-32 |

---

## 🧱 STAGE 1: P1.1 - Foundations & Guardrails (Days 1-3)

### Problem Statement
- ❌ Hardcoded `True` guardrails → blind trust in invalid trades
- ❌ Missing `MarketDataCache` import → allocator runtime failure
- ❌ No calendar feed → event window checks are stubs
- ❌ No sector mapping → exposure checks incomplete
- ❌ Broker dependency unclear → pipeline fails to inject upstox_service

### Desired Outcomes (DoD)
✅ All 6 guardrails use real checks with actual data sources  
✅ Allocator fully functional with `MarketDataCache` import fixed  
✅ Risk warnings block execution when severity == CRITICAL  
✅ Guardrail API endpoint with auth and rate limiting  
✅ Frontend displays guardrail status with "Explain" modal  
✅ Database migrations for new columns  
✅ Metrics: `guardrail_pass_ratio`, `guardrail_latency_ms`, `blocked_cards_total`  
✅ 20+ test cases covering all guardrails  

### Architecture / UI Changes

**Backend:**
- New service: `backend/app/services/risk_evaluation.py` (dataclasses with proper typing)
- New ingestion: `backend/app/services/ingestion/calendar_feed.py` (NSE earnings calendar)
- New ingestion: `backend/app/services/ingestion/nse_master.py` (symbol → sector mapping)
- Enhanced: `backend/app/services/risk_checks.py` (real checks)
- Enhanced: `backend/app/services/trade_card_pipeline_v2.py` (integration)
- New router: `backend/app/routers/guardrails.py` (API endpoints)

**Frontend:**
- Enhanced: `frontend/static/js/app.js` (guardrail chips in card view)
- New: Guardrail explain modal with detailed warnings
- New CSS: `.guardrail.pass`, `.guardrail.fail`, `.guardrail.warning`

**Database:**
- New table: `earnings_calendar` (symbol, date, event_type, source)
- New table: `symbol_master` (symbol, sector, industry, exchange, isin)
- Enhanced: `trade_cards_v2` - ensure all guardrail boolean fields exist

### Data Contracts

#### RiskEvaluationResult
```json
{
  "liquidity_check": true,
  "position_size_check": true,
  "exposure_check": false,
  "event_window_check": true,
  "regime_check": true,
  "catalyst_freshness_check": true,
  "risk_warnings": [
    {
      "type": "CRITICAL",
      "message": "Sector exposure exceeds 30% limit (current: 35%)",
      "code": "SECTOR_EXPOSURE_EXCEEDED",
      "details": {"current_exposure": 0.35, "limit": 0.30, "sector": "IT"}
    }
  ],
  "passed_all": false,
  "has_critical_failures": true,
  "timestamp": "2025-10-22T09:30:00+05:30",
  "account_id": 1,
  "symbol": "INFY",
  "evaluation_duration_ms": 45.2
}
```

#### GuardrailCheckRequest
```json
{
  "symbol": "INFY",
  "account_id": 1,
  "quantity": 100,
  "entry_price": 1450.50,
  "stop_loss": 1420.00,
  "direction": "LONG",
  "exchange": "NSE",
  "sector": "IT",
  "event_id": 123
}
```

### API Changes

#### New Endpoints

**1. POST /api/guardrails/check**
- Auth: Required (JWT)
- Rate Limit: 30 req/min per IP
- Request: `GuardrailCheckRequest`
- Response: `RiskEvaluationResult`
- Error Codes: 422 (validation), 503 (upstream failure)

**2. GET /api/guardrails/explain?card_id={id}**
- Auth: Required
- Returns: Full risk warnings with context for a trade card
- Response: `{"card_id": 1, "guardrails": {...}, "warnings": [...]}`

### Backend Implementation

#### 1.1 Fix Import Bug in allocator.py

**File:** `backend/app/services/allocator.py:6`

```python
# OLD
from ..database import Account, Mandate, FundingPlan, Signal, PositionV2, Feature

# NEW
from ..database import Account, Mandate, FundingPlan, Signal, PositionV2, Feature, MarketDataCache
```

#### 1.2 Create RiskEvaluationResult with Proper Typing

**New File:** `backend/app/services/risk_evaluation.py`

```python
"""Risk evaluation dataclasses with production-grade typing."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
import pytz

IST = pytz.timezone('Asia/Kolkata')

class GuardrailSeverity(str, Enum):
    """Severity levels for guardrail failures."""
    CRITICAL = "CRITICAL"  # Blocks trade completely
    WARNING = "WARNING"    # Shows warning but allows approval
    INFO = "INFO"          # Informational only

@dataclass
class RiskWarning:
    """Structured risk warning with traceability."""
    type: GuardrailSeverity
    message: str
    code: str  # e.g., "LIQUIDITY_BELOW_THRESHOLD", "SECTOR_EXPOSURE_EXCEEDED"
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "message": self.message,
            "code": self.code,
            "details": self.details or {}
        }

@dataclass
class RiskEvaluationResult:
    """Complete guardrail evaluation result."""
    # Individual checks
    liquidity_check: bool
    position_size_check: bool
    exposure_check: bool
    event_window_check: bool
    regime_check: bool
    catalyst_freshness_check: bool
    
    # Warnings and metadata
    risk_warnings: List[RiskWarning] = field(default_factory=list)
    passed_all: bool = True
    has_critical_failures: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(IST))
    
    # Context for debugging
    account_id: Optional[int] = None
    symbol: Optional[str] = None
    evaluation_duration_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "liquidity_check": self.liquidity_check,
            "position_size_check": self.position_size_check,
            "exposure_check": self.exposure_check,
            "event_window_check": self.event_window_check,
            "regime_check": self.regime_check,
            "catalyst_freshness_check": self.catalyst_freshness_check,
            "risk_warnings": [w.to_dict() for w in self.risk_warnings],
            "passed_all": self.passed_all,
            "has_critical_failures": self.has_critical_failures,
            "timestamp": self.timestamp.isoformat(),
            "account_id": self.account_id,
            "symbol": self.symbol,
            "evaluation_duration_ms": self.evaluation_duration_ms
        }
```

#### 1.3 Create Calendar Feed Ingestion

**New File:** `backend/app/services/ingestion/calendar_feed.py`

```python
"""NSE earnings and corporate action calendar ingestion."""
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from ...database import Base, Column, Integer, String, Date, DateTime
import logging

logger = logging.getLogger(__name__)

# Database model
class EarningsCalendar(Base):
    __tablename__ = "earnings_calendar"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    event_date = Column(Date, nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # EARNINGS, DIVIDEND, AGM, etc.
    source = Column(String(100))
    created_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))

class CalendarFeed:
    """Fetch earnings and corporate action calendar from NSE."""
    
    NSE_CALENDAR_URL = "https://www.nseindia.com/api/corporate-announcements"
    
    def __init__(self, db: Session):
        self.db = db
    
    async def fetch_upcoming_events(self, lookback_days: int = 7) -> List[Dict[str, Any]]:
        """Fetch events from NSE for next N days."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.NSE_CALENDAR_URL, headers=headers) as resp:
                    if resp.status != 200:
                        logger.error(f"NSE calendar fetch failed: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    events = self._parse_nse_events(data, lookback_days)
                    
                    # Store in DB
                    for event in events:
                        cal_entry = EarningsCalendar(**event)
                        self.db.merge(cal_entry)
                    self.db.commit()
                    
                    logger.info(f"Fetched {len(events)} calendar events")
                    return events
        
        except Exception as e:
            logger.error(f"Calendar feed error: {e}")
            return []
    
    def _parse_nse_events(self, data: Dict, lookback_days: int) -> List[Dict[str, Any]]:
        """Parse NSE API response into structured events."""
        events = []
        cutoff_date = datetime.now() + timedelta(days=lookback_days)
        
        # Parse based on NSE API structure (adjust as needed)
        for item in data.get("data", []):
            event_date_str = item.get("date")
            if not event_date_str:
                continue
            
            event_date = datetime.strptime(event_date_str, "%d-%b-%Y").date()
            if event_date > cutoff_date.date():
                continue
            
            events.append({
                "symbol": item.get("symbol"),
                "event_date": event_date,
                "event_type": item.get("purpose", "UNKNOWN"),
                "source": "NSE"
            })
        
        return events
    
    def has_upcoming_event(self, symbol: str, days_ahead: int = 2) -> bool:
        """Check if symbol has event within N days."""
        cutoff = datetime.now().date() + timedelta(days=days_ahead)
        event = self.db.query(EarningsCalendar).filter(
            EarningsCalendar.symbol == symbol,
            EarningsCalendar.event_date <= cutoff,
            EarningsCalendar.event_date >= datetime.now().date()
        ).first()
        
        return event is not None
```

#### 1.4 Create NSE Master for Sector Mapping

**New File:** `backend/app/services/ingestion/nse_master.py`

```python
"""NSE master equity list for symbol → sector mapping."""
import aiohttp
import pandas as pd
from sqlalchemy.orm import Session
from ...database import Base, Column, Integer, String, DateTime
from datetime import datetime
import pytz
import logging

logger = logging.getLogger(__name__)

class SymbolMaster(Base):
    __tablename__ = "symbol_master"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    company_name = Column(String(200))
    sector = Column(String(100), index=True)
    industry = Column(String(100))
    exchange = Column(String(10), default="NSE")
    isin = Column(String(20))
    updated_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))

class NSEMasterFeed:
    """Fetch and maintain NSE equity master list."""
    
    NSE_EQUITY_LIST = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    
    def __init__(self, db: Session):
        self.db = db
    
    async def fetch_and_update(self) -> int:
        """Download NSE equity master and update database."""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.NSE_EQUITY_LIST, headers=headers) as resp:
                    if resp.status != 200:
                        logger.error(f"NSE master fetch failed: {resp.status}")
                        return 0
                    
                    content = await resp.text()
                    df = pd.read_csv(pd.io.common.StringIO(content))
                    
                    count = 0
                    for _, row in df.iterrows():
                        master_entry = SymbolMaster(
                            symbol=row["SYMBOL"],
                            company_name=row.get("NAME OF COMPANY", ""),
                            sector=row.get("SECTOR", "UNKNOWN"),
                            industry=row.get("INDUSTRY", "UNKNOWN"),
                            isin=row.get("ISIN NUMBER", ""),
                            exchange="NSE"
                        )
                        self.db.merge(master_entry)
                        count += 1
                    
                    self.db.commit()
                    logger.info(f"Updated {count} symbols in master")
                    return count
        
        except Exception as e:
            logger.error(f"NSE master update error: {e}")
            return 0
    
    def get_sector(self, symbol: str) -> str:
        """Get sector for a symbol."""
        master = self.db.query(SymbolMaster).filter(SymbolMaster.symbol == symbol).first()
        return master.sector if master else "UNKNOWN"
```

#### 1.5 Implement Real Guardrail Checks

**File:** `backend/app/services/risk_checks.py` (Major Enhancement)

```python
"""Production-grade guardrail checks with real data sources."""
import time
from datetime import datetime, timedelta
import pytz
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from .risk_evaluation import RiskEvaluationResult, RiskWarning, GuardrailSeverity
from .ingestion.calendar_feed import CalendarFeed, EarningsCalendar
from .ingestion.nse_master import NSEMasterFeed, SymbolMaster
from ..database import MarketDataCache, PositionV2, Mandate, Feature, Event
import logging

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class RiskChecker:
    """Production-grade risk checker with comprehensive guardrails."""
    
    # Configuration constants
    ADV_LOOKBACK_DAYS = 20  # Average Daily Volume lookback
    ADV_MIN_LIQUIDITY_RATIO = 0.05  # Trade should be <= 5% of ADV
    EVENT_BLACKOUT_DAYS = 2  # Days before event to avoid trading
    CATALYST_FRESHNESS_HOURS = 24  # Hot-path events must be < 24h old
    MAX_SECTOR_EXPOSURE = 0.30  # 30% max in single sector
    
    def __init__(self, db: Session, broker=None):
        self.db = db
        self.broker = broker
        self.calendar_feed = CalendarFeed(db)
        self.nse_master = NSEMasterFeed(db)
    
    async def run_all_checks(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        trade_type: str,
        exchange: str = "NSE",
        account_id: Optional[int] = None,
        sector: Optional[str] = None,
        event_id: Optional[int] = None
    ) -> RiskEvaluationResult:
        """Run all guardrail checks and return structured result."""
        start_time = time.time()
        warnings = []
        
        # Resolve sector if not provided
        if not sector:
            sector = self.nse_master.get_sector(symbol)
        
        # Check 1: Liquidity
        liquidity_ok = await self.check_liquidity(symbol, quantity, warnings)
        
        # Check 2: Position Size Risk
        position_size_ok = await self.check_position_size_risk(
            account_id, entry_price, stop_loss, quantity, warnings
        )
        
        # Check 3: Sector Exposure
        exposure_ok = await self.check_sector_exposure(
            account_id, sector, entry_price * quantity, warnings
        )
        
        # Check 4: Event Window
        event_window_ok = await self.check_event_window(symbol, warnings)
        
        # Check 5: Regime Compatibility
        regime_ok = await self.check_regime_compatibility(symbol, account_id, warnings)
        
        # Check 6: Catalyst Freshness (for hot path)
        catalyst_ok = await self.check_catalyst_freshness(event_id, warnings)
        
        # Aggregate results
        all_checks = [
            liquidity_ok, position_size_ok, exposure_ok,
            event_window_ok, regime_ok, catalyst_ok
        ]
        passed_all = all(all_checks)
        has_critical = any(w.type == GuardrailSeverity.CRITICAL for w in warnings)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return RiskEvaluationResult(
            liquidity_check=liquidity_ok,
            position_size_check=position_size_ok,
            exposure_check=exposure_ok,
            event_window_check=event_window_ok,
            regime_check=regime_ok,
            catalyst_freshness_check=catalyst_ok,
            risk_warnings=warnings,
            passed_all=passed_all and not has_critical,
            has_critical_failures=has_critical,
            timestamp=datetime.now(IST),
            account_id=account_id,
            symbol=symbol,
            evaluation_duration_ms=round(duration_ms, 2)
        )
    
    async def check_liquidity(
        self, symbol: str, quantity: int, warnings: list
    ) -> bool:
        """Check if trade size is reasonable vs average daily volume."""
        try:
            # Get last 20 days of volume data
            cutoff_date = datetime.now(IST) - timedelta(days=self.ADV_LOOKBACK_DAYS)
            
            volume_data = self.db.query(MarketDataCache.volume).filter(
                and_(
                    MarketDataCache.symbol == symbol,
                    MarketDataCache.ts >= cutoff_date
                )
            ).all()
            
            if not volume_data or len(volume_data) < 10:
                warnings.append(RiskWarning(
                    type=GuardrailSeverity.WARNING,
                    message=f"Insufficient volume history for {symbol}",
                    code="INSUFFICIENT_VOLUME_DATA",
                    details={"days_found": len(volume_data)}
                ))
                return True  # Allow but warn
            
            avg_daily_volume = sum(v[0] for v in volume_data) / len(volume_data)
            trade_ratio = quantity / avg_daily_volume
            
            if trade_ratio > self.ADV_MIN_LIQUIDITY_RATIO:
                warnings.append(RiskWarning(
                    type=GuardrailSeverity.CRITICAL,
                    message=f"Trade size {quantity} exceeds {self.ADV_MIN_LIQUIDITY_RATIO*100}% of ADV",
                    code="LIQUIDITY_BELOW_THRESHOLD",
                    details={
                        "trade_quantity": quantity,
                        "avg_daily_volume": int(avg_daily_volume),
                        "ratio": round(trade_ratio, 4),
                        "threshold": self.ADV_MIN_LIQUIDITY_RATIO
                    }
                ))
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Liquidity check error: {e}")
            warnings.append(RiskWarning(
                type=GuardrailSeverity.WARNING,
                message="Liquidity check failed",
                code="LIQUIDITY_CHECK_ERROR"
            ))
            return True  # Fail open on errors
    
    async def check_position_size_risk(
        self, account_id: Optional[int], entry_price: float,
        stop_loss: float, quantity: int, warnings: list
    ) -> bool:
        """Check if position risk is within mandate limits."""
        if not account_id:
            return True
        
        try:
            mandate = self.db.query(Mandate).filter(
                Mandate.account_id == account_id
            ).first()
            
            if not mandate:
                return True
            
            # Calculate risk per trade
            position_value = entry_price * quantity
            max_loss = abs(entry_price - stop_loss) * quantity
            risk_percent = (max_loss / mandate.total_capital) * 100
            
            if risk_percent > mandate.risk_per_trade_percent:
                warnings.append(RiskWarning(
                    type=GuardrailSeverity.CRITICAL,
                    message=f"Risk {risk_percent:.2f}% exceeds mandate limit {mandate.risk_per_trade_percent}%",
                    code="POSITION_SIZE_EXCEEDED",
                    details={
                        "risk_percent": round(risk_percent, 2),
                        "limit_percent": mandate.risk_per_trade_percent,
                        "max_loss": round(max_loss, 2),
                        "total_capital": mandate.total_capital
                    }
                ))
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Position size check error: {e}")
            return True
    
    async def check_sector_exposure(
        self, account_id: Optional[int], sector: str,
        new_position_value: float, warnings: list
    ) -> bool:
        """Check if adding this trade exceeds sector exposure limits."""
        if not account_id or sector == "UNKNOWN":
            return True
        
        try:
            mandate = self.db.query(Mandate).filter(
                Mandate.account_id == account_id
            ).first()
            
            if not mandate:
                return True
            
            # Get current sector exposure
            positions = self.db.query(PositionV2).filter(
                and_(
                    PositionV2.account_id == account_id,
                    PositionV2.status == "OPEN"
                )
            ).all()
            
            sector_value = 0
            for pos in positions:
                pos_sector = self.nse_master.get_sector(pos.symbol)
                if pos_sector == sector:
                    sector_value += pos.current_value or 0
            
            # Add new position
            sector_value += new_position_value
            sector_exposure = sector_value / mandate.total_capital
            
            if sector_exposure > self.MAX_SECTOR_EXPOSURE:
                warnings.append(RiskWarning(
                    type=GuardrailSeverity.CRITICAL,
                    message=f"Sector {sector} exposure {sector_exposure:.1%} exceeds {self.MAX_SECTOR_EXPOSURE:.0%} limit",
                    code="SECTOR_EXPOSURE_EXCEEDED",
                    details={
                        "sector": sector,
                        "current_exposure": round(sector_exposure, 3),
                        "limit": self.MAX_SECTOR_EXPOSURE,
                        "sector_value": round(sector_value, 2)
                    }
                ))
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Sector exposure check error: {e}")
            return True
    
    async def check_event_window(self, symbol: str, warnings: list) -> bool:
        """Check if symbol has upcoming earnings or corporate action."""
        try:
            has_event = self.calendar_feed.has_upcoming_event(
                symbol, days_ahead=self.EVENT_BLACKOUT_DAYS
            )
            
            if has_event:
                event = self.db.query(EarningsCalendar).filter(
                    and_(
                        EarningsCalendar.symbol == symbol,
                        EarningsCalendar.event_date >= datetime.now(IST).date(),
                        EarningsCalendar.event_date <= (datetime.now(IST) + timedelta(days=self.EVENT_BLACKOUT_DAYS)).date()
                    )
                ).first()
                
                warnings.append(RiskWarning(
                    type=GuardrailSeverity.WARNING,
                    message=f"Upcoming {event.event_type} on {event.event_date}",
                    code="EVENT_WINDOW_WARNING",
                    details={
                        "event_type": event.event_type,
                        "event_date": str(event.event_date),
                        "days_until": (event.event_date - datetime.now(IST).date()).days
                    }
                ))
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Event window check error: {e}")
            return True
    
    async def check_regime_compatibility(
        self, symbol: str, account_id: Optional[int], warnings: list
    ) -> bool:
        """Check if current market regime matches mandate."""
        if not account_id:
            return True
        
        try:
            mandate = self.db.query(Mandate).filter(
                Mandate.account_id == account_id
            ).first()
            
            if not mandate or not mandate.regime_filter:
                return True
            
            # Get latest feature for symbol
            feature = self.db.query(Feature).filter(
                Feature.symbol == symbol
            ).order_by(Feature.ts.desc()).first()
            
            if not feature or not feature.regime_label:
                return True
            
            # Check if regime matches mandate filter
            allowed_regimes = mandate.regime_filter  # Should be list like ["BULL", "SIDEWAYS"]
            
            if feature.regime_label not in allowed_regimes:
                warnings.append(RiskWarning(
                    type=GuardrailSeverity.WARNING,
                    message=f"Regime {feature.regime_label} not in mandate filter {allowed_regimes}",
                    code="REGIME_MISMATCH",
                    details={
                        "current_regime": feature.regime_label,
                        "allowed_regimes": allowed_regimes
                    }
                ))
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Regime check error: {e}")
            return True
    
    async def check_catalyst_freshness(
        self, event_id: Optional[int], warnings: list
    ) -> bool:
        """Check if event (for hot path) is fresh enough."""
        if not event_id:
            return True  # Not applicable for regular pipeline
        
        try:
            event = self.db.query(Event).filter(Event.id == event_id).first()
            
            if not event:
                return True
            
            age_hours = (datetime.now(IST) - event.created_at).total_seconds() / 3600
            
            if age_hours > self.CATALYST_FRESHNESS_HOURS:
                warnings.append(RiskWarning(
                    type=GuardrailSeverity.CRITICAL,
                    message=f"Event is {age_hours:.1f} hours old (stale)",
                    code="CATALYST_STALE",
                    details={
                        "event_age_hours": round(age_hours, 1),
                        "threshold_hours": self.CATALYST_FRESHNESS_HOURS,
                        "event_id": event_id
                    }
                ))
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Catalyst freshness check error: {e}")
            return True
```

#### 1.6 Integrate Real Checks into Pipeline

**File:** `backend/app/services/trade_card_pipeline_v2.py` (Lines 150-190)

```python
# Add imports at top
from .risk_evaluation import RiskEvaluationResult
from .risk_checks import RiskChecker

# In __init__, add:
self.risk_checker = RiskChecker(self.db)

# In run_full_pipeline, replace lines 178-184 with:

try:
    # Run real guardrail checks
    risk_result = await self.risk_checker.run_all_checks(
        symbol=opp["symbol"],
        quantity=opp["quantity"],
        entry_price=opp["entry_price"],
        stop_loss=opp["stop_loss"],
        trade_type=opp["direction"],
        exchange=opp.get("exchange", "NSE"),
        account_id=account.id,
        sector=opp.get("sector"),  # Allocator should populate this
        event_id=None  # Regular pipeline, not hot-path
    )
    
    # Block card creation if critical guardrail failure
    if risk_result.has_critical_failures:
        logger.warning(
            f"Blocking card for {opp['symbol']} account {account.id}: "
            f"critical guardrail failure - {[w.code for w in risk_result.risk_warnings if w.type == 'CRITICAL']}"
        )
        
        # Persist blocked card marker for idempotency
        blocked_card = TradeCardV2(
            account_id=account.id,
            signal_id=opp.get("signal_id"),
            symbol=opp["symbol"],
            direction=opp["direction"],
            status="BLOCKED",
            thesis="Blocked by guardrails",
            risk_warnings=[w.to_dict() for w in risk_result.risk_warnings],
            liquidity_check=risk_result.liquidity_check,
            position_size_check=risk_result.position_size_check,
            exposure_check=risk_result.exposure_check,
            event_window_check=risk_result.event_window_check,
            regime_check=risk_result.regime_check,
            catalyst_freshness_check=risk_result.catalyst_freshness_check,
            created_at=datetime.now(pytz.timezone('Asia/Kolkata'))
        )
        self.db.add(blocked_card)
        self.db.commit()
        
        continue  # Skip to next opportunity
    
    # Create card with guardrail results
    card = TradeCardV2(
        account_id=account.id,
        signal_id=opp.get("signal_id"),
        symbol=opp["symbol"],
        direction=opp["direction"],
        quantity=opp["quantity"],
        entry_price=opp["entry_price"],
        stop_loss=opp["stop_loss"],
        take_profit=opp["take_profit"],
        thesis=thesis,
        risk_assessment=risk_assessment,
        status="PENDING_APPROVAL",
        # Guardrail results
        liquidity_check=risk_result.liquidity_check,
        position_size_check=risk_result.position_size_check,
        exposure_check=risk_result.exposure_check,
        event_window_check=risk_result.event_window_check,
        regime_check=risk_result.regime_check,
        catalyst_freshness_check=risk_result.catalyst_freshness_check,
        risk_warnings=[w.to_dict() for w in risk_result.risk_warnings],
        # ... rest of fields
    )
    
except Exception as e:
    logger.error(f"Guardrail check failed for {opp['symbol']}: {e}", exc_info=True)
    # Degrade gracefully - log and skip card
    continue
```

#### 1.7 Create Guardrails API Router

**New File:** `backend/app/routers/guardrails.py`

```python
"""Guardrails API endpoints with auth and rate limiting."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from ..database import get_db
from ..services.risk_checks import RiskChecker
from ..services.risk_evaluation import RiskEvaluationResult
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/guardrails", tags=["Guardrails"])

# Rate limiting (simple in-memory, replace with Redis in production)
from collections import defaultdict
from datetime import datetime, timedelta
rate_limit_store = defaultdict(list)

def check_rate_limit(request: Request, limit: int = 30, window_seconds: int = 60):
    """Simple rate limiter: 30 req/min per IP."""
    client_ip = request.client.host
    now = datetime.now()
    cutoff = now - timedelta(seconds=window_seconds)
    
    # Clean old requests
    rate_limit_store[client_ip] = [
        ts for ts in rate_limit_store[client_ip] if ts > cutoff
    ]
    
    if len(rate_limit_store[client_ip]) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    rate_limit_store[client_ip].append(now)

class GuardrailCheckRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    account_id: int
    quantity: int = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    direction: str = Field(..., regex="^(LONG|SHORT)$")
    exchange: str = "NSE"
    sector: Optional[str] = None
    event_id: Optional[int] = None

class GuardrailCheckResponse(BaseModel):
    liquidity_check: bool
    position_size_check: bool
    exposure_check: bool
    event_window_check: bool
    regime_check: bool
    catalyst_freshness_check: bool
    risk_warnings: list
    passed_all: bool
    has_critical_failures: bool
    timestamp: str
    evaluation_duration_ms: float

@router.post("/check", response_model=GuardrailCheckResponse)
async def check_guardrails(
    request: Request,
    payload: GuardrailCheckRequest,
    db: Session = Depends(get_db)
):
    """Check all guardrails for a potential trade."""
    # Rate limiting
    check_rate_limit(request)
    
    # TODO: Add JWT auth check here
    # if not verify_jwt(request.headers.get("Authorization")):
    #     raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        risk_checker = RiskChecker(db)
        result = await risk_checker.run_all_checks(
            symbol=payload.symbol,
            quantity=payload.quantity,
            entry_price=payload.entry_price,
            stop_loss=payload.stop_loss,
            trade_type=payload.direction,
            exchange=payload.exchange,
            account_id=payload.account_id,
            sector=payload.sector,
            event_id=payload.event_id
        )
        
        return GuardrailCheckResponse(**result.to_dict())
    
    except Exception as e:
        logger.error(f"Guardrail check error: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Guardrail check service unavailable")

@router.get("/explain")
async def explain_guardrails(
    card_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed explanation of guardrail results for a trade card."""
    from ..database import TradeCardV2
    
    card = db.query(TradeCardV2).filter(TradeCardV2.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    return {
        "card_id": card_id,
        "symbol": card.symbol,
        "guardrails": {
            "liquidity_check": card.liquidity_check,
            "position_size_check": card.position_size_check,
            "exposure_check": card.exposure_check,
            "event_window_check": card.event_window_check,
            "regime_check": card.regime_check,
            "catalyst_freshness_check": card.catalyst_freshness_check
        },
        "risk_warnings": card.risk_warnings or [],
        "status": card.status
    }
```

**Register router in `backend/app/main.py`:**

```python
from .routers import guardrails
app.include_router(guardrails.router)
```

#### 1.8 Database Migrations

**New File:** `backend/alembic/versions/001_phase2_guardrails.py`

```python
"""Phase 2 P1.1: Add guardrail tables and indexes

Revision ID: 001_phase2_guardrails
Revises: 
Create Date: 2025-10-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = '001_phase2_guardrails'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create earnings_calendar table
    op.create_table(
        'earnings_calendar',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('source', sa.String(100)),
        sa.Column('created_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_earnings_calendar_symbol', 'earnings_calendar', ['symbol'])
    op.create_index('ix_earnings_calendar_event_date', 'earnings_calendar', ['event_date'])
    op.create_index('ix_earnings_calendar_symbol_date', 'earnings_calendar', ['symbol', 'event_date'])
    
    # Create symbol_master table
    op.create_table(
        'symbol_master',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False, unique=True),
        sa.Column('company_name', sa.String(200)),
        sa.Column('sector', sa.String(100)),
        sa.Column('industry', sa.String(100)),
        sa.Column('exchange', sa.String(10)),
        sa.Column('isin', sa.String(20)),
        sa.Column('updated_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_symbol_master_symbol', 'symbol_master', ['symbol'])
    op.create_index('ix_symbol_master_sector', 'symbol_master', ['sector'])
    
    # Add indexes to existing tables for performance
    op.create_index('ix_events_symbol_created', 'events', ['symbol', 'created_at'])
    op.create_index('ix_market_data_cache_symbol_ts', 'market_data_cache', ['symbol', 'ts'])
    
    # Ensure trade_cards_v2 has all guardrail columns (may already exist)
    # This is idempotent - won't fail if columns exist
    try:
        op.add_column('trade_cards_v2', sa.Column('liquidity_check', sa.Boolean(), default=False))
    except:
        pass
    
    try:
        op.add_column('trade_cards_v2', sa.Column('position_size_check', sa.Boolean(), default=False))
    except:
        pass
    
    try:
        op.add_column('trade_cards_v2', sa.Column('exposure_check', sa.Boolean(), default=False))
    except:
        pass
    
    try:
        op.add_column('trade_cards_v2', sa.Column('event_window_check', sa.Boolean(), default=False))
    except:
        pass
    
    try:
        op.add_column('trade_cards_v2', sa.Column('regime_check', sa.Boolean(), default=False))
    except:
        pass
    
    try:
        op.add_column('trade_cards_v2', sa.Column('catalyst_freshness_check', sa.Boolean(), default=False))
    except:
        pass

def downgrade():
    op.drop_table('earnings_calendar')
    op.drop_table('symbol_master')
    op.drop_index('ix_events_symbol_created')
    op.drop_index('ix_market_data_cache_symbol_ts')
```

#### 1.9 Frontend Implementation

**File:** `frontend/static/css/styles.css` (Add)

```css
/* Guardrail chips */
.guardrails-section {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid #e0e0e0;
}

.guardrails-title {
    font-size: 12px;
    font-weight: 600;
    color: #666;
    margin-bottom: 8px;
}

.guardrail {
    display: inline-block;
    padding: 4px 8px;
    margin: 2px 4px 2px 0;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 500;
}

.guardrail.pass {
    background-color: #e8f5e9;
    color: #2e7d32;
    border: 1px solid #a5d6a7;
}

.guardrail.fail {
    background-color: #ffebee;
    color: #c62828;
    border: 1px solid #ef9a9a;
}

.guardrail.warning {
    background-color: #fff3e0;
    color: #e65100;
    border: 1px solid #ffb74d;
}

.guardrail-explain-btn {
    margin-left: 8px;
    font-size: 11px;
    padding: 2px 8px;
    background: #f5f5f5;
    border: 1px solid #ddd;
    border-radius: 4px;
    cursor: pointer;
}

.guardrail-explain-btn:hover {
    background: #e0e0e0;
}

/* Modal for guardrail details */
.guardrail-modal {
    display: none;
    position: fixed;
    z-index: 1000;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0,0,0,0.5);
}

.guardrail-modal-content {
    background-color: #fff;
    margin: 10% auto;
    padding: 20px;
    border-radius: 8px;
    width: 80%;
    max-width: 600px;
    max-height: 70vh;
    overflow-y: auto;
}

.guardrail-modal-close {
    float: right;
    font-size: 28px;
    font-weight: bold;
    cursor: pointer;
    color: #aaa;
}

.guardrail-modal-close:hover {
    color: #000;
}

.warning-item {
    padding: 12px;
    margin: 8px 0;
    border-radius: 4px;
    border-left: 4px solid;
}

.warning-item.CRITICAL {
    background: #ffebee;
    border-color: #c62828;
}

.warning-item.WARNING {
    background: #fff3e0;
    border-color: #e65100;
}

.warning-item.INFO {
    background: #e3f2fd;
    border-color: #1976d2;
}
```

**File:** `frontend/static/js/app.js` (Enhance)

```javascript
// Add to createTradeCardHTML function

createTradeCardHTML(card) {
    // ... existing code ...
    
    // Guardrails section
    const guardrails = [
        {name: 'Liquidity', passed: card.liquidity_check, icon: '💧'},
        {name: 'Position Size', passed: card.position_size_check, icon: '📊'},
        {name: 'Exposure', passed: card.exposure_check, icon: '🎯'},
        {name: 'Event Window', passed: card.event_window_check, icon: '📅'},
        {name: 'Regime', passed: card.regime_check, icon: '🌡️'},
        {name: 'Catalyst Fresh', passed: card.catalyst_freshness_check, icon: '⚡'}
    ];
    
    const hasWarnings = card.risk_warnings && card.risk_warnings.length > 0;
    const hasCritical = hasWarnings && card.risk_warnings.some(w => w.type === 'CRITICAL');
    
    const guardrailHTML = `
        <div class="guardrails-section">
            <div class="guardrails-title">Guardrails</div>
            ${guardrails.map(g => `
                <span class="guardrail ${g.passed ? 'pass' : 'fail'}">
                    ${g.icon} ${g.name} ${g.passed ? '✓' : '✗'}
                </span>
            `).join('')}
            ${hasWarnings ? `
                <button class="guardrail-explain-btn" onclick="app.showGuardrailDetails(${card.id})">
                    ${hasCritical ? '⚠️' : 'ℹ️'} Explain (${card.risk_warnings.length})
                </button>
            ` : ''}
        </div>
    `;
    
    // Insert before action buttons
    // ... rest of card HTML ...
}

// Add new method
async showGuardrailDetails(cardId) {
    try {
        const response = await api.get(`/api/guardrails/explain?card_id=${cardId}`);
        const data = response;
        
        // Create modal
        const modal = document.createElement('div');
        modal.className = 'guardrail-modal';
        modal.innerHTML = `
            <div class="guardrail-modal-content">
                <span class="guardrail-modal-close">&times;</span>
                <h3>Guardrail Details: ${data.symbol}</h3>
                <div style="margin-top: 20px;">
                    ${data.risk_warnings.map(w => `
                        <div class="warning-item ${w.type}">
                            <div style="font-weight: 600; margin-bottom: 4px;">
                                ${w.type}: ${w.code}
                            </div>
                            <div style="margin-bottom: 8px;">${w.message}</div>
                            ${w.details ? `
                                <div style="font-size: 12px; color: #666;">
                                    ${JSON.stringify(w.details, null, 2)}
                                </div>
                            ` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        modal.style.display = 'block';
        
        // Close on click
        modal.querySelector('.guardrail-modal-close').onclick = () => {
            modal.remove();
        };
        
        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        };
        
    } catch (error) {
        console.error('Failed to fetch guardrail details:', error);
        alert('Failed to load guardrail details');
    }
}
```

#### 1.10 Observability & Metrics

**File:** `backend/app/services/metrics.py` (New or Enhanced)

```python
"""Metrics collection for guardrails."""
from prometheus_client import Counter, Histogram, Gauge
from typing import Dict, Any

# Guardrail metrics
guardrail_checks_total = Counter(
    'guardrail_checks_total',
    'Total guardrail checks performed',
    ['check_type', 'result']
)

guardrail_latency_ms = Histogram(
    'guardrail_latency_ms',
    'Guardrail evaluation latency in milliseconds',
    buckets=[10, 25, 50, 100, 250, 500, 1000]
)

blocked_cards_total = Counter(
    'blocked_cards_total',
    'Total trade cards blocked by guardrails',
    ['account_id', 'reason']
)

guardrail_pass_ratio = Gauge(
    'guardrail_pass_ratio',
    'Ratio of signals passing all guardrails (last 100)',
    ['account_id']
)

def record_guardrail_check(result: Dict[str, Any]):
    """Record metrics for a guardrail check."""
    # Record individual check results
    for check in ['liquidity', 'position_size', 'exposure', 'event_window', 'regime', 'catalyst_freshness']:
        check_key = f"{check}_check"
        if check_key in result:
            guardrail_checks_total.labels(
                check_type=check,
                result='pass' if result[check_key] else 'fail'
            ).inc()
    
    # Record latency
    if 'evaluation_duration_ms' in result:
        guardrail_latency_ms.observe(result['evaluation_duration_ms'])
    
    # Record blocked cards
    if result.get('has_critical_failures'):
        blocked_cards_total.labels(
            account_id=result.get('account_id', 'unknown'),
            reason=result.get('risk_warnings', [{}])[0].get('code', 'UNKNOWN')
        ).inc()
```

**Update risk_checks.py to record metrics:**

```python
from .metrics import record_guardrail_check

# At end of run_all_checks():
record_guardrail_check(result.to_dict())
```

#### 1.11 Environment Variables

**File:** `env.template` (Add)

```env
# Guardrail Configuration
REAL_GUARDRAILS=true
ADV_LOOKBACK_DAYS=20
ADV_MIN_LIQUIDITY_RATIO=0.05
EVENT_BLACKOUT_DAYS=2
CATALYST_FRESHNESS_HOURS=24
MAX_SECTOR_EXPOSURE=0.30

# Calendar Feed
NSE_CALENDAR_UPDATE_HOUR=8
NSE_MASTER_UPDATE_DAY=SUNDAY
```

### Testing

#### Test File: `tests/test_guardrails.py`

```python
"""Comprehensive guardrail tests (20+ cases)."""
import pytest
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import Session
from backend.app.services.risk_checks import RiskChecker
from backend.app.services.risk_evaluation import GuardrailSeverity
from backend.app.database import (
    MarketDataCache, Account, Mandate, PositionV2,
    Feature, Event, EarningsCalendar, SymbolMaster
)

IST = pytz.timezone('Asia/Kolkata')

@pytest.fixture
def setup_test_data(db: Session):
    """Setup test data."""
    # Create account with mandate
    account = Account(id=1, name="Test Account", user_id="test_user")
    mandate = Mandate(
        id=1,
        account_id=1,
        total_capital=1000000,
        risk_per_trade_percent=2.0,
        regime_filter=["BULL", "SIDEWAYS"]
    )
    
    # Symbol master
    symbol_master = SymbolMaster(
        symbol="INFY",
        sector="IT",
        exchange="NSE"
    )
    
    # Market data for liquidity
    for i in range(20):
        md = MarketDataCache(
            symbol="INFY",
            volume=5000000,
            close=1450.0,
            ts=datetime.now(IST) - timedelta(days=i)
        )
        db.add(md)
    
    db.add(account)
    db.add(mandate)
    db.add(symbol_master)
    db.commit()
    
    yield db
    
    # Cleanup
    db.query(Account).delete()
    db.query(Mandate).delete()
    db.query(SymbolMaster).delete()
    db.query(MarketDataCache).delete()
    db.commit()

class TestLiquidityCheck:
    """Test liquidity guardrail."""
    
    @pytest.mark.asyncio
    async def test_liquidity_pass(self, setup_test_data):
        """Trade size within ADV limit should pass."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # 1% of ADV (5M) = 50k shares
        result = await checker.check_liquidity("INFY", 50000, warnings)
        
        assert result is True
        assert len(warnings) == 0
    
    @pytest.mark.asyncio
    async def test_liquidity_fail(self, setup_test_data):
        """Trade size exceeding ADV limit should fail."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # 10% of ADV = 500k shares (exceeds 5% limit)
        result = await checker.check_liquidity("INFY", 500000, warnings)
        
        assert result is False
        assert len(warnings) == 1
        assert warnings[0].type == GuardrailSeverity.CRITICAL
        assert warnings[0].code == "LIQUIDITY_BELOW_THRESHOLD"
    
    @pytest.mark.asyncio
    async def test_liquidity_insufficient_data(self, setup_test_data):
        """Insufficient data should warn but not block."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        result = await checker.check_liquidity("UNKNOWN", 1000, warnings)
        
        assert result is True  # Fail open
        assert len(warnings) == 1
        assert warnings[0].type == GuardrailSeverity.WARNING

class TestPositionSizeCheck:
    """Test position size guardrail."""
    
    @pytest.mark.asyncio
    async def test_position_size_pass(self, setup_test_data):
        """Risk within mandate limit should pass."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Max loss = (1450 - 1420) * 500 = 15,000
        # Risk % = 15000 / 1000000 = 1.5% < 2.0%
        result = await checker.check_position_size_risk(
            account_id=1,
            entry_price=1450.0,
            stop_loss=1420.0,
            quantity=500,
            warnings=warnings
        )
        
        assert result is True
        assert len(warnings) == 0
    
    @pytest.mark.asyncio
    async def test_position_size_fail(self, setup_test_data):
        """Risk exceeding mandate limit should fail."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Max loss = (1450 - 1400) * 500 = 25,000
        # Risk % = 25000 / 1000000 = 2.5% > 2.0%
        result = await checker.check_position_size_risk(
            account_id=1,
            entry_price=1450.0,
            stop_loss=1400.0,
            quantity=500,
            warnings=warnings
        )
        
        assert result is False
        assert len(warnings) == 1
        assert warnings[0].code == "POSITION_SIZE_EXCEEDED"

class TestSectorExposureCheck:
    """Test sector exposure guardrail."""
    
    @pytest.mark.asyncio
    async def test_sector_exposure_pass(self, setup_test_data):
        """Sector exposure within limit should pass."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Existing position: 100k in IT sector
        position = PositionV2(
            account_id=1,
            symbol="TCS",
            quantity=100,
            entry_price=1000.0,
            current_value=100000,
            status="OPEN"
        )
        setup_test_data.add(position)
        
        # Add SymbolMaster for TCS
        tcs_master = SymbolMaster(symbol="TCS", sector="IT", exchange="NSE")
        setup_test_data.add(tcs_master)
        setup_test_data.commit()
        
        # New position: 150k in IT (total = 250k = 25% < 30%)
        result = await checker.check_sector_exposure(
            account_id=1,
            sector="IT",
            new_position_value=150000,
            warnings=warnings
        )
        
        assert result is True
        assert len(warnings) == 0
    
    @pytest.mark.asyncio
    async def test_sector_exposure_fail(self, setup_test_data):
        """Sector exposure exceeding limit should fail."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Existing position: 200k in IT sector
        position = PositionV2(
            account_id=1,
            symbol="TCS",
            quantity=200,
            entry_price=1000.0,
            current_value=200000,
            status="OPEN"
        )
        setup_test_data.add(position)
        
        tcs_master = SymbolMaster(symbol="TCS", sector="IT", exchange="NSE")
        setup_test_data.add(tcs_master)
        setup_test_data.commit()
        
        # New position: 150k in IT (total = 350k = 35% > 30%)
        result = await checker.check_sector_exposure(
            account_id=1,
            sector="IT",
            new_position_value=150000,
            warnings=warnings
        )
        
        assert result is False
        assert len(warnings) == 1
        assert warnings[0].code == "SECTOR_EXPOSURE_EXCEEDED"

class TestEventWindowCheck:
    """Test event window guardrail."""
    
    @pytest.mark.asyncio
    async def test_event_window_pass(self, setup_test_data):
        """No upcoming event should pass."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        result = await checker.check_event_window("INFY", warnings)
        
        assert result is True
        assert len(warnings) == 0
    
    @pytest.mark.asyncio
    async def test_event_window_fail(self, setup_test_data):
        """Upcoming event within blackout should fail."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Add earnings event tomorrow
        event = EarningsCalendar(
            symbol="INFY",
            event_date=(datetime.now(IST) + timedelta(days=1)).date(),
            event_type="EARNINGS",
            source="NSE"
        )
        setup_test_data.add(event)
        setup_test_data.commit()
        
        result = await checker.check_event_window("INFY", warnings)
        
        assert result is False
        assert len(warnings) == 1
        assert warnings[0].code == "EVENT_WINDOW_WARNING"

class TestRegimeCheck:
    """Test regime compatibility guardrail."""
    
    @pytest.mark.asyncio
    async def test_regime_pass(self, setup_test_data):
        """Regime matching mandate should pass."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Add feature with BULL regime
        feature = Feature(
            symbol="INFY",
            regime_label="BULL",
            ts=datetime.now(IST)
        )
        setup_test_data.add(feature)
        setup_test_data.commit()
        
        result = await checker.check_regime_compatibility("INFY", 1, warnings)
        
        assert result is True
        assert len(warnings) == 0
    
    @pytest.mark.asyncio
    async def test_regime_fail(self, setup_test_data):
        """Regime not in mandate filter should fail."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Add feature with BEAR regime (not in mandate filter)
        feature = Feature(
            symbol="INFY",
            regime_label="BEAR",
            ts=datetime.now(IST)
        )
        setup_test_data.add(feature)
        setup_test_data.commit()
        
        result = await checker.check_regime_compatibility("INFY", 1, warnings)
        
        assert result is False
        assert len(warnings) == 1
        assert warnings[0].code == "REGIME_MISMATCH"

class TestCatalystFreshnessCheck:
    """Test catalyst freshness guardrail."""
    
    @pytest.mark.asyncio
    async def test_catalyst_fresh_pass(self, setup_test_data):
        """Fresh event should pass."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Event created 1 hour ago
        event = Event(
            id=1,
            source="NEWS",
            event_type="POSITIVE",
            created_at=datetime.now(IST) - timedelta(hours=1)
        )
        setup_test_data.add(event)
        setup_test_data.commit()
        
        result = await checker.check_catalyst_freshness(1, warnings)
        
        assert result is True
        assert len(warnings) == 0
    
    @pytest.mark.asyncio
    async def test_catalyst_stale_fail(self, setup_test_data):
        """Stale event should fail."""
        checker = RiskChecker(setup_test_data)
        warnings = []
        
        # Event created 30 hours ago
        event = Event(
            id=1,
            source="NEWS",
            event_type="POSITIVE",
            created_at=datetime.now(IST) - timedelta(hours=30)
        )
        setup_test_data.add(event)
        setup_test_data.commit()
        
        result = await checker.check_catalyst_freshness(1, warnings)
        
        assert result is False
        assert len(warnings) == 1
        assert warnings[0].code == "CATALYST_STALE"

class TestIntegration:
    """End-to-end integration tests."""
    
    @pytest.mark.asyncio
    async def test_all_checks_pass(self, setup_test_data):
        """All checks passing should allow card creation."""
        checker = RiskChecker(setup_test_data)
        
        result = await checker.run_all_checks(
            symbol="INFY",
            quantity=50000,
            entry_price=1450.0,
            stop_loss=1420.0,
            trade_type="LONG",
            exchange="NSE",
            account_id=1,
            sector="IT"
        )
        
        assert result.passed_all is True
        assert result.has_critical_failures is False
        assert result.evaluation_duration_ms > 0
    
    @pytest.mark.asyncio
    async def test_critical_failure_blocks(self, setup_test_data):
        """Critical failure should block card."""
        checker = RiskChecker(setup_test_data)
        
        # Excessive liquidity request
        result = await checker.run_all_checks(
            symbol="INFY",
            quantity=1000000,  # 20% of ADV
            entry_price=1450.0,
            stop_loss=1420.0,
            trade_type="LONG",
            exchange="NSE",
            account_id=1,
            sector="IT"
        )
        
        assert result.passed_all is False
        assert result.has_critical_failures is True
        assert result.liquidity_check is False

# Additional tests...
# - Test error handling (DB failures, timeouts)
# - Test async coherence
# - Test timezone handling
# - Test idempotency of blocked cards
# - Test rate limiting on API endpoint
# - Test auth on API endpoint (once JWT implemented)
# - Test metrics recording
```

### Documentation

**New File:** `PHASE2_P1.1_GUARDRAILS.md`

```markdown
# Phase 2 P1.1: Guardrails Implementation

## Overview
Production-grade guardrail system with 6 real checks backed by live data sources.

## Guardrails

### 1. Liquidity Check
- **Purpose:** Ensure trade size doesn't exceed market liquidity
- **Data Source:** `market_data_cache` (20-day ADV)
- **Threshold:** Trade must be ≤ 5% of Average Daily Volume
- **Severity:** CRITICAL (blocks if failed)

### 2. Position Size Risk Check
- **Purpose:** Respect per-trade risk limits from mandate
- **Data Source:** `mandates.risk_per_trade_percent`
- **Calculation:** `(|entry - SL| * qty) / total_capital ≤ limit`
- **Severity:** CRITICAL

### 3. Sector Exposure Check
- **Purpose:** Prevent over-concentration in single sector
- **Data Source:** `positions_v2` + `symbol_master`
- **Threshold:** Sector exposure must be ≤ 30% of capital
- **Severity:** CRITICAL

### 4. Event Window Check
- **Purpose:** Avoid trading during earnings blackout
- **Data Source:** `earnings_calendar` (NSE)
- **Threshold:** No event within 2 days
- **Severity:** WARNING

### 5. Regime Compatibility Check
- **Purpose:** Match trades to mandate regime filter
- **Data Source:** `features.regime_label` vs `mandates.regime_filter`
- **Threshold:** Current regime must be in allowed list
- **Severity:** WARNING

### 6. Catalyst Freshness Check
- **Purpose:** Ensure hot-path events are recent
- **Data Source:** `events.created_at`
- **Threshold:** Event age must be < 24 hours
- **Severity:** CRITICAL (for hot-path only)

## API Endpoints

### POST /api/guardrails/check
Check all guardrails for a potential trade.

**Request:**
```json
{
  "symbol": "INFY",
  "account_id": 1,
  "quantity": 100,
  "entry_price": 1450.50,
  "stop_loss": 1420.00,
  "direction": "LONG",
  "exchange": "NSE",
  "sector": "IT"
}
```

**Response:**
```json
{
  "liquidity_check": true,
  "position_size_check": true,
  "exposure_check": false,
  "event_window_check": true,
  "regime_check": true,
  "catalyst_freshness_check": true,
  "risk_warnings": [
    {
      "type": "CRITICAL",
      "message": "Sector exposure exceeds 30% limit",
      "code": "SECTOR_EXPOSURE_EXCEEDED",
      "details": {"current_exposure": 0.35}
    }
  ],
  "passed_all": false,
  "has_critical_failures": true,
  "timestamp": "2025-10-22T09:30:00+05:30"
}
```

### GET /api/guardrails/explain?card_id=123
Get detailed explanation for a trade card's guardrail results.

## Configuration

Environment variables in `.env`:
```env
REAL_GUARDRAILS=true
ADV_LOOKBACK_DAYS=20
ADV_MIN_LIQUIDITY_RATIO=0.05
EVENT_BLACKOUT_DAYS=2
CATALYST_FRESHNESS_HOURS=24
MAX_SECTOR_EXPOSURE=0.30
```

## Database Schema

### New Tables

**earnings_calendar:**
- `symbol`, `event_date`, `event_type`, `source`
- Indexes: (symbol), (event_date), (symbol, event_date)

**symbol_master:**
- `symbol`, `sector`, `industry`, `exchange`, `isin`
- Indexes: (symbol), (sector)

### Modified Tables

**trade_cards_v2:** All 6 guardrail boolean fields + `risk_warnings` JSON

## Data Ingestion

### Calendar Feed
- Source: NSE Corporate Announcements API
- Frequency: Daily at 8 AM IST
- Command: `python -m backend.app.services.ingestion.calendar_feed`

### NSE Master
- Source: NSE EQUITY_L.csv
- Frequency: Weekly on Sunday
- Command: `python -m backend.app.services.ingestion.nse_master`

## Metrics

Prometheus metrics exposed at `/metrics`:
- `guardrail_checks_total{check_type, result}`
- `guardrail_latency_ms`
- `blocked_cards_total{account_id, reason}`
- `guardrail_pass_ratio{account_id}`

## Testing

Run tests:
```bash
pytest tests/test_guardrails.py -v
```

Coverage: 20+ test cases covering all guardrails and edge cases.

## Rollout Plan

1. **Day 1:** Deploy with `REAL_GUARDRAILS=false` (observability only)
2. **Day 2:** Enable for test account, monitor metrics
3. **Day 3:** Enable globally with `REAL_GUARDRAILS=true`

## Troubleshooting

### Guardrail Check Fails with 503
- Check calendar feed freshness: `SELECT MAX(created_at) FROM earnings_calendar`
- Check NSE master: `SELECT COUNT(*) FROM symbol_master`
- Verify DB indexes exist

### High Latency (>100ms)
- Check DB indexes on `market_data_cache(symbol, ts)`
- Check positions query performance
- Consider caching sector mappings

## Production Checklist

- [ ] Database migration applied
- [ ] Calendar feed scheduled (cron)
- [ ] NSE master updated
- [ ] Metrics dashboard created
- [ ] Alert rules configured (pass rate < 85%)
- [ ] API rate limiting enabled
- [ ] JWT auth enabled
- [ ] All tests passing (pytest)
- [ ] Feature flag tested on sandbox account
```

### Rollout Strategy

**Feature Flag:** `REAL_GUARDRAILS` (default: `true`)

**Timeline:**
- **Day 1 Morning:** Deploy code, run migration, feature flag OFF
- **Day 1 Afternoon:** Ingest calendar + NSE master data
- **Day 2 Morning:** Enable for 1 test account, monitor metrics
- **Day 2 Afternoon:** Review blocked cards, tune thresholds if needed
- **Day 3:** Enable globally

**Rollback Plan:**
- Set `REAL_GUARDRAILS=false` → reverts to pass-through (all checks return True)
- No code rollback needed

---

## Security

- ✅ Read-only checks (no DB writes in guardrail logic)
- ✅ Rate limiting: 30 req/min per IP
- ✅ Input validation: Pydantic models
- ✅ SQL injection safe: SQLAlchemy ORM
- ⚠️ TODO: Add JWT auth to `/api/guardrails/check`
- ✅ Timezone-aware timestamps (Asia/Kolkata)

---

## Observability

### Dashboards

**Guardrails Overview (Grafana):**
- Pass rate by check type (last 24h)
- P95 latency per check
- Blocked cards by reason (pie chart)
- Alert: Pass rate < 85% for any check

### Alerts

1. **Low Pass Rate:** If `guardrail_pass_ratio < 0.85` for 1 hour → Slack alert
2. **High Latency:** If P95 latency > 250ms → Investigate DB performance
3. **Stale Data:** If calendar feed not updated in 48h → Manual intervention

---

## Success Criteria (DoD)

✅ All 6 guardrails implemented with real checks  
✅ Allocator import bug fixed (`MarketDataCache`)  
✅ Calendar feed ingesting NSE data daily  
✅ NSE master providing sector mappings  
✅ API endpoint with rate limiting functional  
✅ Frontend displaying guardrail chips + explain modal  
✅ Database migration applied successfully  
✅ 20+ tests passing with >85% coverage  
✅ Metrics visible in Prometheus/Grafana  
✅ Documentation complete (`PHASE2_P1.1_GUARDRAILS.md`)  
✅ Feature flag tested on sandbox account  

---

---

## 🧮 STAGE 2: P1.2 - Derivatives & Options Intelligence (Days 4-9)

### Problem Statement
- ❌ No options chain data → missing IV, OI, PCR signals
- ❌ Cannot generate multi-leg strategies → no hedging capability
- ❌ No Greeks calculation → incomplete risk view
- ❌ Missing options execution → cannot place spreads/iron condors

### Desired Outcomes (DoD)
✅ Options chain ingestion (IV, OI, PCR, IV Rank, expected move)  
✅ Options engine generates and evaluates multi-leg strategies  
✅ Greeks calculation (delta, gamma, theta, vega)  
✅ Upstox integration for option order placement  
✅ Frontend options chain viewer with strategy preview  
✅ 12+ test cases covering options logic  

### Architecture / UI Changes

**Backend:**
- New model: `OptionChain` (strikes, IVs, OI, greeks per expiry)
- New model: `OptionStrategy` (legs, P&L scenarios, margin requirement)
- New ingestion: `backend/app/services/ingestion/options_chain_feed.py`
- New service: `backend/app/services/options_engine.py`
- Enhanced: `backend/app/services/broker/upstox.py` (option methods)
- New router: `backend/app/routers/options.py`

**Frontend:**
- New tab: "Options" with chain viewer
- Options strategy cards in TradeCard modal
- Max loss / max gain annotations

### Data Contracts

#### OptionChain
```json
{
  "symbol": "RELIANCE",
  "expiry": "2025-10-31",
  "spot_price": 2450.75,
  "option_chain": [
    {
      "strike": 2450,
      "ce_ltp": 65.20,
      "ce_oi": 1200000,
      "ce_iv": 22.4,
      "ce_delta": 0.52,
      "ce_gamma": 0.015,
      "ce_theta": -12.5,
      "ce_vega": 8.2,
      "pe_ltp": 18.10,
      "pe_oi": 800000,
      "pe_iv": 23.1,
      "pe_delta": -0.48,
      "pe_gamma": 0.015,
      "pe_theta": -11.8,
      "pe_vega": 8.0
    }
  ],
  "atm_iv": 22.75,
  "iv_rank": 0.78,
  "pcr": 1.2,
  "expected_move": 85.5,
  "max_pain": 2450
}
```

#### OptionStrategy
```json
{
  "id": 1,
  "strategy_type": "IRON_CONDOR",
  "underlying": "RELIANCE",
  "expiry": "2025-10-31",
  "legs": [
    {"type": "SELL", "option_type": "CE", "strike": 2500, "quantity": 1, "premium": 45.0},
    {"type": "BUY", "option_type": "CE", "strike": 2550, "quantity": 1, "premium": 20.0},
    {"type": "SELL", "option_type": "PE", "strike": 2400, "quantity": 1, "premium": 40.0},
    {"type": "BUY", "option_type": "PE", "strike": 2350, "quantity": 1, "premium": 15.0}
  ],
  "net_premium": 50.0,
  "max_profit": 5000,
  "max_loss": -5000,
  "breakeven_upper": 2550,
  "breakeven_lower": 2350,
  "margin_required": 15000,
  "pop": 0.65,
  "pnl_scenarios": [
    {"spot_at_expiry": 2300, "pnl": -5000},
    {"spot_at_expiry": 2450, "pnl": 5000},
    {"spot_at_expiry": 2600, "pnl": -5000}
  ]
}
```

### API Endpoints

**1. GET /api/options/chain?symbol={symbol}&expiry={date}**
- Returns: Full option chain with greeks
- Rate limit: 20/min
- Cache: 15 min

**2. POST /api/options/strategy/generate**
```json
{
  "symbol": "RELIANCE",
  "strategy_types": ["COVERED_CALL", "IRON_CONDOR", "BULL_PUT_SPREAD"],
  "account_id": 1,
  "max_risk": 10000
}
```
Returns: List of candidate strategies ranked by risk-reward

**3. POST /api/options/strategy/execute**
```json
{
  "strategy_id": 1,
  "account_id": 1,
  "approval_id": 123,
  "quantity": 1
}
```
Returns: Order IDs for all legs

### Backend Implementation

#### 2.1 Database Models

**File:** `backend/app/database.py` (Add)

```python
class OptionChain(Base):
    __tablename__ = "option_chains"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    expiry = Column(Date, nullable=False, index=True)
    spot_price = Column(Float)
    strike = Column(Float, nullable=False)
    
    # Call data
    ce_ltp = Column(Float)
    ce_oi = Column(Integer)
    ce_volume = Column(Integer)
    ce_iv = Column(Float)
    ce_delta = Column(Float)
    ce_gamma = Column(Float)
    ce_theta = Column(Float)
    ce_vega = Column(Float)
    
    # Put data
    pe_ltp = Column(Float)
    pe_oi = Column(Integer)
    pe_volume = Column(Integer)
    pe_iv = Column(Float)
    pe_delta = Column(Float)
    pe_gamma = Column(Float)
    pe_theta = Column(Float)
    pe_vega = Column(Float)
    
    # Chain-level metrics
    atm_iv = Column(Float)
    iv_rank = Column(Float)
    pcr = Column(Float)
    max_pain = Column(Float)
    
    ts = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))
    
    __table_args__ = (
        Index('ix_option_chain_symbol_expiry_strike', 'symbol', 'expiry', 'strike'),
    )

class OptionStrategy(Base):
    __tablename__ = "option_strategies"
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    strategy_type = Column(String(50))  # COVERED_CALL, IRON_CONDOR, etc.
    underlying = Column(String(20), index=True)
    expiry = Column(Date)
    
    legs = Column(JSON)  # List of leg specifications
    net_premium = Column(Float)
    max_profit = Column(Float)
    max_loss = Column(Float)
    breakeven_upper = Column(Float)
    breakeven_lower = Column(Float)
    margin_required = Column(Float)
    pop = Column(Float)  # Probability of profit
    pnl_scenarios = Column(JSON)
    
    status = Column(String(20), default="PENDING")  # PENDING, EXECUTED, CLOSED
    created_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))
    executed_at = Column(DateTime)
    order_ids = Column(JSON)  # List of order IDs for each leg
```

#### 2.2 Options Chain Feed

**New File:** `backend/app/services/ingestion/options_chain_feed.py`

```python
"""Options chain ingestion from Upstox."""
import aiohttp
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from ...database import OptionChain
from ..broker.upstox import UpstoxBroker
import logging

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class OptionsChainFeed:
    """Fetch options chain data from Upstox."""
    
    def __init__(self, db: Session):
        self.db = db
        self.upstox = UpstoxBroker()
    
    async def fetch_chain(self, symbol: str, expiry: str) -> Dict[str, Any]:
        """Fetch full option chain for symbol and expiry."""
        try:
            # Call Upstox API (adjust based on actual API)
            chain_data = await self.upstox.get_option_chain(symbol, expiry)
            
            if not chain_data:
                logger.error(f"No chain data for {symbol} {expiry}")
                return {}
            
            # Parse and store
            spot_price = chain_data.get("spot_price")
            strikes = chain_data.get("strikes", [])
            
            for strike_data in strikes:
                chain_entry = OptionChain(
                    symbol=symbol,
                    expiry=datetime.strptime(expiry, "%Y-%m-%d").date(),
                    spot_price=spot_price,
                    strike=strike_data["strike"],
                    ce_ltp=strike_data.get("call", {}).get("ltp"),
                    ce_oi=strike_data.get("call", {}).get("oi"),
                    ce_volume=strike_data.get("call", {}).get("volume"),
                    ce_iv=strike_data.get("call", {}).get("iv"),
                    ce_delta=self._calculate_delta(strike_data, "CE", spot_price),
                    pe_ltp=strike_data.get("put", {}).get("ltp"),
                    pe_oi=strike_data.get("put", {}).get("oi"),
                    pe_volume=strike_data.get("put", {}).get("volume"),
                    pe_iv=strike_data.get("put", {}).get("iv"),
                    pe_delta=self._calculate_delta(strike_data, "PE", spot_price),
                    ts=datetime.now(IST)
                )
                
                self.db.merge(chain_entry)
            
            # Calculate chain-level metrics
            atm_strike = min(strikes, key=lambda x: abs(x["strike"] - spot_price))
            atm_iv = (atm_strike.get("call", {}).get("iv", 0) + atm_strike.get("put", {}).get("iv", 0)) / 2
            
            total_ce_oi = sum(s.get("call", {}).get("oi", 0) for s in strikes)
            total_pe_oi = sum(s.get("put", {}).get("oi", 0) for s in strikes)
            pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
            
            iv_rank = await self._calculate_iv_rank(symbol, atm_iv)
            
            self.db.commit()
            
            logger.info(f"Fetched option chain for {symbol} {expiry}: {len(strikes)} strikes")
            
            return {
                "symbol": symbol,
                "expiry": expiry,
                "spot_price": spot_price,
                "atm_iv": atm_iv,
                "iv_rank": iv_rank,
                "pcr": pcr,
                "strikes_count": len(strikes)
            }
        
        except Exception as e:
            logger.error(f"Options chain fetch error: {e}", exc_info=True)
            return {}
    
    def _calculate_delta(self, strike_data: Dict, option_type: str, spot: float) -> float:
        """Simple delta approximation (replace with Black-Scholes if needed)."""
        strike = strike_data["strike"]
        if option_type == "CE":
            # Call delta: 0-1, increases as spot > strike
            return min(1.0, max(0.0, 0.5 + (spot - strike) / (2 * strike)))
        else:
            # Put delta: -1-0, decreases as spot < strike
            return max(-1.0, min(0.0, -0.5 - (strike - spot) / (2 * strike)))
    
    async def _calculate_iv_rank(self, symbol: str, current_iv: float) -> float:
        """Calculate IV rank over last 52 weeks."""
        try:
            # Get historical IV data
            lookback = datetime.now(IST) - timedelta(days=365)
            historical_iv = self.db.query(OptionChain.atm_iv).filter(
                OptionChain.symbol == symbol,
                OptionChain.ts >= lookback,
                OptionChain.atm_iv.isnot(None)
            ).all()
            
            if len(historical_iv) < 50:
                return 0.5  # Default if insufficient data
            
            iv_values = [iv[0] for iv in historical_iv]
            iv_min = min(iv_values)
            iv_max = max(iv_values)
            
            if iv_max == iv_min:
                return 0.5
            
            iv_rank = (current_iv - iv_min) / (iv_max - iv_min)
            return round(iv_rank, 3)
        
        except Exception as e:
            logger.error(f"IV rank calculation error: {e}")
            return 0.5
```

#### 2.3 Options Engine

**New File:** `backend/app/services/options_engine.py`

```python
"""Options strategy generation and evaluation engine."""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, date
import pytz
from ..database import OptionChain, OptionStrategy, Mandate
import logging

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class OptionsEngine:
    """Generate and evaluate multi-leg option strategies."""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def generate_strategies(
        self,
        symbol: str,
        expiry: date,
        account_id: int,
        strategy_types: List[str],
        max_risk: float
    ) -> List[Dict[str, Any]]:
        """Generate candidate option strategies."""
        strategies = []
        
        # Get option chain
        chain = self._get_chain(symbol, expiry)
        if not chain:
            logger.error(f"No chain data for {symbol} {expiry}")
            return []
        
        # Get account mandate for risk limits
        mandate = self.db.query(Mandate).filter(Mandate.account_id == account_id).first()
        if not mandate:
            logger.error(f"No mandate for account {account_id}")
            return []
        
        # Generate each strategy type
        for strategy_type in strategy_types:
            if strategy_type == "COVERED_CALL":
                strat = self._generate_covered_call(chain, max_risk)
            elif strategy_type == "IRON_CONDOR":
                strat = self._generate_iron_condor(chain, max_risk)
            elif strategy_type == "BULL_PUT_SPREAD":
                strat = self._generate_bull_put_spread(chain, max_risk)
            elif strategy_type == "BEAR_CALL_SPREAD":
                strat = self._generate_bear_call_spread(chain, max_risk)
            elif strategy_type == "LONG_STRADDLE":
                strat = self._generate_long_straddle(chain, max_risk)
            else:
                continue
            
            if strat:
                strat["account_id"] = account_id
                strategies.append(strat)
        
        # Rank by risk-reward ratio
        strategies = self._rank_strategies(strategies)
        
        # Store in database
        for strat in strategies:
            strategy_obj = OptionStrategy(**strat)
            self.db.add(strategy_obj)
        self.db.commit()
        
        logger.info(f"Generated {len(strategies)} option strategies for {symbol}")
        return strategies
    
    def _get_chain(self, symbol: str, expiry: date) -> List[Dict[str, Any]]:
        """Get option chain from database."""
        chain_data = self.db.query(OptionChain).filter(
            OptionChain.symbol == symbol,
            OptionChain.expiry == expiry
        ).order_by(OptionChain.strike).all()
        
        return [
            {
                "strike": row.strike,
                "ce_ltp": row.ce_ltp,
                "ce_oi": row.ce_oi,
                "ce_iv": row.ce_iv,
                "ce_delta": row.ce_delta,
                "pe_ltp": row.pe_ltp,
                "pe_oi": row.pe_oi,
                "pe_iv": row.pe_iv,
                "pe_delta": row.pe_delta,
                "spot_price": row.spot_price
            }
            for row in chain_data
        ]
    
    def _generate_iron_condor(self, chain: List[Dict], max_risk: float) -> Optional[Dict]:
        """Generate iron condor: Sell OTM call + put, buy further OTM for protection."""
        if len(chain) < 10:
            return None
        
        spot = chain[0]["spot_price"]
        atm_idx = min(range(len(chain)), key=lambda i: abs(chain[i]["strike"] - spot))
        
        # Pick strikes: sell at ±2 strikes from ATM, buy at ±4 strikes
        if atm_idx < 4 or atm_idx >= len(chain) - 4:
            return None
        
        sell_call_strike = chain[atm_idx + 2]
        buy_call_strike = chain[atm_idx + 4]
        sell_put_strike = chain[atm_idx - 2]
        buy_put_strike = chain[atm_idx - 4]
        
        # Calculate P&L
        net_premium = (
            sell_call_strike["ce_ltp"] +
            sell_put_strike["pe_ltp"] -
            buy_call_strike["ce_ltp"] -
            buy_put_strike["pe_ltp"]
        )
        
        wing_width = buy_call_strike["strike"] - sell_call_strike["strike"]
        max_profit = net_premium * 100  # Per lot (assume 100 qty)
        max_loss = (wing_width - net_premium) * 100
        
        if max_loss > max_risk:
            return None
        
        return {
            "strategy_type": "IRON_CONDOR",
            "underlying": chain[0].get("symbol", "UNKNOWN"),
            "expiry": chain[0].get("expiry"),
            "legs": [
                {"type": "SELL", "option_type": "CE", "strike": sell_call_strike["strike"], "quantity": 1, "premium": sell_call_strike["ce_ltp"]},
                {"type": "BUY", "option_type": "CE", "strike": buy_call_strike["strike"], "quantity": 1, "premium": buy_call_strike["ce_ltp"]},
                {"type": "SELL", "option_type": "PE", "strike": sell_put_strike["strike"], "quantity": 1, "premium": sell_put_strike["pe_ltp"]},
                {"type": "BUY", "option_type": "PE", "strike": buy_put_strike["strike"], "quantity": 1, "premium": buy_put_strike["pe_ltp"]}
            ],
            "net_premium": round(net_premium, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven_upper": sell_call_strike["strike"] + net_premium,
            "breakeven_lower": sell_put_strike["strike"] - net_premium,
            "margin_required": max_loss,  # Simplified; use broker API for actual margin
            "pop": 0.65,  # Placeholder; calculate from deltas
            "pnl_scenarios": self._calculate_pnl_scenarios(chain[0]["spot_price"], None)
        }
    
    def _generate_covered_call(self, chain: List[Dict], max_risk: float) -> Optional[Dict]:
        """Generate covered call: Long stock + sell OTM call."""
        # Requires existing stock position
        # Placeholder implementation
        return None
    
    def _generate_bull_put_spread(self, chain: List[Dict], max_risk: float) -> Optional[Dict]:
        """Generate bull put spread: Sell OTM put + buy further OTM put."""
        # Similar to iron condor logic but only put side
        return None
    
    def _generate_bear_call_spread(self, chain: List[Dict], max_risk: float) -> Optional[Dict]:
        """Generate bear call spread: Sell OTM call + buy further OTM call."""
        # Similar to iron condor logic but only call side
        return None
    
    def _generate_long_straddle(self, chain: List[Dict], max_risk: float) -> Optional[Dict]:
        """Generate long straddle: Buy ATM call + put."""
        # For high volatility expectation
        return None
    
    def _calculate_pnl_scenarios(self, spot: float, legs: Any) -> List[Dict[str, float]]:
        """Calculate P&L at various spot prices at expiry."""
        # Placeholder: calculate P&L for spot ±10%, ±20%
        return [
            {"spot_at_expiry": spot * 0.8, "pnl": 0},
            {"spot_at_expiry": spot * 0.9, "pnl": 0},
            {"spot_at_expiry": spot, "pnl": 0},
            {"spot_at_expiry": spot * 1.1, "pnl": 0},
            {"spot_at_expiry": spot * 1.2, "pnl": 0}
        ]
    
    def _rank_strategies(self, strategies: List[Dict]) -> List[Dict]:
        """Rank strategies by risk-reward ratio."""
        for strat in strategies:
            if strat["max_loss"] != 0:
                strat["risk_reward_ratio"] = strat["max_profit"] / abs(strat["max_loss"])
            else:
                strat["risk_reward_ratio"] = 0
        
        return sorted(strategies, key=lambda s: s["risk_reward_ratio"], reverse=True)
```

#### 2.4 Extend Upstox Broker for Options

**File:** `backend/app/services/broker/upstox.py` (Add methods)

```python
async def get_option_chain(self, symbol: str, expiry: str) -> Dict[str, Any]:
    """Fetch option chain from Upstox."""
    try:
        # Adjust based on actual Upstox API endpoint
        endpoint = f"{self.BASE_URL}/option/chain"
        params = {"instrument_key": f"NSE_FO|{symbol}", "expiry_date": expiry}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params=params, headers=self._get_headers()) as resp:
                if resp.status != 200:
                    logger.error(f"Option chain fetch failed: {resp.status}")
                    return {}
                
                data = await resp.json()
                return data.get("data", {})
    
    except Exception as e:
        logger.error(f"Option chain error: {e}")
        return {}

async def place_option_strategy(self, strategy: Dict[str, Any]) -> List[str]:
    """Place all legs of an option strategy."""
    order_ids = []
    
    try:
        for leg in strategy["legs"]:
            order_payload = {
                "quantity": leg["quantity"],
                "product": "D",  # Delivery/MIS
                "validity": "DAY",
                "price": 0,
                "tag": f"strategy_{strategy['id']}",
                "instrument_token": self._get_option_instrument_token(
                    strategy["underlying"],
                    leg["strike"],
                    leg["option_type"],
                    strategy["expiry"]
                ),
                "order_type": "MARKET",
                "transaction_type": "BUY" if leg["type"] == "BUY" else "SELL",
                "disclosed_quantity": 0,
                "trigger_price": 0,
                "is_amo": False
            }
            
            # Place order
            result = await self.place_order(**order_payload)
            if result.get("status") == "success":
                order_ids.append(result["data"]["order_id"])
            else:
                logger.error(f"Leg failed: {leg}")
                # Rollback previous legs if needed
                break
        
        return order_ids
    
    except Exception as e:
        logger.error(f"Strategy execution error: {e}")
        return []

def _get_option_instrument_token(self, symbol: str, strike: float, option_type: str, expiry: str) -> str:
    """Get Upstox instrument token for option."""
    # Format: NSE_FO|RELIANCE25OCT2450CE
    expiry_str = datetime.strptime(expiry, "%Y-%m-%d").strftime("%d%b").upper()
    return f"NSE_FO|{symbol}{expiry_str[:5]}{int(strike)}{option_type}"
```

#### 2.5 Options API Router

**New File:** `backend/app/routers/options.py`

```python
"""Options API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import date
from ..database import get_db
from ..services.ingestion.options_chain_feed import OptionsChainFeed
from ..services.options_engine import OptionsEngine
from ..services.broker.upstox import UpstoxBroker
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/options", tags=["Options"])

class StrategyGenerateRequest(BaseModel):
    symbol: str
    expiry: date
    account_id: int
    strategy_types: List[str]
    max_risk: float = 10000

class StrategyExecuteRequest(BaseModel):
    strategy_id: int
    account_id: int
    approval_id: int
    quantity: int = 1

@router.get("/chain")
async def get_option_chain(
    symbol: str,
    expiry: str,
    db: Session = Depends(get_db)
):
    """Get option chain for symbol and expiry."""
    feed = OptionsChainFeed(db)
    chain = await feed.fetch_chain(symbol, expiry)
    
    if not chain:
        raise HTTPException(status_code=404, detail="Option chain not found")
    
    return chain

@router.post("/strategy/generate")
async def generate_strategies(
    request: StrategyGenerateRequest,
    db: Session = Depends(get_db)
):
    """Generate option strategies."""
    engine = OptionsEngine(db)
    strategies = await engine.generate_strategies(
        symbol=request.symbol,
        expiry=request.expiry,
        account_id=request.account_id,
        strategy_types=request.strategy_types,
        max_risk=request.max_risk
    )
    
    return {"strategies": strategies, "count": len(strategies)}

@router.post("/strategy/execute")
async def execute_strategy(
    request: StrategyExecuteRequest,
    db: Session = Depends(get_db)
):
    """Execute an option strategy."""
    from ..database import OptionStrategy
    
    # Get strategy
    strategy = db.query(OptionStrategy).filter(
        OptionStrategy.id == request.strategy_id
    ).first()
    
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Place orders
    broker = UpstoxBroker()
    order_ids = await broker.place_option_strategy(strategy.__dict__)
    
    if not order_ids:
        raise HTTPException(status_code=503, detail="Strategy execution failed")
    
    # Update strategy
    strategy.status = "EXECUTED"
    strategy.order_ids = order_ids
    strategy.executed_at = datetime.now(pytz.timezone('Asia/Kolkata'))
    db.commit()
    
    return {"status": "executed", "order_ids": order_ids}
```

**Register in `main.py`:**
```python
from .routers import options
app.include_router(options.router)
```

### Frontend Implementation (Brief)

**New File:** `frontend/static/js/options.js`

```javascript
class OptionsViewer {
    async loadChain(symbol, expiry) {
        const data = await api.get(`/api/options/chain?symbol=${symbol}&expiry=${expiry}`);
        this.renderChain(data);
    }
    
    renderChain(data) {
        // Render option chain table with strikes, IVs, OI
        // Add chart for IV smile
        // Add PCR and IV Rank widgets
    }
    
    async generateStrategies(symbol, expiry, accountId) {
        const strategies = await api.post('/api/options/strategy/generate', {
            symbol, expiry, account_id: accountId,
            strategy_types: ['IRON_CONDOR', 'BULL_PUT_SPREAD'],
            max_risk: 10000
        });
        
        this.renderStrategies(strategies.strategies);
    }
}
```

### Testing

**File:** `tests/test_options.py` (12+ test cases)

```python
"""Options engine tests."""
import pytest
from backend.app.services.options_engine import OptionsEngine
from backend.app.services.ingestion.options_chain_feed import OptionsChainFeed

class TestOptionsChainFeed:
    @pytest.mark.asyncio
    async def test_fetch_chain(self, db):
        """Test option chain ingestion."""
        feed = OptionsChainFeed(db)
        chain = await feed.fetch_chain("RELIANCE", "2025-10-31")
        assert "spot_price" in chain
        assert chain["strikes_count"] > 0
    
    @pytest.mark.asyncio
    async def test_iv_rank_calculation(self, db):
        """Test IV rank over 52 weeks."""
        # Test implementation
        pass

class TestOptionsEngine:
    @pytest.mark.asyncio
    async def test_iron_condor_generation(self, db):
        """Test iron condor strategy generation."""
        engine = OptionsEngine(db)
        # Setup mock chain data
        # Generate strategy
        # Assert legs, max_profit, max_loss
        pass
    
    @pytest.mark.asyncio
    async def test_strategy_ranking(self, db):
        """Test strategies ranked by risk-reward."""
        # Test implementation
        pass

# Additional tests for Greeks, P&L scenarios, execution, etc.
```

### Documentation

**File:** `PHASE2_P1.2_OPTIONS.md` - Complete documentation of options module

### Rollout

- **Day 4-5:** Implement models, chain feed, options engine
- **Day 6-7:** Implement API endpoints, Upstox integration
- **Day 8:** Frontend options viewer
- **Day 9:** Testing and documentation

**Feature Flag:** `OPTIONS_TRADING_ENABLED=false` (read-only first, then enable execution)

---

## 🌐 STAGE 3: P1.3 - Institutional Flows & Policy Awareness (Days 10-14)

### Problem Statement
- ❌ No FPI/DII flow data → missing institutional sentiment
- ❌ No insider trading tracking → missing smart money signals
- ❌ No RBI/SEBI policy feed → missing macro context
- ❌ No LLM summarization → raw policy text unusable

### Desired Outcomes (DoD)
✅ Daily FPI/DII flow ingestion from NSDL/AMFI  
✅ Insider trading feed (SAST + bulk deals) from NSE  
✅ Policy feed scraper for RBI/SEBI/PIB announcements  
✅ AnalystAgent summarizes policy with stance + impacted sectors  
✅ Flow & policy evidence in trade cards  
✅ Dashboard widget showing daily flows + policy highlights  
✅ 8+ test cases covering ingestion and summarization  

### Data Contracts

#### InstitutionalFlow
```json
{
  "date": "2025-10-22",
  "fpi_equity_flow": 2350.5,
  "dii_equity_flow": -1800.0,
  "fii_derivative_flow": 850.0,
  "fpi_debt_flow": 1200.0,
  "total_flow": 2600.5,
  "sentiment": "BULLISH"
}
```

#### InsiderTrade
```json
{
  "symbol": "INFY",
  "acquirer_name": "John Doe",
  "trade_type": "ACQUISITION",
  "quantity": 50000,
  "value": 7250000,
  "trade_date": "2025-10-20",
  "disclosure_date": "2025-10-22",
  "source": "NSE_SAST"
}
```

#### PolicyUpdate
```json
{
  "headline": "RBI raises repo rate by 25bps to 6.75%",
  "source": "RBI",
  "date": "2025-10-22",
  "stance": "HAWKISH",
  "impacted_sectors": ["Banks", "NBFCs", "Real Estate"],
  "confidence": 0.88,
  "summary": "RBI indicates focus on inflation control...",
  "key_points": ["Repo rate to 6.75%", "CRR unchanged", "GDP forecast revised down"],
  "url": "https://rbi.org.in/..."
}
```

### API Endpoints

**1. GET /api/flows/daily?date={YYYY-MM-DD}**
Returns: FPI/DII flows for specified date

**2. GET /api/flows/insider?symbol={symbol}&days={N}**
Returns: Insider trades for symbol in last N days

**3. GET /api/policy/updates?days={N}**
Returns: Policy updates in last N days with LLM summaries

### Backend Implementation

#### 3.1 Database Models

**File:** `backend/app/database.py` (Add)

```python
class InstitutionalFlow(Base):
    __tablename__ = "institutional_flows"
    
    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False, index=True)
    
    fpi_equity_flow = Column(Float)  # Crores
    dii_equity_flow = Column(Float)
    fii_derivative_flow = Column(Float)
    fpi_debt_flow = Column(Float)
    total_flow = Column(Float)
    sentiment = Column(String(20))  # BULLISH, BEARISH, NEUTRAL
    
    source = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))

class InsiderTrade(Base):
    __tablename__ = "insider_trades"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    acquirer_name = Column(String(200))
    trade_type = Column(String(50))  # ACQUISITION, DISPOSAL
    quantity = Column(Integer)
    value = Column(Float)
    trade_date = Column(Date, index=True)
    disclosure_date = Column(Date)
    source = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))

class PolicyUpdate(Base):
    __tablename__ = "policy_updates"
    
    id = Column(Integer, primary_key=True)
    headline = Column(Text, nullable=False)
    source = Column(String(50), index=True)  # RBI, SEBI, PIB
    date = Column(Date, index=True)
    
    # LLM analysis
    stance = Column(String(20))  # HAWKISH, DOVISH, NEUTRAL
    impacted_sectors = Column(JSON)
    confidence = Column(Float)
    summary = Column(Text)
    key_points = Column(JSON)
    
    url = Column(Text)
    raw_content = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))
```

#### 3.2 Flows Feed

**New File:** `backend/app/services/ingestion/flows_feed.py`

```python
"""FPI/DII institutional flow ingestion."""
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
import pytz
from typing import Dict, Any
from sqlalchemy.orm import Session
from ...database import InstitutionalFlow
import logging

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class FlowsFeed:
    """Fetch FPI/DII flows from NSDL and AMFI."""
    
    NSDL_URL = "https://www.fpi.nsdl.co.in/web/Reports/LatestReport.aspx"
    
    def __init__(self, db: Session):
        self.db = db
    
    async def fetch_daily_flows(self, date: str = None) -> Dict[str, Any]:
        """Fetch flows for specified date (or latest)."""
        if not date:
            date = datetime.now(IST).strftime("%Y-%m-%d")
        
        try:
            # Scrape NSDL (adjust based on actual HTML structure)
            flows = await self._scrape_nsdl(date)
            
            if not flows:
                logger.error(f"No flow data for {date}")
                return {}
            
            # Calculate total and sentiment
            total_flow = flows.get("fpi_equity_flow", 0) + flows.get("dii_equity_flow", 0)
            
            if total_flow > 1000:
                sentiment = "BULLISH"
            elif total_flow < -1000:
                sentiment = "BEARISH"
            else:
                sentiment = "NEUTRAL"
            
            # Store in DB
            flow_entry = InstitutionalFlow(
                date=datetime.strptime(date, "%Y-%m-%d").date(),
                fpi_equity_flow=flows.get("fpi_equity_flow"),
                dii_equity_flow=flows.get("dii_equity_flow"),
                fii_derivative_flow=flows.get("fii_derivative_flow"),
                fpi_debt_flow=flows.get("fpi_debt_flow"),
                total_flow=total_flow,
                sentiment=sentiment,
                source="NSDL"
            )
            
            self.db.merge(flow_entry)
            self.db.commit()
            
            logger.info(f"Fetched flows for {date}: FPI={flows['fpi_equity_flow']}, DII={flows['dii_equity_flow']}")
            
            return flows
        
        except Exception as e:
            logger.error(f"Flows feed error: {e}", exc_info=True)
            return {}
    
    async def _scrape_nsdl(self, date: str) -> Dict[str, float]:
        """Scrape NSDL for FPI/FII flows."""
        # Placeholder: implement actual scraping logic
        # Use BeautifulSoup or requests to parse HTML/CSV
        
        return {
            "fpi_equity_flow": 0.0,
            "dii_equity_flow": 0.0,
            "fii_derivative_flow": 0.0,
            "fpi_debt_flow": 0.0
        }
```

#### 3.3 Insider Feed

**New File:** `backend/app/services/ingestion/insider_feed.py`

```python
"""Insider trading and bulk deal ingestion from NSE."""
import aiohttp
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from ...database import InsiderTrade
import logging

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class InsiderFeed:
    """Fetch insider trades (SAST) and bulk deals from NSE."""
    
    NSE_SAST_URL = "https://www.nseindia.com/api/corporates-pit"
    NSE_BULK_URL = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
    
    def __init__(self, db: Session):
        self.db = db
    
    async def fetch_recent_trades(self, days_back: int = 7) -> List[Dict[str, Any]]:
        """Fetch insider trades from last N days."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            }
            
            trades = []
            
            # Fetch SAST data
            async with aiohttp.ClientSession() as session:
                async with session.get(self.NSE_SAST_URL, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        trades.extend(self._parse_sast(data))
                
                # Fetch bulk deals
                async with session.get(self.NSE_BULK_URL, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        trades.extend(self._parse_bulk_deals(data))
            
            # Store in DB
            for trade in trades:
                insider_entry = InsiderTrade(**trade)
                self.db.merge(insider_entry)
            
            self.db.commit()
            
            logger.info(f"Fetched {len(trades)} insider trades")
            return trades
        
        except Exception as e:
            logger.error(f"Insider feed error: {e}", exc_info=True)
            return []
    
    def _parse_sast(self, data: Dict) -> List[Dict]:
        """Parse NSE SAST data."""
        trades = []
        for item in data.get("data", []):
            trades.append({
                "symbol": item.get("symbol"),
                "acquirer_name": item.get("acqName"),
                "trade_type": "ACQUISITION" if "acquisition" in item.get("acqMode", "").lower() else "DISPOSAL",
                "quantity": int(item.get("befAcqSharesNo", 0)),
                "value": 0,  # Not provided in SAST
                "trade_date": datetime.strptime(item.get("date"), "%d-%b-%Y").date() if item.get("date") else None,
                "disclosure_date": datetime.now(IST).date(),
                "source": "NSE_SAST"
            })
        return trades
    
    def _parse_bulk_deals(self, data: Dict) -> List[Dict]:
        """Parse NSE bulk deal data."""
        trades = []
        for item in data.get("data", []):
            trades.append({
                "symbol": item.get("symbol"),
                "acquirer_name": item.get("clientName"),
                "trade_type": "BUY" if item.get("buyOrSell") == "B" else "SELL",
                "quantity": int(item.get("quantityTraded", 0)),
                "value": float(item.get("tradePrice", 0)) * int(item.get("quantityTraded", 0)),
                "trade_date": datetime.strptime(item.get("date"), "%d-%b-%Y").date() if item.get("date") else None,
                "disclosure_date": datetime.now(IST).date(),
                "source": "NSE_BULK_DEAL"
            })
        return trades
```

#### 3.4 Policy Feed

**New File:** `backend/app/services/ingestion/policy_feed.py`

```python
"""Policy announcement scraper for RBI/SEBI/PIB."""
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from ...database import PolicyUpdate
import logging

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class PolicyFeed:
    """Scrape policy announcements from RBI, SEBI, PIB."""
    
    RBI_PRESS_URL = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"
    SEBI_PRESS_URL = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecent=yes"
    PIB_URL = "https://pib.gov.in/allRel.aspx"
    
    def __init__(self, db: Session):
        self.db = db
    
    async def fetch_recent_policies(self, days_back: int = 7) -> List[Dict[str, Any]]:
        """Fetch policy updates from last N days."""
        try:
            policies = []
            
            # Scrape each source
            policies.extend(await self._scrape_rbi())
            policies.extend(await self._scrape_sebi())
            policies.extend(await self._scrape_pib())
            
            # Store raw data (LLM analysis done separately)
            for policy in policies:
                policy_entry = PolicyUpdate(
                    headline=policy["headline"],
                    source=policy["source"],
                    date=policy["date"],
                    url=policy["url"],
                    raw_content=policy["raw_content"]
                )
                self.db.add(policy_entry)
            
            self.db.commit()
            
            logger.info(f"Fetched {len(policies)} policy updates")
            return policies
        
        except Exception as e:
            logger.error(f"Policy feed error: {e}", exc_info=True)
            return []
    
    async def _scrape_rbi(self) -> List[Dict]:
        """Scrape RBI press releases."""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.RBI_PRESS_URL, headers=headers) as resp:
                    if resp.status != 200:
                        return []
                    
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Parse based on RBI HTML structure
                    # Placeholder implementation
                    return []
        
        except Exception as e:
            logger.error(f"RBI scrape error: {e}")
            return []
    
    async def _scrape_sebi(self) -> List[Dict]:
        """Scrape SEBI press releases."""
        # Similar to RBI
        return []
    
    async def _scrape_pib(self) -> List[Dict]:
        """Scrape PIB announcements."""
        # Similar to RBI
        return []
```

#### 3.5 Analyst Agent for Policy Summarization

**New File:** `backend/app/services/analyst_agent.py`

```python
"""LLM-powered analyst agent for policy summarization."""
from typing import Dict, Any
from sqlalchemy.orm import Session
from .llm.base import get_llm_provider
from ..database import PolicyUpdate
import logging

logger = logging.getLogger(__name__)

class AnalystAgent:
    """Summarize policy updates and classify stance."""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm = get_llm_provider()
        
        self.system_prompt = """You are a financial policy analyst.
Analyze policy announcements and provide:
1. Stance: HAWKISH / DOVISH / NEUTRAL
2. Impacted sectors: List of sectors affected
3. Confidence: 0-1 score
4. Summary: 2-3 sentence overview
5. Key points: Bullet list of main takeaways

Output as JSON."""
    
    async def analyze_policy(self, policy_id: int) -> Dict[str, Any]:
        """Analyze a policy update using LLM."""
        policy = self.db.query(PolicyUpdate).filter(PolicyUpdate.id == policy_id).first()
        
        if not policy or not policy.raw_content:
            logger.error(f"Policy {policy_id} not found or no content")
            return {}
        
        try:
            prompt = f"""
Analyze this policy announcement:

Source: {policy.source}
Headline: {policy.headline}
Date: {policy.date}
Content: {policy.raw_content[:2000]}

Provide structured analysis in JSON format with:
- stance (HAWKISH/DOVISH/NEUTRAL)
- impacted_sectors (array of sector names)
- confidence (0-1)
- summary (2-3 sentences)
- key_points (array of strings)
"""
            
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt=self.system_prompt,
                temperature=0.3,
                max_tokens=500
            )
            
            # Parse JSON response
            import json
            analysis = json.loads(response)
            
            # Update policy record
            policy.stance = analysis.get("stance", "NEUTRAL")
            policy.impacted_sectors = analysis.get("impacted_sectors", [])
            policy.confidence = analysis.get("confidence", 0.5)
            policy.summary = analysis.get("summary", "")
            policy.key_points = analysis.get("key_points", [])
            
            self.db.commit()
            
            logger.info(f"Analyzed policy {policy_id}: {policy.stance}")
            
            return analysis
        
        except Exception as e:
            logger.error(f"Policy analysis error: {e}", exc_info=True)
            return {}
    
    async def analyze_pending_policies(self) -> int:
        """Analyze all policies without LLM analysis."""
        policies = self.db.query(PolicyUpdate).filter(
            PolicyUpdate.stance.is_(None)
        ).all()
        
        count = 0
        for policy in policies:
            await self.analyze_policy(policy.id)
            count += 1
        
        return count
```

### API Endpoints

**New File:** `backend/app/routers/flows.py`

```python
"""Flows and policy API endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..database import get_db, InstitutionalFlow, InsiderTrade, PolicyUpdate

router = APIRouter(prefix="/api/flows", tags=["Flows & Policy"])

@router.get("/daily")
async def get_daily_flows(
    date: str = Query(None),
    db: Session = Depends(get_db)
):
    """Get institutional flows for a date."""
    if not date:
        date = datetime.now().date()
    else:
        date = datetime.strptime(date, "%Y-%m-%d").date()
    
    flow = db.query(InstitutionalFlow).filter(InstitutionalFlow.date == date).first()
    
    if not flow:
        return {"error": "No data for date"}
    
    return {
        "date": str(flow.date),
        "fpi_equity_flow": flow.fpi_equity_flow,
        "dii_equity_flow": flow.dii_equity_flow,
        "total_flow": flow.total_flow,
        "sentiment": flow.sentiment
    }

@router.get("/insider")
async def get_insider_trades(
    symbol: str = Query(...),
    days: int = Query(30),
    db: Session = Depends(get_db)
):
    """Get insider trades for a symbol."""
    cutoff_date = datetime.now().date() - timedelta(days=days)
    
    trades = db.query(InsiderTrade).filter(
        InsiderTrade.symbol == symbol,
        InsiderTrade.trade_date >= cutoff_date
    ).order_by(InsiderTrade.trade_date.desc()).all()
    
    return {"trades": [
        {
            "acquirer_name": t.acquirer_name,
            "trade_type": t.trade_type,
            "quantity": t.quantity,
            "value": t.value,
            "trade_date": str(t.trade_date)
        }
        for t in trades
    ]}

@router.get("/policy/updates")
async def get_policy_updates(
    days: int = Query(7),
    db: Session = Depends(get_db)
):
    """Get recent policy updates."""
    cutoff_date = datetime.now().date() - timedelta(days=days)
    
    policies = db.query(PolicyUpdate).filter(
        PolicyUpdate.date >= cutoff_date
    ).order_by(PolicyUpdate.date.desc()).all()
    
    return {"policies": [
        {
            "headline": p.headline,
            "source": p.source,
            "date": str(p.date),
            "stance": p.stance,
            "impacted_sectors": p.impacted_sectors,
            "summary": p.summary
        }
        for p in policies
    ]}
```

### Testing & Documentation

**File:** `tests/test_flows_policy.py` (8+ tests)
**File:** `PHASE2_P1.3_FLOWS_POLICY.md` (Complete documentation)

### Rollout

- **Day 10-11:** Implement flows & insider feeds
- **Day 12-13:** Implement policy feed & analyst agent
- **Day 14:** API, frontend widget, testing

---

_Continue with remaining stages P1.4, P2.1, P2.2, P3.1, Testing Strategy, Agent Collaboration Protocol, and Open Questions in next section..._

---

_Generated: 2025-10-22 | Phase 2 Implementation Plan - Stages 1-3 Complete_

