"""Integration test: approving a trade card in paper mode simulates a fill
without ever touching the broker (Step 1)."""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import SessionLocal, TradeCard, Order, Position
from backend.app.config import get_settings

client = TestClient(app)


@pytest.fixture
def paper_trade_card():
    """Create a pending trade card directly in the DB; clean up afterwards."""
    # Ensure paper mode (it is the default, but be explicit for the test).
    settings = get_settings()
    prev_mode = settings.trading_mode
    settings.trading_mode = "paper"

    db = SessionLocal()
    card = TradeCard(
        symbol="RELIANCE",
        exchange="NSE",
        entry_price=100.0,
        quantity=3,
        stop_loss=95.0,
        take_profit=115.0,
        trade_type="BUY",
        strategy="momentum",
        confidence=0.8,
        status="pending_approval",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    card_id = card.id
    db.close()

    yield card_id

    # Cleanup
    db = SessionLocal()
    db.query(Order).filter(Order.trade_card_id == card_id).delete()
    db.query(Position).filter(Position.symbol == "RELIANCE", Position.is_paper == True).delete()  # noqa: E712
    db.query(TradeCard).filter(TradeCard.id == card_id).delete()
    db.commit()
    db.close()
    settings.trading_mode = prev_mode


def test_paper_approval_creates_simulated_fill(paper_trade_card):
    card_id = paper_trade_card

    resp = client.post(f"/api/trade-cards/{card_id}/approve", json={
        "trade_card_id": card_id,
        "user_id": "tester",
    })
    assert resp.status_code == 200, resp.text
    order = resp.json()

    # Order was simulated (PAPER-* id), filled, and flagged is_paper.
    assert order["broker_order_id"].startswith("PAPER-")
    assert order["status"] == "complete"
    assert order["filled_quantity"] == 3

    db = SessionLocal()
    try:
        # Order row flagged paper
        db_order = db.query(Order).filter(Order.trade_card_id == card_id).first()
        assert db_order is not None
        assert db_order.is_paper is True
        # BUY fills at entry +5bps default slippage = 100.05
        assert db_order.average_price == pytest.approx(100.05, abs=1e-6)

        # A paper position was opened
        pos = db.query(Position).filter(
            Position.symbol == "RELIANCE", Position.is_paper == True  # noqa: E712
        ).first()
        assert pos is not None
        assert pos.quantity == 3

        # Trade card moved to executed
        card = db.query(TradeCard).filter(TradeCard.id == card_id).first()
        assert card.status == "executed"
    finally:
        db.close()


def test_health_reports_trading_mode():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "trading_mode" in resp.json()
