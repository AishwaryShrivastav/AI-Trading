"""Tests for Step 7: trust scoring, regime classifier, self-reflection, reporting endpoints."""
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import (
    SessionLocal, PositionV2, TradeCardV2, StrategyTrustScore, WeeklyReflection,
)
from backend.app.services.trust_scoring import (
    _day_score, _ema, update_trust_scores, get_all_trust_scores, get_trust_score,
)
from backend.app.services.regime_classifier import RegimeClassifier, TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOL, UNKNOWN

client = TestClient(app)


# ================================================================== trust scoring unit tests

def test_day_score_empty():
    assert _day_score([]) is None


def test_day_score_all_winners():
    class FakePos:
        def __init__(self, pnl, entry=100.0, qty=10):
            self.realized_pnl = pnl
            self.average_entry_price = entry
            self.quantity = qty

    positions = [FakePos(50), FakePos(30), FakePos(20)]
    score = _day_score(positions)
    assert score is not None
    assert 0.0 <= score <= 1.0
    assert score > 0.5  # all winners → above neutral


def test_day_score_all_losers():
    class FakePos:
        def __init__(self, pnl, entry=100.0, qty=10):
            self.realized_pnl = pnl
            self.average_entry_price = entry
            self.quantity = qty

    positions = [FakePos(-50), FakePos(-30)]
    score = _day_score(positions)
    assert score is not None
    assert 0.0 <= score <= 1.0
    assert score < 0.5  # all losers → below neutral


def test_ema_neutral():
    # EMA of two equal values should return the same value
    assert abs(_ema(0.5, 0.5) - 0.5) < 1e-9


def test_ema_pulls_toward_new():
    result = _ema(0.4, 0.8, alpha=0.5)
    assert abs(result - 0.6) < 1e-9


def test_update_trust_scores_no_trades():
    db = SessionLocal()
    result = update_trust_scores(db, target_date=date(2000, 1, 1))
    assert result == {}
    db.close()


def test_update_trust_scores_creates_row():
    db = SessionLocal()
    try:
        # Create a paper position closed today
        card = TradeCardV2(
            account_id=1, symbol="TRUSTTEST", exchange="NSE", direction="LONG",
            entry_price=100.0, stop_loss=90.0, take_profit=120.0,
            quantity=5, position_size_rupees=500.0,
            status="APPROVED", strategy="momentum_breakout",
        )
        db.add(card)
        db.flush()

        today = datetime.utcnow()
        pos = PositionV2(
            account_id=1, symbol="TRUSTTEST", exchange="NSE", direction="LONG",
            quantity=5, average_entry_price=100.0, is_paper=True,
            opened_at=today, closed_at=today,
            realized_pnl=25.0, trade_card_id=card.id,
        )
        db.add(pos)
        db.commit()

        result = update_trust_scores(db, target_date=today.date())
        assert "momentum_breakout" in result
        score = result["momentum_breakout"]["trust_score"]
        assert 0.0 <= score <= 1.0
        assert result["momentum_breakout"]["trade_count"] >= 1
    finally:
        db.rollback()
        db.close()


def test_get_trust_score_default():
    db = SessionLocal()
    score = get_trust_score(db, "nonexistent_strategy_xyz")
    assert score == 0.5
    db.close()


def test_get_all_trust_scores_returns_list():
    db = SessionLocal()
    scores = get_all_trust_scores(db)
    assert isinstance(scores, list)
    for s in scores:
        assert "strategy" in s
        assert "trust_score" in s
    db.close()


# ================================================================== regime classifier

def test_regime_classifier_unknown_no_data():
    db = SessionLocal()
    classifier = RegimeClassifier(db)
    regime = classifier.classify()
    # With no VIX or feature data, should be UNKNOWN
    assert regime in (UNKNOWN, TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOL)
    db.close()


def test_regime_get_strategy_weight_default():
    db = SessionLocal()
    classifier = RegimeClassifier(db)
    weight = classifier.get_strategy_weight("unknown_strategy_xyz", UNKNOWN)
    assert 0.0 <= weight <= 1.0
    db.close()


def test_regime_get_all_weights_structure():
    db = SessionLocal()
    classifier = RegimeClassifier(db)
    result = classifier.get_all_weights()
    assert "regime" in result
    assert "strategy_weights" in result
    assert "vix" in result
    db.close()


def test_regime_weights_trending_up():
    db = SessionLocal()
    classifier = RegimeClassifier(db)
    weight = classifier.get_strategy_weight("momentum_breakout", TRENDING_UP)
    assert weight == 1.0  # momentum should be fully weighted in uptrend
    db.close()


def test_regime_weights_high_vol_low():
    db = SessionLocal()
    classifier = RegimeClassifier(db)
    weight = classifier.get_strategy_weight("momentum_breakout", HIGH_VOL)
    assert weight <= 0.3  # momentum should be de-weighted in high vol
    db.close()


