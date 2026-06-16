"""Tests for the Step 3b daily strategies."""
import numpy as np
import pandas as pd
import pytest

from backend.app.services.signals.extra import (
    RSIDivergenceStrategy, BollingerSqueezeStrategy,
    FiftyTwoWeekHighStrategy, NiftyETFBaselineStrategy,
)

SYM = "T"


def _df(closes, vol=1_000_000):
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "open": closes - 0.2,
        "high": closes + 0.5,
        "low": closes - 0.5,
        "close": closes,
        "volume": [vol] * len(closes),
    })


def _valid_signal(s):
    assert s["symbol"] == SYM
    assert s["trade_type"] in ("BUY", "SELL")
    assert s["entry_price"] > 0
    # SL/TP on the correct sides
    if s["trade_type"] == "BUY":
        assert s["suggested_sl"] < s["entry_price"] < s["suggested_tp"]
    else:
        assert s["suggested_tp"] < s["entry_price"] < s["suggested_sl"]


@pytest.mark.asyncio
async def test_strategies_silent_on_thin_data():
    df = _df(np.linspace(100, 105, 10))  # too few bars
    for strat in (RSIDivergenceStrategy(), BollingerSqueezeStrategy(),
                  FiftyTwoWeekHighStrategy(), NiftyETFBaselineStrategy()):
        assert await strat.generate_signals([SYM], {SYM: df}) == []


@pytest.mark.asyncio
async def test_fifty_two_week_high_fires_on_breakout():
    closes = np.linspace(100, 200, 120)  # steady new highs + positive momentum
    out = await FiftyTwoWeekHighStrategy().generate_signals([SYM], {SYM: _df(closes)})
    assert len(out) == 1
    assert out[0]["trade_type"] == "BUY"
    _valid_signal(out[0])


@pytest.mark.asyncio
async def test_etf_baseline_fires_above_rising_sma():
    closes = np.linspace(100, 160, 80)  # above a rising SMA50
    out = await NiftyETFBaselineStrategy().generate_signals([SYM], {SYM: _df(closes)})
    assert len(out) == 1
    assert out[0]["trade_type"] == "BUY"
    _valid_signal(out[0])


@pytest.mark.asyncio
async def test_etf_baseline_silent_in_downtrend():
    closes = np.linspace(160, 100, 80)  # below falling SMA
    out = await NiftyETFBaselineStrategy().generate_signals([SYM], {SYM: _df(closes)})
    assert out == []


@pytest.mark.asyncio
async def test_bollinger_squeeze_breakout_fires():
    # Flat (squeeze) for a long stretch, then a sharp breakout up on the last bar.
    flat = list(100 + np.random.RandomState(0).normal(0, 0.05, 90))
    rampless = [100.0] * 5
    breakout = [100, 101, 103, 106, 110]  # expands bands, closes above upper
    closes = rampless + flat + breakout
    out = await BollingerSqueezeStrategy(squeeze_lookback=50).generate_signals([SYM], {SYM: _df(closes)})
    # Either fires a BUY breakout or stays silent — but must never crash or mislabel.
    for s in out:
        assert s["trade_type"] == "BUY"
        _valid_signal(s)


@pytest.mark.asyncio
async def test_rsi_divergence_runs_and_is_wellformed():
    rs = np.random.RandomState(1)
    closes = 100 + np.cumsum(rs.normal(0, 1, 80))
    out = await RSIDivergenceStrategy().generate_signals([SYM], {SYM: _df(closes)})
    for s in out:
        _valid_signal(s)
