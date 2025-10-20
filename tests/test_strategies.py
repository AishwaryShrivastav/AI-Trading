"""Tests for trading strategies."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backend.app.services.signals import MomentumStrategy, MeanReversionStrategy


@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
    
    # Generate trending price data
    base_price = 1000
    prices = []
    for i in range(100):
        # Uptrend with noise
        price = base_price + (i * 2) + np.random.randn() * 10
        prices.append(price)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.02 for p in prices],
        'low': [p * 0.98 for p in prices],
        'close': [p + np.random.randn() * 5 for p in prices],
        'volume': [1000000 + np.random.randint(-100000, 100000) for _ in range(100)]
    })
    
    return df


@pytest.mark.asyncio
async def test_momentum_strategy_generates_signals(sample_ohlcv_data):
    """Test that momentum strategy can generate signals."""
    strategy = MomentumStrategy()
    
    symbols = ['TEST']
    market_data = {'TEST': sample_ohlcv_data}
    
    signals = await strategy.generate_signals(symbols, market_data)
    
    # Signals may or may not be generated depending on data
    assert isinstance(signals, list)
    
    if signals:
        signal = signals[0]
        assert 'symbol' in signal
        assert 'strategy' in signal
        assert 'score' in signal
        assert 'entry_price' in signal
        assert 'suggested_sl' in signal
        assert 'suggested_tp' in signal
        assert 'trade_type' in signal


@pytest.mark.asyncio
async def test_mean_reversion_strategy_generates_signals(sample_ohlcv_data):
    """Test that mean reversion strategy can generate signals."""
    strategy = MeanReversionStrategy()
    
    symbols = ['TEST']
    market_data = {'TEST': sample_ohlcv_data}
    
    signals = await strategy.generate_signals(symbols, market_data)
    
    assert isinstance(signals, list)
    
    if signals:
        signal = signals[0]
        assert 'symbol' in signal
        assert 'strategy' in signal
        assert signal['strategy'] == 'mean_reversion'


def test_position_size_calculation():
    """Test position size calculation."""
    strategy = MomentumStrategy()
    
    # Entry at 100, SL at 95, risk 1000
    quantity = strategy.calculate_position_size(
        entry_price=100,
        stop_loss=95,
        risk_amount=1000
    )
    
    # Risk per share = 5, so quantity = 1000/5 = 200
    assert quantity == 200


def test_risk_reward_calculation():
    """Test risk/reward ratio calculation."""
    strategy = MomentumStrategy()
    
    # Entry 100, SL 95, TP 110
    # Risk = 5, Reward = 10, R:R = 2:1
    rr = strategy.calculate_risk_reward(
        entry_price=100,
        stop_loss=95,
        take_profit=110
    )
    
    assert rr == 2.0

