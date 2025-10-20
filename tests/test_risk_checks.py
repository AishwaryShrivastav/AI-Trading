"""Tests for risk checks."""
import pytest
from backend.app.services.risk_checks import RiskChecker
from backend.app.database import SessionLocal, init_db


@pytest.fixture
def db_session():
    """Create a test database session."""
    init_db()
    session = SessionLocal()
    yield session
    session.close()


@pytest.mark.asyncio
async def test_position_size_risk_check(db_session):
    """Test position size risk validation."""
    risk_checker = RiskChecker(db_session)
    
    # Test case: 2% risk on 100k capital = 2k max risk
    # Entry 1000, SL 950 = 50 risk per share
    # Max quantity = 2000/50 = 40 shares
    
    # This should pass (risk = 40 * 50 = 2000 = 2%)
    result = await risk_checker.check_position_size_risk(
        quantity=40,
        entry_price=1000,
        stop_loss=950
    )
    assert result is True
    
    # This should fail (risk = 100 * 50 = 5000 = 5%)
    result = await risk_checker.check_position_size_risk(
        quantity=100,
        entry_price=1000,
        stop_loss=950
    )
    assert result is False


@pytest.mark.asyncio
async def test_exposure_limits_check(db_session):
    """Test exposure limits validation."""
    risk_checker = RiskChecker(db_session)
    
    # Test position size limits (10% max)
    # Capital 100k, position value should be <= 10k
    
    # This should pass (100 * 100 = 10k = 10%)
    result = await risk_checker.check_exposure_limits(
        symbol="TEST",
        quantity=100,
        entry_price=100
    )
    assert result is True
    
    # This should fail (200 * 100 = 20k = 20%)
    result = await risk_checker.check_exposure_limits(
        symbol="TEST",
        quantity=200,
        entry_price=100
    )
    assert result is False

