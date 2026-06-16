"""Backtest runner — run strategies over symbols and persist results (Step 3a)."""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...config import get_settings
from ...database import BacktestResult
from ..signals import (
    MomentumStrategy, MeanReversionStrategy, RSIDivergenceStrategy,
    BollingerSqueezeStrategy, FiftyTwoWeekHighStrategy, NiftyETFBaselineStrategy,
)
from .data_loader import BacktestDataLoader
from .engine import Backtester

logger = logging.getLogger(__name__)


def default_strategies():
    """All daily-timeframe strategies backtested by default (Step 3a+3b)."""
    return [
        MomentumStrategy(),
        MeanReversionStrategy(),
        RSIDivergenceStrategy(),
        BollingerSqueezeStrategy(),
        FiftyTwoWeekHighStrategy(),
        NiftyETFBaselineStrategy(),
    ]


async def run_backtests(
    db: Session,
    symbols: List[str],
    strategies: Optional[List[Any]] = None,
    interval: str = "1D",
    persist: bool = True,
) -> List[Dict[str, Any]]:
    """Backtest each strategy on each symbol using cached OHLCV; persist results."""
    settings = get_settings()
    loader = BacktestDataLoader(db)
    bt = Backtester(slippage_bps=getattr(settings, "paper_slippage_bps", 5.0))
    strategies = strategies or default_strategies()

    out: List[Dict[str, Any]] = []
    for symbol in symbols:
        df = loader.load_from_cache(symbol, interval=interval)
        if df.empty:
            logger.warning(f"No cached data for {symbol}; skipping (backfill from Upstox first).")
            continue
        for strat in strategies:
            metrics = await bt.run(strat, df, symbol)
            result = metrics.to_dict()
            out.append(result)
            if persist:
                db.add(BacktestResult(
                    strategy=metrics.strategy, symbol=symbol, interval=interval,
                    start_date=metrics.start_date, end_date=metrics.end_date,
                    num_trades=metrics.num_trades, win_rate=metrics.win_rate,
                    total_return_pct=metrics.total_return_pct, cagr=metrics.cagr,
                    sharpe=metrics.sharpe, max_drawdown=metrics.max_drawdown,
                    avg_hold_days=metrics.avg_hold_days,
                    params={"slippage_bps": bt.slippage_bps, "max_hold_days": bt.max_hold_days},
                    trades=metrics.trades,
                ))
    if persist and out:
        db.commit()
    return out
