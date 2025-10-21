import pytest
from datetime import datetime, timedelta, date
from backend.app.database import SessionLocal, init_db, OptionChain
from backend.app.services.options_engine import OptionsEngine


@pytest.fixture
def db_session():
    init_db()
    session = SessionLocal()
    session.query(OptionChain).delete()
    session.commit()
    yield session
    session.close()


def test_generate_iron_condor_basic(db_session):
    symbol = "RELIANCE"
    expiry = date.today() + timedelta(days=30)
    spot = 2500.0
    # Seed strikes around ATM
    for k, strike in enumerate(range(2400, 2610, 10)):
        db_session.add(OptionChain(
            symbol=symbol, exchange="NSE", expiry=expiry, strike=float(strike),
            ce_ltp=20.0 if strike >= 2500 else 60.0,
            pe_ltp=60.0 if strike <= 2500 else 20.0,
            spot_price=spot, atm_iv=22.0, pcr=1.2,
            ts=datetime.utcnow()
        ))
    db_session.commit()

    engine = OptionsEngine(db_session)
    strat = engine.generate_iron_condor(symbol, expiry, account_id=1, max_risk=50000.0)
    assert strat is not None
    assert strat["strategy_type"] == "IRON_CONDOR"
    assert len(strat["legs"]) == 4

    obj = engine.persist_strategy(strat)
    assert obj.id is not None
    assert obj.strategy_type == "IRON_CONDOR"

