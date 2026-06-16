"""Integration test for orchestrator -> v2 pipeline (Step 2c).

Seeds a full account context, stubs guardrails to pass, and injects a fake
orchestrator to assert AUTO -> paper-executed, HIL -> pending, SKIP -> no card.
The LLM/broker never hit the network (paper mode, injected orchestrator).
"""
from datetime import datetime

import pytest

from backend.app.database import (
    SessionLocal, Account, Mandate, FundingPlan, Signal, Feature,
    MarketDataCache, TradeCardV2, OrderV2, PositionV2,
)
from backend.app.services.trade_card_pipeline_v2 import TradeCardPipelineV2

SYMBOL = "PAPERTEST"
USER = "orch_test_user"


class _FakeRiskResult:
    liquidity_check = position_size_check = exposure_check = True
    event_window_check = regime_check = catalyst_freshness_check = True
    has_critical_failures = False
    risk_warnings = []


class _FakeRiskChecker:
    def __init__(self, db):
        pass

    async def run_all_checks(self, **kwargs):
        return _FakeRiskResult()


class _FakeOrchestrator:
    def __init__(self, tier):
        self.tier = tier

    async def decide(self, symbols, account_id=None):
        inst = symbols[0] if symbols else SYMBOL
        return {
            "source": "fake", "fallback": False,
            "market_thesis": "test thesis", "regime_assessment": "ranging",
            "tier_counts": {self.tier: 1},
            "trade_recommendations": [{
                "instrument": inst, "direction": "LONG",
                "conviction": 0.9 if self.tier == "AUTO" else 0.6,
                "size_pct": 5, "stop_loss": 95, "reasoning": "fake reasoning",
                "tier": self.tier,
            }],
        }


@pytest.fixture
def account_ctx():
    db = SessionLocal()
    acct = Account(user_id=USER, name="Orch Test Acct", account_type="LUMP_SUM", status="ACTIVE")
    db.add(acct); db.flush()
    db.add(Mandate(
        account_id=acct.id, version=1, objective="MAX_PROFIT", risk_per_trade_percent=2.0,
        max_positions=10, max_sector_exposure_percent=30.0, horizon_min_days=1,
        horizon_max_days=10, sl_multiplier=1.5, tp_multiplier=3.0, is_active=True,
    ))
    db.add(FundingPlan(
        account_id=acct.id, funding_type="LUMP_SUM", lump_sum_amount=100000.0,
        available_cash=100000.0, total_deployed=0.0,
    ))
    db.add(Signal(
        symbol=SYMBOL, exchange="NSE", direction="LONG", edge=4.0, confidence=0.7,
        quality_score=0.8, horizon_days=5, status="ACTIVE", regime_compatible=True,
    ))
    db.add(Feature(symbol=SYMBOL, timestamp=datetime.utcnow(), atr_14d=5.0, rsi_14=55.0))
    db.add(MarketDataCache(
        symbol=SYMBOL, exchange="NSE", interval="1D", timestamp=datetime.utcnow(),
        open=99, high=101, low=98, close=100.0, volume=1_000_000,
    ))
    db.commit()
    aid = acct.id
    db.close()

    yield aid

    db = SessionLocal()
    db.query(OrderV2).filter(OrderV2.account_id == aid).delete()
    db.query(PositionV2).filter(PositionV2.account_id == aid).delete()
    db.query(TradeCardV2).filter(TradeCardV2.account_id == aid).delete()
    db.query(FundingPlan).filter(FundingPlan.account_id == aid).delete()
    db.query(Mandate).filter(Mandate.account_id == aid).delete()
    db.query(Account).filter(Account.id == aid).delete()
    db.query(Signal).filter(Signal.symbol == SYMBOL).delete()
    db.query(Feature).filter(Feature.symbol == SYMBOL).delete()
    db.query(MarketDataCache).filter(MarketDataCache.symbol == SYMBOL).delete()
    db.commit(); db.close()


def _run(monkeypatch, tier, aid):
    import backend.app.services.trade_card_pipeline_v2 as pipe_mod
    monkeypatch.setattr(pipe_mod, "RiskChecker", _FakeRiskChecker)
    import asyncio
    db = SessionLocal()
    pipeline = TradeCardPipelineV2(db)
    result = asyncio.run(
        pipeline.run_orchestrated([SYMBOL], user_id=USER, orchestrator=_FakeOrchestrator(tier))
    )
    db.close()
    return result


def test_auto_tier_paper_executes(monkeypatch, account_ctx):
    aid = account_ctx
    result = _run(monkeypatch, "AUTO", aid)
    acct_result = list(result["results_by_account"].values())[0]
    assert len(acct_result["cards_created"]) == 1
    assert len(acct_result["cards_executed"]) == 1

    db = SessionLocal()
    try:
        card = db.query(TradeCardV2).filter(TradeCardV2.account_id == aid).first()
        assert card.status == "EXECUTED"
        order = db.query(OrderV2).filter(OrderV2.account_id == aid).first()
        assert order is not None and order.is_paper is True
        assert order.status == "complete"
        pos = db.query(PositionV2).filter(PositionV2.account_id == aid).first()
        assert pos is not None and pos.is_paper is True
    finally:
        db.close()


def test_hil_tier_creates_pending_card_not_executed(monkeypatch, account_ctx):
    aid = account_ctx
    result = _run(monkeypatch, "HIL", aid)
    acct_result = list(result["results_by_account"].values())[0]
    assert len(acct_result["cards_created"]) == 1
    assert len(acct_result["cards_executed"]) == 0

    db = SessionLocal()
    try:
        card = db.query(TradeCardV2).filter(TradeCardV2.account_id == aid).first()
        assert card.status == "PENDING"
        assert db.query(OrderV2).filter(OrderV2.account_id == aid).count() == 0
    finally:
        db.close()


def test_skip_tier_creates_no_card(monkeypatch, account_ctx):
    aid = account_ctx
    result = _run(monkeypatch, "SKIP", aid)
    acct_result = list(result["results_by_account"].values())[0]
    assert acct_result["cards_created"] == []
    assert SYMBOL in acct_result["skipped"]
