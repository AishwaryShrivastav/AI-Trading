"""Additional daily-timeframe strategies (TradeHarness Step 3b).

All implement the SignalBase contract and return the standard signal dict
(symbol, strategy, score, entry_price, suggested_sl, suggested_tp, trade_type,
reasoning, metadata). Indicators are computed with pandas/numpy so they work
without the optional `ta` package. Strategies degrade to no-signal on thin data.

(ORB — opening-range breakout — is intraday and deferred to the live-WebSocket
step; it is not implemented here.)
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .base import SignalBase

logger = logging.getLogger(__name__)


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = tr.rolling(window=period).mean().iloc[-1]
    if atr is None or np.isnan(atr) or atr <= 0:
        return float(close.iloc[-1]) * 0.02
    return float(atr)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _signal(symbol, name, score, entry, sl, tp, side, reason, meta=None):
    return {
        "symbol": symbol, "strategy": name, "score": round(float(score), 3),
        "entry_price": round(float(entry), 2), "suggested_sl": round(float(sl), 2),
        "suggested_tp": round(float(tp), 2), "trade_type": side,
        "reasoning": reason, "metadata": meta or {},
    }


class RSIDivergenceStrategy(SignalBase):
    """Bullish/bearish RSI divergence over a lookback window (swing)."""

    def __init__(self, rsi_period=14, lookback=20, sl_atr=2.0, tp_atr=3.0):
        super().__init__("rsi_divergence")
        self.rsi_period = rsi_period
        self.lookback = lookback
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr

    async def generate_signals(self, symbols, market_data, context=None):
        out = []
        for symbol in symbols:
            df = market_data.get(symbol)
            if df is None or len(df) < self.lookback + self.rsi_period + 2:
                continue
            try:
                df = df.copy()
                df["rsi"] = _rsi(df["close"], self.rsi_period)
                win = df.iloc[-self.lookback:]
                half = self.lookback // 2
                older, recent = win.iloc[:half], win.iloc[half:]
                close, atr = float(df["close"].iloc[-1]), _atr(df, self.rsi_period)
                rsi_now = float(df["rsi"].iloc[-1])

                # Bullish divergence: price lower-low, RSI higher-low.
                if (recent["close"].min() < older["close"].min()
                        and recent["rsi"].min() > older["rsi"].min() and rsi_now < 45):
                    out.append(_signal(symbol, self.name, 0.65, close,
                                       close - self.sl_atr * atr, close + self.tp_atr * atr,
                                       "BUY", "Bullish RSI divergence", {"rsi": round(rsi_now, 1)}))
                # Bearish divergence: price higher-high, RSI lower-high.
                elif (recent["close"].max() > older["close"].max()
                        and recent["rsi"].max() < older["rsi"].max() and rsi_now > 55):
                    out.append(_signal(symbol, self.name, 0.65, close,
                                       close + self.sl_atr * atr, close - self.tp_atr * atr,
                                       "SELL", "Bearish RSI divergence", {"rsi": round(rsi_now, 1)}))
            except Exception as e:
                logger.debug(f"{self.name} error {symbol}: {e}")
        return out


class BollingerSqueezeStrategy(SignalBase):
    """Low-volatility squeeze followed by a band breakout (swing)."""

    def __init__(self, bb_period=20, bb_std=2.0, squeeze_lookback=50, sl_atr=2.0, tp_atr=3.0):
        super().__init__("bollinger_squeeze")
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.squeeze_lookback = squeeze_lookback
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr

    async def generate_signals(self, symbols, market_data, context=None):
        out = []
        for symbol in symbols:
            df = market_data.get(symbol)
            if df is None or len(df) < self.bb_period + self.squeeze_lookback:
                continue
            try:
                df = df.copy()
                mid = df["close"].rolling(self.bb_period).mean()
                std = df["close"].rolling(self.bb_period).std()
                upper, lower = mid + self.bb_std * std, mid - self.bb_std * std
                bandwidth = (upper - lower) / mid
                bw_now = float(bandwidth.iloc[-1])
                bw_floor = float(bandwidth.iloc[-self.squeeze_lookback:].quantile(0.25))
                was_squeezed = float(bandwidth.iloc[-2]) <= bw_floor
                close, atr = float(df["close"].iloc[-1]), _atr(df)

                if was_squeezed and close > float(upper.iloc[-1]):
                    out.append(_signal(symbol, self.name, 0.7, close,
                                       close - self.sl_atr * atr, close + self.tp_atr * atr,
                                       "BUY", "Squeeze breakout up", {"bandwidth": round(bw_now, 4)}))
                elif was_squeezed and close < float(lower.iloc[-1]):
                    out.append(_signal(symbol, self.name, 0.7, close,
                                       close + self.sl_atr * atr, close - self.tp_atr * atr,
                                       "SELL", "Squeeze breakout down", {"bandwidth": round(bw_now, 4)}))
            except Exception as e:
                logger.debug(f"{self.name} error {symbol}: {e}")
        return out


class FiftyTwoWeekHighStrategy(SignalBase):
    """Long-only breakout near the 52-week high with positive momentum (positional)."""

    def __init__(self, window=252, proximity=0.995, mom_lookback=20, sl_atr=2.5, tp_atr=5.0):
        super().__init__("fifty_two_week_high")
        self.window = window
        self.proximity = proximity
        self.mom_lookback = mom_lookback
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr

    async def generate_signals(self, symbols, market_data, context=None):
        out = []
        for symbol in symbols:
            df = market_data.get(symbol)
            if df is None or len(df) < self.mom_lookback + 30:
                continue
            try:
                w = min(self.window, len(df) - 1)
                hh = float(df["high"].iloc[-w:].max())
                close = float(df["close"].iloc[-1])
                mom_ok = close > float(df["close"].iloc[-self.mom_lookback])
                if close >= hh * self.proximity and mom_ok:
                    atr = _atr(df)
                    out.append(_signal(symbol, self.name, 0.6, close,
                                       close - self.sl_atr * atr, close + self.tp_atr * atr,
                                       "BUY", "52-week-high breakout", {"high_52w": round(hh, 2)}))
            except Exception as e:
                logger.debug(f"{self.name} error {symbol}: {e}")
        return out


class NiftyETFBaselineStrategy(SignalBase):
    """Trend-following baseline anchor: long while above a rising SMA(50)."""

    def __init__(self, sma_period=50, rising_lookback=5, sl_atr=3.0, tp_atr=6.0):
        super().__init__("etf_baseline")
        self.sma_period = sma_period
        self.rising_lookback = rising_lookback
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr

    async def generate_signals(self, symbols, market_data, context=None):
        out = []
        for symbol in symbols:
            df = market_data.get(symbol)
            if df is None or len(df) < self.sma_period + self.rising_lookback + 1:
                continue
            try:
                sma = df["close"].rolling(self.sma_period).mean()
                close = float(df["close"].iloc[-1])
                rising = float(sma.iloc[-1]) > float(sma.iloc[-1 - self.rising_lookback])
                if close > float(sma.iloc[-1]) and rising:
                    atr = _atr(df)
                    out.append(_signal(symbol, self.name, 0.55, close,
                                       close - self.sl_atr * atr, close + self.tp_atr * atr,
                                       "BUY", "Above rising SMA50 (baseline)", {"sma50": round(float(sma.iloc[-1]), 2)}))
            except Exception as e:
                logger.debug(f"{self.name} error {symbol}: {e}")
        return out
