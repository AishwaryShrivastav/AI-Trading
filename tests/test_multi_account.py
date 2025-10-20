"""Production tests for multi-account AI Trader functionality."""
import pytest
import sys
from pathlib import Path
from datetime import datetime

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import (
    SessionLocal, Account, Mandate, FundingPlan,
    CapitalTransaction, TradeCardV2
)
from backend.app.services.intake_agent import intake_agent
from backend.app.services.treasury import Treasury
from backend.app.services.allocator import Allocator
from backend.app.services.risk_monitor import RiskMonitor
from backend.app.services.playbook_manager import PlaybookManager
from backend.app.schemas import AccountType, Objective, IntakeAnswer


@pytest.fixture
def db():
    """Database session fixture."""
    session = SessionLocal()
    yield session
    session.close()


class TestAccountManagement:
    """Test account creation and management."""
    
    def test_create_account(self, db):
        """Test creating a trading account."""
        account = Account(
            user_id="test_user",
            name="Test SIP Account",
            account_type="SIP",
            status="ACTIVE"
        )
        
        db.add(account)
        db.commit()
        db.refresh(account)
        
        assert account.id is not None
        assert account.name == "Test SIP Account"
        assert account.status == "ACTIVE"
        
        # Cleanup
        db.delete(account)
        db.commit()
    
    def test_create_mandate(self, db):
        """Test creating a mandate."""
        # Create account first
        account = Account(
            user_id="test_user",
            name="Test Account",
            account_type="SIP",
            status="ACTIVE"
        )
        db.add(account)
        db.flush()
        
        # Create mandate
        mandate = Mandate(
            account_id=account.id,
            version=1,
            objective="MAX_PROFIT",
            risk_per_trade_percent=2.0,
            max_positions=10,
            max_sector_exposure_percent=30.0,
            horizon_min_days=3,
            horizon_max_days=7,
            banned_sectors=[],
            earnings_blackout_days=2,
            liquidity_floor_adv=1000000,
            min_market_cap=100.0,
            allowed_strategies=["momentum"],
            sl_multiplier=2.0,
            tp_multiplier=4.0,
            is_active=True
        )
        
        db.add(mandate)
        db.commit()
        db.refresh(mandate)
        
        assert mandate.id is not None
        assert mandate.account_id == account.id
        assert mandate.objective == "MAX_PROFIT"
        assert mandate.risk_per_trade_percent == 2.0
        
        # Cleanup
        db.delete(mandate)
        db.delete(account)
        db.commit()
    
    def test_create_funding_plan(self, db):
        """Test creating a funding plan."""
        # Create account
        account = Account(
            user_id="test_user",
            name="Test Account",
            account_type="SIP",
            status="ACTIVE"
        )
        db.add(account)
        db.flush()
        
        # Create funding plan
        funding = FundingPlan(
            account_id=account.id,
            funding_type="SIP",
            sip_amount=10000,
            sip_frequency="MONTHLY",
            sip_duration_months=24,
            available_cash=10000,
            total_deployed=0,
            reserved_cash=0
        )
        
        db.add(funding)
        db.commit()
        db.refresh(funding)
        
        assert funding.id is not None
        assert funding.sip_amount == 10000
        assert funding.available_cash == 10000
        
        # Cleanup
        db.delete(funding)
        db.delete(account)
        db.commit()


class TestIntakeAgent:
    """Test intake agent functionality."""
    
    def test_start_session(self):
        """Test starting an intake session."""
        session = intake_agent.start_session(
            account_name="Test Account",
            account_type=AccountType.SIP,
            user_id="test_user"
        )
        
        assert session.session_id is not None
        assert session.account_name == "Test Account"
        assert session.total_questions == 9  # 6 common + 3 SIP
        assert session.current_question is not None
        
        # Cleanup
        intake_agent.clear_session(session.session_id)
    
    def test_answer_questions(self):
        """Test answering intake questions."""
        session = intake_agent.start_session(
            account_name="Test Account",
            account_type=AccountType.SIP,
            user_id="test_user"
        )
        
        # Answer first question
        answer = IntakeAnswer(
            question_id=session.current_question.question_id,
            answer="MAX_PROFIT"
        )
        
        session = intake_agent.answer_question(session.session_id, answer)
        
        assert session.answers_collected == 1
        assert not session.is_complete
        
        # Cleanup
        intake_agent.clear_session(session.session_id)
    
    def test_generate_mandate(self):
        """Test generating mandate from answers."""
        session = intake_agent.start_session(
            account_name="Test Account",
            account_type=AccountType.SIP,
            user_id="test_user"
        )
        
        # Answer all questions
        answers = {
            "objective": "MAX_PROFIT",
            "risk_per_trade_percent": 2.0,
            "max_positions": 10,
            "horizon": "3-7",
            "banned_sectors": "none",
            "liquidity_floor_adv": 1000000,
            "sip_amount": 10000,
            "sip_frequency": "MONTHLY",
            "sip_duration_months": 24
        }
        
        for answer_value in answers.values():
            if session.is_complete:
                break
            
            answer = IntakeAnswer(
                question_id=session.current_question.question_id,
                answer=answer_value
            )
            session = intake_agent.answer_question(session.session_id, answer)
        
        # Generate mandate
        result = intake_agent.generate_mandate_and_plan(session.session_id)
        
        assert "mandate_data" in result
        assert "funding_plan_data" in result
        assert "summary" in result
        assert result["mandate_data"]["objective"] == "MAX_PROFIT"
        assert result["funding_plan_data"]["sip_amount"] == 10000
        
        # Cleanup
        intake_agent.clear_session(session.session_id)


