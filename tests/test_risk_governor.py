"""Tests for the RiskGovernor drawdown protocol (Step 4a)."""
import pytest

from backend.app.database import SessionLocal, Setting, Account, FundingPlan
from backend.app.services.risk_governor import (
    RiskGovernor, decide_state, ACTIVE, DERISK, HALTED,
)

USER = "rg_test_user"


def _clear_state():
    db = SessionLocal()
    db.query(Setting).filter(Setting.key.in_(["system_state", "equity_peak"])).delete(
        synchronize_session=False
    )
    db.commit()
    db.close()


@pytest.fixture
def clean_state():
    _clear_state()
    yield
    _clear_state()


@pytest.fixture
def funded_account():
    db = SessionLocal()
    acct = Account(user_id=USER, name="RG Acct", account_type="LUMP_SUM", status="ACTIVE")
    db.add(acct); db.flush()
    db.add(FundingPlan(
        account_id=acct.id, funding_type="LUMP_SUM", lump_sum_amount=100000.0,
        available_cash=100000.0, total_deployed=0.0, reserved_cash=0.0,
    ))
    db.commit()
    aid = acct.id
    db.close()
    yield aid
    db = SessionLocal()
    db.query(FundingPlan).filter(FundingPlan.account_id == aid).delete()
    db.query(Account).filter(Account.id == aid).delete()
    db.commit(); db.close()


# --------------------------------------------------------------- pure logic
def test_decide_state_thresholds():
    assert decide_state(ACTIVE, 0, 8, 12) == ACTIVE
    assert decide_state(ACTIVE, 8, 8, 12) == DERISK
    assert decide_state(ACTIVE, 11.9, 8, 12) == DERISK
    assert decide_state(ACTIVE, 12, 8, 12) == HALTED
    assert decide_state(DERISK, 15, 8, 12) == HALTED


def test_halted_is_sticky():
    # Even if drawdown recovers, HALTED only clears via resume().
    assert decide_state(HALTED, 0, 8, 12) == HALTED


# --------------------------------------------------------------- DB-backed
@pytest.mark.asyncio
async def test_derisk_state_and_size_factor(clean_state, funded_account):
    gov = RiskGovernor(SessionLocal())
    gov._set("equity_peak", 110000.0)  # equity will be 100000 -> ~9.09% drawdown
    state = await gov.evaluate(account_id=funded_account)
    assert state["state"] == DERISK
    assert gov.position_size_factor() == pytest.approx(gov.settings.derisk_capital_factor)
    assert gov.blocks_new_entries() is False


@pytest.mark.asyncio
async def test_halt_triggers_protocol_and_resume(clean_state, funded_account):
    gov = RiskGovernor(SessionLocal())
    gov._set("equity_peak", 120000.0)  # ~16.7% drawdown -> HALT
    state = await gov.evaluate(account_id=funded_account)
    assert state["state"] == HALTED
    assert state["resume_required"] is True
    assert state["forced_paper"] is True
    assert "diagnosis" in state and state["diagnosis"]["classification"]
    assert gov.blocks_new_entries() is True
    assert gov.position_size_factor() == 0.0

    # Sticky: re-evaluating after recovery stays HALTED.
    gov._set("equity_peak", 100000.0)
    state2 = await gov.evaluate(account_id=funded_account)
    assert state2["state"] == HALTED

    # RESUME clears it and starts the reduced-sizing window.
    res = gov.resume()
    assert res["resumed"] is True
    assert gov.get_state()["state"] == ACTIVE
    assert gov.blocks_new_entries() is False
    assert gov.position_size_factor() == pytest.approx(gov.settings.post_resume_capital_factor)


@pytest.mark.asyncio
async def test_resume_noop_when_not_halted(clean_state):
    gov = RiskGovernor(SessionLocal())
    res = gov.resume()
    assert res["resumed"] is False


@pytest.mark.asyncio
async def test_pipeline_skips_new_entries_when_halted(clean_state, funded_account):
    from backend.app.services.trade_card_pipeline_v2 import TradeCardPipelineV2

    gov = RiskGovernor(SessionLocal())
    gov._set("system_state", {"state": HALTED, "reason": "test halt", "resume_required": True})

    db = SessionLocal()
    pipeline = TradeCardPipelineV2(db)
    result = await pipeline.run_orchestrated(["NOSUCHSYM"], user_id=USER)
    db.close()

    acct_result = result["results_by_account"][ "RG Acct" ]
    assert acct_result["halted"] is True
    assert acct_result["cards_created"] == []
