"""Historical data loading for backtests (TradeHarness Step 3a).

The engine runs off ``market_data_cache`` so backtests are deterministic and
offline-testable. ``backfill_from_upstox`` populates that cache from the Upstox
historical API (chosen data source) when a valid token is available.
"""
import logging
from datetime import datetime
from typing import List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from ...database import MarketDataCache

logger = logging.getLogger(__name__)


class BacktestDataLoader:
    def __init__(self, db: Session):
        self.db = db

    def load_from_cache(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: str = "1D",
    ) -> pd.DataFrame:
        """Return an OHLCV DataFrame (lowercase columns, time-ascending).

        Columns: timestamp(index), open, high, low, close, volume.
        Empty DataFrame if no data cached.
        """
        rows = (
            self.db.query(MarketDataCache)
            .filter(
                MarketDataCache.symbol == symbol,
                MarketDataCache.exchange == exchange,
                MarketDataCache.interval == interval,
            )
            .order_by(MarketDataCache.timestamp.asc())
            .all()
        )
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(
            [
                {
                    "timestamp": r.timestamp,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                }
                for r in rows
            ]
        )
        df = df.set_index("timestamp")
        return df

    async def backfill_from_upstox(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        broker=None,
        exchange: str = "NSE",
        interval: str = "1D",
    ) -> int:
        """Fetch historical candles from Upstox and upsert into the cache.

        Needs a valid Upstox token on the broker. Returns the number of candles
        written. Safe to re-run (skips timestamps already cached).
        """
        if broker is None:
            from ..broker import UpstoxBroker
            from ...config import get_settings

            s = get_settings()
            broker = UpstoxBroker(s.upstox_api_key, s.upstox_api_secret, s.upstox_redirect_uri)
            # Caller is responsible for setting broker.access_token (see factory).

        candles = await broker.get_ohlcv(
            symbol=symbol, interval=interval, from_date=from_date, to_date=to_date, exchange=exchange
        )

        existing = {
            r.timestamp
            for r in self.db.query(MarketDataCache.timestamp)
            .filter(
                MarketDataCache.symbol == symbol,
                MarketDataCache.exchange == exchange,
                MarketDataCache.interval == interval,
            )
            .all()
        }

        written = 0
        for c in candles or []:
            ts = self._parse_ts(c)
            if ts is None or ts in existing:
                continue
            self.db.add(
                MarketDataCache(
                    symbol=symbol, exchange=exchange, interval=interval, timestamp=ts,
                    open=self._num(c, "open"), high=self._num(c, "high"),
                    low=self._num(c, "low"), close=self._num(c, "close"),
                    volume=int(self._num(c, "volume") or 0),
                )
            )
            written += 1
        if written:
            self.db.commit()
        logger.info(f"Backfilled {written} candles for {symbol} ({interval})")
        return written

    @staticmethod
    def _parse_ts(c) -> Optional[datetime]:
        # Upstox candle is often [ts, o, h, l, c, vol, oi] or a dict.
        raw = None
        if isinstance(c, (list, tuple)) and c:
            raw = c[0]
        elif isinstance(c, dict):
            raw = c.get("timestamp") or c.get("time") or c.get("date")
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw
        try:
            return pd.to_datetime(raw).to_pydatetime().replace(tzinfo=None)
        except Exception:
            return None

    @staticmethod
    def _num(c, key):
        idx = {"open": 1, "high": 2, "low": 3, "close": 4, "volume": 5}
        if isinstance(c, (list, tuple)):
            i = idx.get(key)
            return c[i] if i is not None and i < len(c) else None
        if isinstance(c, dict):
            return c.get(key)
        return None