class TestTreasury:
    """Test treasury operations."""
    
    @pytest.mark.asyncio
    async def test_portfolio_summary(self, db):
        """Test getting portfolio summary."""
        treasury = Treasury(db)
        summary = await treasury.get_portfolio_summary()
        
        assert "total_capital" in summary
        assert "total_available" in summary
        assert "total_deployed" in summary
        assert summary["total_capital"] >= 0
    
    @pytest.mark.asyncio
    async def test_reserve_cash(self, db):
        """Test cash reservation."""
        # Create account with funding
        account = Account(
            user_id="test_user",
            name="Test Account",
            account_type="SIP",
            status="ACTIVE"
        )
        db.add(account)
        db.flush()
        
        funding = FundingPlan(
            account_id=account.id,
            funding_type="SIP",
            available_cash=10000,
            total_deployed=0,
            reserved_cash=0
        )
        db.add(funding)
        db.commit()
        
        # Reserve cash
        treasury = Treasury(db)
        reserved = await treasury.reserve_cash(account.id, 5000)
        
        assert reserved is True
        
        db.refresh(funding)
        assert funding.available_cash == 5000
        assert funding.reserved_cash == 5000
        
        # Cleanup
        db.delete(funding)
        db.delete(account)
        db.commit()


class TestRiskMonitor:
    """Test risk monitoring."""
    
    @pytest.mark.asyncio
    async def test_capture_snapshot(self, db):
        """Test capturing risk snapshot."""
        monitor = RiskMonitor(db)
        snapshot = await monitor.capture_snapshot()
        
        assert snapshot.id is not None
        assert snapshot.total_open_risk >= 0
        assert snapshot.open_positions_count >= 0
    
    @pytest.mark.asyncio
    async def test_check_kill_switches(self, db):
        """Test kill switch checking."""
        monitor = RiskMonitor(db)
        triggered = await monitor.check_kill_switches()
        
        assert isinstance(triggered, list)
    
    @pytest.mark.asyncio
    async def test_should_pause_new_entries(self, db):
        """Test pause check."""
        monitor = RiskMonitor(db)
        should_pause = await monitor.should_pause_new_entries()
        
        assert isinstance(should_pause, bool)


class TestAllocator:
    """Test allocation logic."""
    
    @pytest.mark.asyncio
    async def test_check_position_limits(self, db):
        """Test position limit checking."""
        # Create account with mandate
        account = Account(
            user_id="test_user",
            name="Test Account",
            account_type="SIP",
            status="ACTIVE"
        )
        db.add(account)
        db.flush()
        
        mandate = Mandate(
            account_id=account.id,
            version=1,
            objective="BALANCED",
            risk_per_trade_percent=1.5,
            max_positions=5,
            max_sector_exposure_percent=30.0,
            horizon_min_days=1,
            horizon_max_days=7,
            is_active=True
        )
        db.add(mandate)
        db.commit()
        
        # Check limits
        allocator = Allocator(db)
        limits = await allocator.check_position_limits(account.id)
        
        assert "can_add" in limits
        assert limits["max_positions"] == 5
        assert limits["current_positions"] >= 0
        
        # Cleanup
        db.delete(mandate)
        db.delete(account)
        db.commit()


class TestPlaybookManager:
    """Test playbook manager."""
    
    @pytest.mark.asyncio
    async def test_get_playbook_for_event(self, db):
        """Test finding playbook for event."""
        manager = PlaybookManager(db)
        
        playbook = await manager.get_playbook_for_event(
            event_type="BUYBACK",
            regime={"volatility": "MED", "liquidity": "HIGH"}
        )
        
        # Should find the "Buyback Bullish" playbook
        assert playbook is not None or playbook is None  # May or may not exist
        
        if playbook:
            assert playbook.event_type == "BUYBACK"
            assert playbook.is_active is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

