"""Market Data Sync - Production-ready Upstox integration for real-time data."""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from .broker import UpstoxBroker
from ..database import MarketDataCache, Setting
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MarketDataSync:
    """
    Syncs market data from Upstox to local cache.
    
    Production features:
    - Real-time LTP from Upstox
    - Historical OHLCV from Upstox
    - Automatic cache updates
    - No dummy/mock data
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.broker: Optional[UpstoxBroker] = None
    
    def _get_broker(self) -> UpstoxBroker:
        """Get authenticated Upstox broker instance."""
        if self.broker is None:
            self.broker = UpstoxBroker(
                api_key=settings.upstox_api_key,
                api_secret=settings.upstox_api_secret,
                redirect_uri=settings.upstox_redirect_uri
            )
            
            # Load authentication tokens
            access_token = self.db.query(Setting).filter(
                Setting.key == "upstox_access_token"
            ).first()
            
            refresh_token = self.db.query(Setting).filter(
                Setting.key == "upstox_refresh_token"
            ).first()
            
            if access_token:
                self.broker.access_token = access_token.value
            if refresh_token:
                self.broker.refresh_token = refresh_token.value
        
        return self.broker
    
    async def sync_current_prices(
        self,
        symbols: List[str],
        exchange: str = "NSE"
    ) -> Dict[str, float]:
        """
        Get current prices for symbols from Upstox.
        
        Args:
            symbols: List of symbols
            exchange: Exchange (NSE, BSE)
            
        Returns:
            Dict mapping symbol to LTP
        """
        broker = self._get_broker()
        prices = {}
        
        for symbol in symbols:
            try:
                ltp = await broker.get_ltp(symbol, exchange)
                prices[symbol] = ltp
                logger.info(f"Fetched LTP for {symbol}: ₹{ltp:.2f}")
            except Exception as e:
                logger.error(f"Failed to fetch LTP for {symbol}: {e}")
        
        return prices
    
    async def sync_historical_data(
        self,
        symbol: str,
        days: int = 60,
        exchange: str = "NSE"
    ) -> int:
        """
        Sync historical OHLCV data from Upstox to cache.
        
        Args:
            symbol: Trading symbol
            days: Number of days to fetch
            exchange: Exchange
            
        Returns:
            Number of candles synced
        """
        broker = self._get_broker()
        
        try:
            # Calculate date range
            to_date = datetime.utcnow()
            from_date = to_date - timedelta(days=days)
            
            # Fetch from Upstox
            candles = await broker.get_ohlcv(
                symbol=symbol,
                interval="1day",
                from_date=from_date,
                to_date=to_date,
                exchange=exchange
            )
            
            if not candles:
                logger.warning(f"No historical data received for {symbol}")
                return 0
            
            # Store in cache
            synced_count = 0
            
            for candle in candles:
                # Parse timestamp
                timestamp = candle.get("timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                elif isinstance(timestamp, int):
                    timestamp = datetime.fromtimestamp(timestamp / 1000)  # Milliseconds to seconds
                
                # Check if already exists
                existing = self.db.query(MarketDataCache).filter(
                    MarketDataCache.symbol == symbol,
                    MarketDataCache.exchange == exchange,
                    MarketDataCache.timestamp == timestamp,
                    MarketDataCache.interval == "1D"
                ).first()
                
                if existing:
                    # Update existing
                    existing.open = candle.get("open")
                    existing.high = candle.get("high")
                    existing.low = candle.get("low")
                    existing.close = candle.get("close")
                    existing.volume = candle.get("volume")
                    existing.fetched_at = datetime.utcnow()
                else:
                    # Create new
                    cache_entry = MarketDataCache(
                        symbol=symbol,
                        exchange=exchange,
                        interval="1D",
                        timestamp=timestamp,
                        open=candle.get("open"),
                        high=candle.get("high"),
                        low=candle.get("low"),
                        close=candle.get("close"),
                        volume=candle.get("volume"),
                        fetched_at=datetime.utcnow()
                    )
                    self.db.add(cache_entry)
                
                synced_count += 1
            
            self.db.commit()
            logger.info(f"Synced {synced_count} candles for {symbol} from Upstox")
            
            return synced_count
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to sync historical data for {symbol}: {e}")
            return 0
    
    async def sync_batch(
        self,
        symbols: List[str],
        exchange: str = "NSE"
    ) -> Dict[str, int]:
        """
        Sync historical data for multiple symbols.
        
        Returns:
            Dict mapping symbol to number of candles synced
        """
        results = {}
        
        for symbol in symbols:
            count = await self.sync_historical_data(symbol, exchange=exchange)
            results[symbol] = count
        
        logger.info(f"Batch sync complete: {len(results)} symbols")
        return results
    
    async def get_latest_price(
        self,
        symbol: str,
        exchange: str = "NSE",
        use_cache: bool = True
    ) -> Optional[float]:
        """
        Get latest price for symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange
            use_cache: If True, check cache first, else fetch from Upstox
            
        Returns:
            Latest price or None
        """
        if use_cache:
            # Try cache first
            latest = self.db.query(MarketDataCache).filter(
                MarketDataCache.symbol == symbol,
                MarketDataCache.exchange == exchange
            ).order_by(MarketDataCache.timestamp.desc()).first()
            
            if latest:
                # Check if cache is fresh (< 5 minutes for trading hours)
                age = datetime.utcnow() - latest.fetched_at
                if age < timedelta(minutes=5):
                    return latest.close
        
        # Fetch from Upstox
        try:
            broker = self._get_broker()
            ltp = await broker.get_ltp(symbol, exchange)
            
            # Update cache
            latest = self.db.query(MarketDataCache).filter(
                MarketDataCache.symbol == symbol,
                MarketDataCache.exchange == exchange
            ).order_by(MarketDataCache.timestamp.desc()).first()
            
            if latest:
                latest.close = ltp
                latest.fetched_at = datetime.utcnow()
                self.db.commit()
            
            return ltp
            
        except Exception as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            return None
    
    async def close(self):
        """Close broker connection."""
        if self.broker:
            await self.broker.close()

