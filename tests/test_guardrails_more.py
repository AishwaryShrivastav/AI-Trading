import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import (
    SessionLocal, init_db,
    Setting, Mandate, FundingPlan,
    Event, PositionV2, MarketDataCache
)
from backend.app.services.risk_checks import RiskChecker


@pytest.fixture
def db_session():
    init_db()
    session = SessionLocal()
    # Reset key tables
    session.query(PositionV2).delete()
    session.query(Event).delete()
    session.query(MarketDataCache).delete()
    session.query(Mandate).delete()
    session.query(FundingPlan).delete()
    session.query(Setting).filter(Setting.key == "total_capital").delete()
    session.commit()

    # Baseline config
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
async def test_catalyst_freshness_stale_blocks(db_session):
    # Create an event older than 30 hours
    stale_ts = datetime.utcnow() - timedelta(hours=30)
    ev = Event(
        source="NEWS",
        event_type="EARNINGS",
        symbols=["INFY"],
        event_timestamp=stale_ts,
        ingested_at=stale_ts
    )
    db_session.add(ev)
    db_session.commit()

    checker = RiskChecker(db_session)
    warnings = []
    ok = await checker.check_catalyst_freshness(ev.id, warnings)
    assert ok is False
    assert any(w.code == "CATALYST_STALE" for w in warnings)


def test_guardrails_explain_not_found():
    client = TestClient(app)
    res = client.get("/api/guardrails/explain?card_id=999999")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_run_all_checks_happy_path(db_session):
    # Seed volumes for liquidity
    now = datetime.utcnow()
    for i in range(20):
        db_session.add(MarketDataCache(
            symbol="INFY", exchange="NSE", interval="1D",
            timestamp=now - timedelta(days=i), open=1, high=1, low=1, close=1, volume=100000
        ))
    db_session.commit()

    checker = RiskChecker(db_session)
    result = await checker.run_all_checks(
        symbol="INFY",
        quantity=100,  # Risk = (1000-980)*100 = 2000 => 2% of 100k (limit)
        entry_price=1000.0,
        stop_loss=980.0,
        trade_type="LONG",
        exchange="NSE",
        account_id=1,
        sector="IT",
        event_id=None
    )

    assert isinstance(result.passed_all, bool)
    assert result.liquidity_check is True
    assert result.position_size_check is True

