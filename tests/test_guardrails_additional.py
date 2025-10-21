import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import (
    SessionLocal, init_db,
    Setting, Mandate, FundingPlan,
    MarketDataCache, Feature, Event, EarningsCalendar
)
from backend.app.services.risk_checks import RiskChecker


@pytest.fixture
def db_session():
    init_db()
    session = SessionLocal()
    # Reset
    session.query(MarketDataCache).delete()
    session.query(Feature).delete()
    session.query(Event).delete()
    session.query(EarningsCalendar).delete()
    session.query(Mandate).delete()
    session.query(FundingPlan).delete()
    session.query(Setting).filter(Setting.key == "total_capital").delete()
    session.commit()

    # Baseline setup
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
async def test_liquidity_check_blocks_on_large_trade(db_session):
    # Seed 20 days of volume at 100k per day
    now = datetime.utcnow()
    for i in range(20):
        db_session.add(MarketDataCache(
            symbol="INFY", exchange="NSE", interval="1D",
            timestamp=now - timedelta(days=i), open=1, high=1, low=1, close=1, volume=100000
        ))
    db_session.commit()

    checker = RiskChecker(db_session)
    warnings = []
    # 10% of ADV should fail (ADV ~100k → 10k qty > 5% limit 5k)
    ok = await checker.check_liquidity("INFY", 10000, warnings)
    assert ok is False
    assert any(w.code == "LIQUIDITY_BELOW_THRESHOLD" for w in warnings)


@pytest.mark.asyncio
async def test_event_window_warns_around_earnings(db_session):
    # Seed calendar with earnings tomorrow
    tomorrow = datetime.utcnow() + timedelta(days=1)
    db_session.add(EarningsCalendar(symbol="INFY", event_date=tomorrow.date(), event_type="EARNINGS", source="TEST"))
    db_session.commit()

    checker = RiskChecker(db_session)
    warnings = []
    ok = await checker.check_event_window("INFY", 1, warnings)
    assert ok is False
    assert any(w.code == "EVENT_WINDOW_WARNING" for w in warnings)


@pytest.mark.asyncio
async def test_regime_info_is_informational(db_session):
    # No regime label should not block
    checker = RiskChecker(db_session)
    warnings = []
    ok = await checker.check_regime_compatibility("INFY", 1, warnings)
    assert ok is True


def test_guardrails_check_endpoint_contract():
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
    if res.status_code == 200:
        data = res.json()
        for key in [
            "liquidity_check","position_size_check","exposure_check",
            "event_window_check","regime_check","catalyst_freshness_check",
            "risk_warnings","passed_all","has_critical_failures","timestamp"
        ]:
            assert key in data

