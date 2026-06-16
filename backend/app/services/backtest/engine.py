"""Backtest engine (TradeHarness Step 3a).

Forward-bias-safe: at bar ``t`` a strategy is only ever shown ``df.iloc[:t+1]``
(data up to and including t), then a trade is entered at the close of bar t with
slippage and managed on subsequent bars. One position at a time (no pyramiding).

Produces a per-strategy/symbol metric set: CAGR, Sharpe, max drawdown, win-rate,
average hold, number of trades, total return — computed from a daily
mark-to-market equity curve.
"""
import logging
import math
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_TRADING_DAYS = 252


@dataclass
class Trade:
    entry_date: Any
    exit_date: Any
    direction: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    bars_held: int
    exit_reason: str


@dataclass
class BacktestMetrics:
    strategy: str
    symbol: str
    num_trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    cagr: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    avg_hold_days: float = 0.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    trades: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Backtester:
    def __init__(self, slippage_bps: float = 5.0, max_hold_days: int = 20, starting_capital: float = 100_000.0):
        self.slippage_bps = slippage_bps
        self.max_hold_days = max_hold_days
        self.starting_capital = starting_capital

    def _slip(self, price: float, side: str) -> float:
        f = self.slippage_bps / 10_000.0
        return price * (1 + f) if side == "buy" else price * (1 - f)

    async def run(self, strategy, df: pd.DataFrame, symbol: str, min_lookback: int = 60) -> BacktestMetrics:
        """Backtest a single strategy on one symbol's daily OHLCV."""
        name = getattr(strategy, "name", strategy.__class__.__name__)
        metrics = BacktestMetrics(strategy=name, symbol=symbol)
        if df is None or len(df) <= min_lookback:
            logger.warning(f"Not enough data to backtest {name}/{symbol} ({0 if df is None else len(df)} bars)")
            return metrics

        n = len(df)
        closes = df["close"].tolist()
        highs = df["high"].tolist()
        lows = df["low"].tolist()
        index = list(df.index)

        # Daily equity curve (mark-to-market), starts flat at starting_capital.
        equity = [self.starting_capital] * n
        cash = self.starting_capital

        trades: List[Trade] = []
        position = None  # dict: side, entry_price, sl, tp, entry_i, qty

        t = min_lookback
        while t < n:
            bar_high, bar_low, bar_close = highs[t], lows[t], closes[t]

            if position is not None:
                exit_price = None
                reason = None
                if position["side"] == "long":
                    if bar_low <= position["sl"]:
                        exit_price, reason = position["sl"], "stop_loss"
                    elif bar_high >= position["tp"]:
                        exit_price, reason = position["tp"], "take_profit"
                else:  # short
                    if bar_high >= position["sl"]:
                        exit_price, reason = position["sl"], "stop_loss"
                    elif bar_low <= position["tp"]:
                        exit_price, reason = position["tp"], "take_profit"
                if exit_price is None and (t - position["entry_i"]) >= self.max_hold_days:
                    exit_price, reason = bar_close, "time_exit"

                if exit_price is not None:
                    fill = self._slip(exit_price, "sell" if position["side"] == "long" else "buy")
                    if position["side"] == "long":
                        pnl_pct = (fill - position["entry_price"]) / position["entry_price"]
                    else:
                        pnl_pct = (position["entry_price"] - fill) / position["entry_price"]
                    cash = cash * (1 + pnl_pct)
                    trades.append(Trade(
                        entry_date=str(index[position["entry_i"]]), exit_date=str(index[t]),
                        direction=position["side"], entry_price=round(position["entry_price"], 2),
                        exit_price=round(fill, 2), pnl_pct=round(pnl_pct * 100, 3),
                        bars_held=t - position["entry_i"], exit_reason=reason,
                    ))
                    position = None

            # Mark-to-market equity for this bar
            if position is None:
                equity[t] = cash
            else:
                if position["side"] == "long":
                    unreal = (bar_close - position["entry_price"]) / position["entry_price"]
                else:
                    unreal = (position["entry_price"] - bar_close) / position["entry_price"]
                equity[t] = cash * (1 + unreal)

            # Look for a new entry only when flat (decision uses data <= t).
            if position is None:
                try:
                    signals = await strategy.generate_signals([symbol], {symbol: df.iloc[: t + 1].copy()})
                except Exception as e:
                    logger.debug(f"{name} signal error at bar {t}: {e}")
                    signals = []
                sig = signals[0] if signals else None
                if sig and sig.get("entry_price"):
                    side = "long" if str(sig.get("trade_type", "BUY")).upper() == "BUY" else "short"
                    entry_fill = self._slip(bar_close, "buy" if side == "long" else "sell")
                    sl = sig.get("suggested_sl")
                    tp = sig.get("suggested_tp")
                    if sl and tp:
                        position = {"side": side, "entry_price": entry_fill, "sl": sl, "tp": tp, "entry_i": t}
            t += 1

        return self._finalize(metrics, trades, equity, index)

    def _finalize(self, metrics: BacktestMetrics, trades: List[Trade], equity: List[float], index) -> BacktestMetrics:
        metrics.num_trades = len(trades)
        metrics.trades = [asdict(tr) for tr in trades]
        if index:
            metrics.start_date = str(index[0])
            metrics.end_date = str(index[-1])

        if trades:
            metrics.wins = sum(1 for tr in trades if tr.pnl_pct > 0)
            metrics.win_rate = round(metrics.wins / len(trades), 4)
            metrics.avg_hold_days = round(sum(tr.bars_held for tr in trades) / len(trades), 2)

        eq = pd.Series(equity).ffill()
        total_return = (eq.iloc[-1] / eq.iloc[0]) - 1 if len(eq) and eq.iloc[0] else 0.0
        metrics.total_return_pct = round(total_return * 100, 3)

        # CAGR from elapsed calendar days
        try:
            days = (pd.to_datetime(index[-1]) - pd.to_datetime(index[0])).days or 1
            years = days / 365.25
            metrics.cagr = round(((1 + total_return) ** (1 / years) - 1) * 100, 3) if years > 0 else 0.0
        except Exception:
            metrics.cagr = 0.0

        daily_ret = eq.pct_change().dropna()
        if len(daily_ret) > 1 and daily_ret.std() > 0:
            metrics.sharpe = round((daily_ret.mean() / daily_ret.std()) * math.sqrt(_TRADING_DAYS), 3)

        running_max = eq.cummax()
        drawdown = (eq - running_max) / running_max
        metrics.max_drawdown = round(abs(drawdown.min()) * 100, 3) if len(drawdown) else 0.0

        return metrics
