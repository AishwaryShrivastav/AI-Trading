"""Tests for PaperBroker (Step 1 — paper trading mode)."""
import pytest

from backend.app.services.broker.paper import PaperBroker


@pytest.mark.asyncio
async def test_buy_fills_at_price_plus_slippage():
    broker = PaperBroker(slippage_bps=10.0)  # 0.10%
    resp = await broker.place_order(
        symbol="RELIANCE", transaction_type="BUY", quantity=5,
        order_type="LIMIT", price=100.0,
    )
    assert resp["status"] == "success"
    data = resp["data"]
    assert data["paper"] is True
    assert data["order_id"].startswith("PAPER-")
    assert data["status"] == "complete"
    assert data["filled_quantity"] == 5
    # BUY fills adverse (higher): 100 * (1 + 0.0010) = 100.10
    assert data["average_price"] == pytest.approx(100.10, abs=1e-6)


@pytest.mark.asyncio
async def test_sell_fills_at_price_minus_slippage():
    broker = PaperBroker(slippage_bps=10.0)
    resp = await broker.place_order(
        symbol="TCS", transaction_type="SELL", quantity=2,
        order_type="LIMIT", price=200.0,
    )
    # SELL fills adverse (lower): 200 * (1 - 0.0010) = 199.80
    assert resp["data"]["average_price"] == pytest.approx(199.80, abs=1e-6)


@pytest.mark.asyncio
async def test_order_status_and_history_tracked():
    broker = PaperBroker()
    resp = await broker.place_order(
        symbol="INFY", transaction_type="BUY", quantity=1, price=50.0,
    )
    oid = resp["data"]["order_id"]
    status = await broker.get_order_status(oid)
    assert status["data"]["order_id"] == oid
    history = await broker.get_order_history()
    assert any(o["order_id"] == oid for o in history)


@pytest.mark.asyncio
async def test_cancel_order():
    broker = PaperBroker()
    resp = await broker.place_order(symbol="INFY", transaction_type="BUY", quantity=1, price=50.0)
    oid = resp["data"]["order_id"]
    cancelled = await broker.cancel_order(oid)
    assert cancelled["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_no_price_and_no_live_broker_raises():
    """Fully offline with no price reference must fail loudly, not fill at 0."""
    broker = PaperBroker(live_broker=None)
    with pytest.raises(ValueError):
        await broker.place_order(symbol="X", transaction_type="BUY", quantity=1, order_type="MARKET")


@pytest.mark.asyncio
async def test_always_authenticated_and_no_network():
    broker = PaperBroker()
    assert broker.is_token_valid() is True
    # get_positions/holdings/funds never hit the network in paper mode
    assert await broker.get_positions() == []
    assert await broker.get_holdings() == []
    assert (await broker.get_funds())["data"]["paper"] is True
