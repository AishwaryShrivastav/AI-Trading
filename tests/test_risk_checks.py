"""Tests for risk checks and guardrails API (no fake data)."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from datetime import datetime, timedelta
from backend.app.database import MarketDataCache, Feature, Event, EarningsCalendar
from backend.app.services.risk_checks import RiskChecker
from backend.app.database import SessionLocal, init_db, Setting, Mandate, FundingPlan, PositionV2


@pytest.fixture
def db_session():
    """Create a test database session."""
    init_db()
    session = SessionLocal()
    # Hard reset relevant tables for deterministic tests
    session.query(PositionV2).delete()
    session.query(Mandate).delete()
    session.query(FundingPlan).delete()
    session.query(Setting).filter(Setting.key == "total_capital").delete()
    session.commit()

    # Controlled capital and mandate for account 1
    session.add(Setting(key="total_capital", value=100000))
    session.add(Mandate(
        account_id=1,
        objective="BALANCED",
        risk_per_trade_percent=2.0,
        max_positions=10,
        max_sector_exposure_percent=30.0,
        horizon_min_days=1,
        horizon_max_days=7,
        is_active=True
    ))
    session.add(FundingPlan(
        account_id=1,
        funding_type="LUMP_SUM",
        total_deployed=0.0,
        available_cash=100000.0
    ))
    session.commit()
    yield session
    session.close()


@pytest.mark.asyncio
async def test_position_size_risk_check(db_session):
    """Test position size risk validation."""
    risk_checker = RiskChecker(db_session)

    # Provide account context via Setting total_capital fallback
    result = await risk_checker.check_position_size_risk(
        account_id=1,
        entry_price=1000,
        stop_loss=950,
        quantity=40,
        warnings=[]
    )
    assert result is True
    
    # This should fail (risk = 100 * 50 = 5000 = 5%)
    result = await risk_checker.check_position_size_risk(
        account_id=1,
        entry_price=1000,
        stop_loss=950,
        quantity=100,
        warnings=[]
    )
    assert result is False


@pytest.mark.asyncio
async def test_exposure_limits_check(db_session):
    """Test exposure limits validation."""
    risk_checker = RiskChecker(db_session)

    # Capital 100k, sector exposure limit default 30%
    result = await risk_checker.check_sector_exposure(
        account_id=1,
        sector="IT",
        new_position_value=10000,
        warnings=[]
    )
    assert result is True
    
    # This should fail if exposure exceeds 30%
    result = await risk_checker.check_sector_exposure(
        account_id=1,
        sector="IT",
        new_position_value=40000,
        warnings=[]
    )
    assert result is False


def test_guardrails_api_smoke():
    """Smoke test for /api/guardrails/check endpoint."""
    client = TestClient(app)
    payload = {
        "symbol": "INFY",
        "account_id": 1,
        "quantity": 10,
        "entry_price": 1500.0,
        "stop_loss": 1450.0,
        "trade_type": "LONG",
        "exchange": "NSE"
    }
    res = client.post("/api/guardrails/check", json=payload)
    assert res.status_code in (200, 503)

