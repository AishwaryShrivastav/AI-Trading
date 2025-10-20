"""Fetch real Indian stock market data using yfinance (free API)."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime, timedelta
from backend.app.database import SessionLocal, MarketDataCache

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import yfinance
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Install with: pip install yfinance")


# Indian stock symbols (NSE)
NIFTY_50_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "TITAN.NS",
    "SUNPHARMA.NS", "ULTRACEMCO.NS", "BAJFINANCE.NS", "NESTLEIND.NS", "HCLTECH.NS"
]


def fetch_stock_data(symbol, days=100):
    """Fetch historical data for a symbol using yfinance."""
    if not YFINANCE_AVAILABLE:
        return None
    
    try:
        ticker = yf.Ticker(symbol)
        
        # Fetch historical data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 10)  # Extra days for buffer
        
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return None
        
        # Convert to our format
        data = []
        for idx, row in df.iterrows():
            data.append({
                "timestamp": idx.to_pydatetime(),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row['Volume'])
            })
        
        return data
        
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return None


def populate_market_data(symbols=None, days=100):
    """Populate database with real market data."""
    if not YFINANCE_AVAILABLE:
        logger.error("\n❌ yfinance not installed!")
        logger.info("\nInstall it with:")
        logger.info("  pip install yfinance")
        return
    
    if symbols is None:
        symbols = NIFTY_50_SYMBOLS[:10]  # Use top 10 for faster testing
    
    db = SessionLocal()
    
    try:
        logger.info("=" * 70)
        logger.info("FETCHING REAL MARKET DATA")
        logger.info("=" * 70)
        logger.info(f"\n📡 Fetching data for {len(symbols)} symbols...")
        logger.info(f"   Period: Last {days} days")
        logger.info(f"   Source: Yahoo Finance (NSE)")
        
        total_candles = 0
        successful = 0
        
        for symbol in symbols:
            # Remove .NS suffix for our database
            clean_symbol = symbol.replace(".NS", "")
            
            # Check if we already have data
            existing = db.query(MarketDataCache).filter(
                MarketDataCache.symbol == clean_symbol
            ).count()
            
            if existing > 0:
                logger.info(f"\n  ⏭️  {clean_symbol}: Already have {existing} candles, skipping...")
                successful += 1
                total_candles += existing
                continue
            
            logger.info(f"\n  📥 {clean_symbol}: Fetching...")
            
            # Fetch data
            data = fetch_stock_data(symbol, days)
            
            if not data:
                logger.warning(f"     ❌ Failed to fetch data")
                continue
            
            # Store in database
            for candle in data:
                cache_entry = MarketDataCache(
                    symbol=clean_symbol,
                    exchange="NSE",
                    interval="1D",
                    timestamp=candle["timestamp"],
                    open=candle["open"],
                    high=candle["high"],
                    low=candle["low"],
                    close=candle["close"],
                    volume=candle["volume"]
                )
                db.add(cache_entry)
            
            db.commit()
            
            successful += 1
            total_candles += len(data)
            logger.info(f"     ✅ Stored {len(data)} candles")
        
        logger.info("\n" + "=" * 70)
        logger.info("FETCH COMPLETE")
        logger.info("=" * 70)
        logger.info(f"  Successful: {successful}/{len(symbols)} symbols")
        logger.info(f"  Total candles: {total_candles}")
        logger.info("=" * 70)
        
        if successful > 0:
            logger.info("\n✨ Ready to generate signals!")
            logger.info("\nNext step:")
            logger.info("  python scripts/test_real_signals.py")
        
    except Exception as e:
        logger.error(f"\n❌ Error: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    try:
        populate_market_data()
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