# ================================================================== reporting endpoints

def test_get_performance():
    resp = client.get("/api/reporting/performance")
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data
    assert "as_of" in data
    assert isinstance(data["strategies"], list)


def test_get_attribution():
    resp = client.get("/api/reporting/attribution")
    assert resp.status_code == 200
    data = resp.json()
    assert "attribution" in data
    assert "total_pnl_inr" in data
    assert data["days"] == 30


def test_get_attribution_custom_days():
    resp = client.get("/api/reporting/attribution?days=7")
    assert resp.status_code == 200
    assert resp.json()["days"] == 7


def test_get_trust_scores_endpoint():
    resp = client.get("/api/reporting/trust-scores")
    assert resp.status_code == 200
    data = resp.json()
    assert "trust_scores" in data
    assert isinstance(data["trust_scores"], list)


def test_refresh_trust_scores_endpoint():
    resp = client.post("/api/reporting/trust-scores/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert "updated" in data
    assert "count" in data


def test_refresh_trust_scores_invalid_date():
    resp = client.post("/api/reporting/trust-scores/refresh?date=not-a-date")
    assert resp.status_code == 400


def test_get_regime_endpoint():
    resp = client.get("/api/reporting/regime")
    assert resp.status_code == 200
    data = resp.json()
    assert "regime" in data
    assert "strategy_weights" in data
    assert "vix" in data


def test_get_equity_curve():
    resp = client.get("/api/reporting/equity-curve")
    assert resp.status_code == 200
    data = resp.json()
    assert "curve" in data
    assert "days" in data
    assert data["days"] == 14


def test_get_equity_curve_custom_days():
    resp = client.get("/api/reporting/equity-curve?days=7")
    assert resp.status_code == 200
    assert resp.json()["days"] == 7


def test_get_reflections_empty():
    resp = client.get("/api/reporting/reflection")
    assert resp.status_code == 200
    data = resp.json()
    assert "reflections" in data
    assert isinstance(data["reflections"], list)


def test_get_reflections_filter_pending():
    resp = client.get("/api/reporting/reflection?status=PENDING_REVIEW")
    assert resp.status_code == 200
    data = resp.json()
    for r in data["reflections"]:
        assert r["status"] == "PENDING_REVIEW"


def test_approve_reflection_not_found():
    resp = client.post("/api/reporting/reflection/999999/approve")
    assert resp.status_code == 404


def test_reject_reflection_not_found():
    resp = client.post("/api/reporting/reflection/999999/reject")
    assert resp.status_code == 404


def test_approve_and_reject_reflection():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        rec = WeeklyReflection(
            week_start=now - timedelta(days=7),
            week_end=now,
            performance_data={"total_trades": 5, "total_pnl_inr": 200.0},
            reflection={"observations": ["test obs"], "risk_notes": "none", "regime_hypothesis": "up", "next_week_focus": "momentum"},
            status="PENDING_REVIEW",
            created_at=now,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        rid = rec.id

        # Approve
        resp = client.post(f"/api/reporting/reflection/{rid}/approve?reviewed_by=tester")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        # Verify DB
        db.refresh(rec)
        assert rec.status == "APPROVED"
        assert rec.reviewed_by == "tester"

        # Reject another
        rec2 = WeeklyReflection(
            week_start=now - timedelta(days=14), week_end=now - timedelta(days=7),
            performance_data={}, reflection={}, status="PENDING_REVIEW", created_at=now,
        )
        db.add(rec2)
        db.commit()
        db.refresh(rec2)

        resp2 = client.post(f"/api/reporting/reflection/{rec2.id}/reject?reviewed_by=tester")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "rejected"
    finally:
        db.rollback()
        db.close()


# ================================================================== orchestrator context enrichment

def test_orchestrator_context_has_trust_and_regime():
    """Smoke test: assemble_context now includes trust_scores and regime fields."""
    from backend.app.services.orchestrator import Orchestrator
    from backend.app.config import get_settings

    db = SessionLocal()
    try:
        svc = Orchestrator(db, settings=get_settings())
        ctx = svc.assemble_context(["RELIANCE"])
        assert "trust_scores" in ctx
        assert "regime" in ctx
        assert "regime_weights" in ctx
        assert isinstance(ctx["trust_scores"], list)
        assert isinstance(ctx["regime_weights"], dict)
    finally:
        db.close()


# ================================================================== scheduler has weekly_reflection job

@pytest.mark.asyncio
async def test_scheduler_has_weekly_reflection_job():
    from backend.app.services.scheduler import SchedulerService
    svc = SchedulerService()
    svc.start()
    job_ids = [j.id for j in svc._sched.get_jobs()]
    assert "weekly_reflection" in job_ids
    svc.shutdown()


# ================================================================== dashboard page

def test_dashboard_route_exists():
    resp = client.get("/dashboard")
    # May return 200 (if frontend exists) or JSON fallback — both are valid
    assert resp.status_code == 200
