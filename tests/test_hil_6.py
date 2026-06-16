"""Tests for Step 6: Notifier, HIL endpoints (status, cards, approve, half, reject, halt, resume)."""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import SessionLocal, TradeCardV2, Setting

client = TestClient(app)


# ================================================================== Notifier
from backend.app.services.notifier import Notifier


@pytest.mark.asyncio
async def test_notifier_subscribe_and_send():
    n = Notifier()
    q = n.subscribe()
    assert n.subscriber_count == 1
    await n.send("test_event", {"hello": "world"})
    payload = q.get_nowait()
    assert payload["type"] == "test_event"
    assert payload["data"]["hello"] == "world"


@pytest.mark.asyncio
async def test_notifier_unsubscribe():
    n = Notifier()
    q = n.subscribe()
    n.unsubscribe(q)
    assert n.subscriber_count == 0
    # send with no subscribers should not raise
    await n.send("test_event", {})


@pytest.mark.asyncio
async def test_notifier_stale_queue_pruned():
    n = Notifier()
    q = n.subscribe()
    # Fill the queue beyond maxsize
    for _ in range(100):
        try:
            q.put_nowait({"x": 1})
        except asyncio.QueueFull:
            break
    # Next send should prune the full queue
    await n.send("overflow", {"y": 2})
    assert n.subscriber_count == 0


# ================================================================== DB fixtures
@pytest.fixture
def pending_card():
    db = SessionLocal()
    card = TradeCardV2(
        account_id=1, symbol="HILTEST", exchange="NSE", direction="LONG",
        entry_price=200.0, quantity=10, position_size_rupees=2000.0,
        stop_loss=190.0, take_profit=220.0, status="PENDING",
        strategy="test", thesis="Test thesis", confidence=0.72,
        edge=5.0, horizon_days=3, risk_amount=100.0,
        reward_amount=200.0, risk_reward_ratio=2.0,
        liquidity_check=True, position_size_check=True, exposure_check=True,
        event_window_check=True, regime_check=True, catalyst_freshness_check=True,
    )
    db.add(card)
    db.commit()
    cid = card.id
    db.close()
    yield cid
    db = SessionLocal()
    db.query(TradeCardV2).filter(TradeCardV2.id == cid).delete()
    db.commit()
    db.close()


@pytest.fixture
def clean_risk_state():
    db = SessionLocal()
    db.query(Setting).filter(Setting.key.in_(["system_state", "equity_peak"])).delete(
        synchronize_session=False
    )
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(Setting).filter(Setting.key.in_(["system_state", "equity_peak"])).delete(
        synchronize_session=False
    )
    db.commit()
    db.close()


# ================================================================== GET /api/hil/status
def test_hil_status_returns_structure(clean_risk_state):
    r = client.get("/api/hil/status")
    assert r.status_code == 200
    body = r.json()
    assert "trading_mode" in body
    assert "risk_state" in body
    assert "pending_approvals" in body
    assert "sse_subscribers" in body


# ================================================================== GET /api/hil/cards
def test_hil_cards_returns_pending(pending_card):
    r = client.get("/api/hil/cards")
    assert r.status_code == 200
    cards = r.json()["cards"]
    ids = [c["id"] for c in cards]
    assert pending_card in ids


def test_hil_cards_structure(pending_card):
    r = client.get("/api/hil/cards")
    card = next(c for c in r.json()["cards"] if c["id"] == pending_card)
    for field in ["id", "symbol", "direction", "quantity", "entry_price", "stop_loss", "take_profit"]:
        assert field in card


# ================================================================== POST approve
def test_hil_approve_executes_card(pending_card, clean_risk_state):
    r = client.post(f"/api/hil/cards/{pending_card}/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "executed"
    assert body["card_id"] == pending_card
    assert body["quantity"] == 10  # full size

    # Card should no longer be PENDING
    db = SessionLocal()
    card = db.query(TradeCardV2).filter(TradeCardV2.id == pending_card).first()
    db.close()
    assert card.status != "PENDING"


def test_hil_approve_404_for_missing_card():
    r = client.post("/api/hil/cards/999999/approve")
    assert r.status_code == 404


def test_hil_approve_400_for_non_pending(pending_card, clean_risk_state):
    # Approve once
    client.post(f"/api/hil/cards/{pending_card}/approve")
    # Try again — should 400
    r = client.post(f"/api/hil/cards/{pending_card}/approve")
    assert r.status_code == 400


# ================================================================== POST half
def test_hil_half_halves_quantity(pending_card, clean_risk_state):
    r = client.post(f"/api/hil/cards/{pending_card}/half")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "executed"
    assert body["half_size"] is True
    assert body["original_quantity"] == 10
    assert body["quantity"] == 5  # ceil(10/2)


# ================================================================== POST reject
def test_hil_reject_marks_card(pending_card):
    r = client.post(f"/api/hil/cards/{pending_card}/reject?reason=test+reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    db = SessionLocal()
    card = db.query(TradeCardV2).filter(TradeCardV2.id == pending_card).first()
    db.close()
    assert card.status == "REJECTED"
    assert "test reject" in (card.rejection_reason or "")


# ================================================================== POST halt / resume
def test_hil_halt_sets_halted_state(clean_risk_state):
    r = client.post("/api/hil/halt")
    assert r.status_code == 200
    assert r.json()["status"] == "halted"

    db = SessionLocal()
    row = db.query(Setting).filter(Setting.key == "system_state").first()
    db.close()
    assert row is not None
    assert row.value["state"] == "HALTED"


def test_hil_resume_after_halt(clean_risk_state):
    client.post("/api/hil/halt")
    r = client.post("/api/hil/resume")
    assert r.status_code == 200
    body = r.json()
    assert body["resumed"] is True
    assert body["state"]["state"] == "ACTIVE"


def test_hil_resume_when_not_halted_returns_false(clean_risk_state):
    r = client.post("/api/hil/resume")
    assert r.status_code == 200
    assert r.json()["resumed"] is False
