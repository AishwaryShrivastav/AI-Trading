"""Tests for the backtest harness (TradeHarness Step 3a)."""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from backend.app.database import SessionLocal, MarketDataCache, BacktestResult
from backend.app.services.backtest.data_loader import BacktestDataLoader
from backend.app.services.backtest.engine import Backtester
from backend.app.services.signals.base import SignalBase

SYMBOL = "BTSYNTH"
N = 150
LOOKBACK = 60


@pytest.fixture
def seeded_history():
    """150 days of a smooth uptrend in market_data_cache; cleaned up after."""
    db = SessionLocal()
    base = datetime(2024, 1, 1)
    for i in range(N):
        close = 100 + i * 0.5
        db.add(MarketDataCache(
            symbol=SYMBOL, exchange="NSE", interval="1D",
            timestamp=base + timedelta(days=i),
            open=close - 0.2, high=close + 0.5, low=close - 0.5, close=close, volume=1_000_000,
        ))
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(MarketDataCache).filter(MarketDataCache.symbol == SYMBOL).delete()
    db.query(BacktestResult).filter(BacktestResult.symbol == SYMBOL).delete()
    db.commit()
    db.close()


class _SpyStrategy(SignalBase):
    """Never trades; records the length of every DataFrame slice it is given."""
    def __init__(self):
        super().__init__("spy")
        self.seen_lengths = []

    async def generate_signals(self, symbols, market_data, context=None):
        self.seen_lengths.append(len(market_data[symbols[0]]))
        return []


class _DeterministicLong(SignalBase):
    """Always wants to buy with a tight TP that the uptrend will hit."""
    def __init__(self):
        super().__init__("deterministic")

    async def generate_signals(self, symbols, market_data, context=None):
        df = market_data[symbols[0]]
        last = df["close"].iloc[-1]
        return [{
            "symbol": symbols[0], "strategy": self.name, "score": 0.9,
            "entry_price": last, "suggested_sl": last * 0.95, "suggested_tp": last * 1.01,
            "trade_type": "BUY", "reasoning": "test", "metadata": {},
        }]


def _df(seeded_unused=None):
    return BacktestDataLoader(SessionLocal()).load_from_cache(SYMBOL)


@pytest.mark.asyncio
async def test_loader_returns_ohlcv(seeded_history):
    df = _df()
    assert len(df) == N
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].is_monotonic_increasing


@pytest.mark.asyncio
async def test_forward_bias_safe(seeded_history):
    """The strategy must only ever see data up to the current bar."""
    spy = _SpyStrategy()
    df = _df()
    await Backtester().run(spy, df, SYMBOL, min_lookback=LOOKBACK)
    # Flat the whole time -> called once per bar from LOOKBACK..N-1, each with t+1 rows.
    assert spy.seen_lengths == list(range(LOOKBACK + 1, N + 1))


@pytest.mark.asyncio
async def test_deterministic_long_wins_in_uptrend(seeded_history):
    df = _df()
    metrics = await Backtester(slippage_bps=0.0, max_hold_days=20).run(
        _DeterministicLong(), df, SYMBOL, min_lookback=LOOKBACK
    )
    assert metrics.num_trades > 0
    assert metrics.win_rate == 1.0  # tight TP in a pure uptrend always hits
    assert metrics.total_return_pct > 0
    assert metrics.start_date is not None and metrics.end_date is not None
    assert metrics.max_drawdown >= 0.0


@pytest.mark.asyncio
async def test_not_enough_data_returns_empty_metrics(seeded_history):
    short_df = _df().head(30)
    metrics = await Backtester().run(_DeterministicLong(), short_df, SYMBOL, min_lookback=LOOKBACK)
    assert metrics.num_trades == 0


@pytest.mark.asyncio
async def test_runner_persists_results(seeded_history):
    from backend.app.services.backtest.runner import run_backtests
    db = SessionLocal()
    results = await run_backtests(db, [SYMBOL], strategies=[_DeterministicLong()])
    assert len(results) == 1
    stored = db.query(BacktestResult).filter(BacktestResult.symbol == SYMBOL).all()
    assert len(stored) == 1
    assert stored[0].strategy == "deterministic"
    db.close()
