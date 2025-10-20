"""Demo script with mock data to test the system end-to-end."""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from datetime import datetime, timedelta
import random
import pandas as pd
import numpy as np

from backend.app.database import SessionLocal, init_db, MarketDataCache, Setting
from backend.app.services.pipeline import TradeCardPipeline
from backend.app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


def generate_mock_ohlcv(symbol, days=100, base_price=1000):
    """Generate mock OHLCV data for testing."""
    data = []
    price = base_price
    
    for i in range(days):
        # Simulate price movement
        change = random.gauss(0, 2)  # Mean 0, std 2%
        price = price * (1 + change / 100)
        
        # Generate OHLCV
        high = price * (1 + abs(random.gauss(0, 0.5)) / 100)
        low = price * (1 - abs(random.gauss(0, 0.5)) / 100)
        open_price = random.uniform(low, high)
        close = random.uniform(low, high)
        volume = int(random.gauss(1000000, 200000))
        
        timestamp = datetime.now() - timedelta(days=days - i)
        
        data.append({
            "timestamp": timestamp,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": max(100000, volume)
        })
    
    return data


def populate_mock_data(db):
    """Populate database with mock market data."""
    symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
    base_prices = {
        "RELIANCE": 2500,
        "TCS": 3500,
        "HDFCBANK": 1600,
        "INFY": 1400,
        "ICICIBANK": 950
    }
    
    logger.info("Generating mock market data...")
    
    for symbol in symbols:
        # Check if data already exists
        existing = db.query(MarketDataCache).filter(
            MarketDataCache.symbol == symbol
        ).first()
        
        if existing:
            logger.info(f"Data for {symbol} already exists, skipping")
            continue
        
        logger.info(f"Generating data for {symbol}...")
        ohlcv_data = generate_mock_ohlcv(symbol, days=100, base_price=base_prices[symbol])
        
        for candle in ohlcv_data:
            cache_entry = MarketDataCache(
                symbol=symbol,
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
        logger.info(f"✓ Generated {len(ohlcv_data)} candles for {symbol}")


async def run_demo():
    """Run demo end-to-end test."""
    logger.info("=" * 70)
    logger.info("AI TRADING SYSTEM - DEMO MODE")
    logger.info("=" * 70)
    
    # Initialize database
    logger.info("\n1. Initializing database...")
    init_db()
    logger.info("✓ Database initialized")
    
    db = SessionLocal()
    
    try:
        # Populate mock data
        logger.info("\n2. Populating mock market data...")
        populate_mock_data(db)
        logger.info("✓ Mock data populated")
        
        # Set mock capital
        capital_setting = db.query(Setting).filter(
            Setting.key == "total_capital"
        ).first()
        
        if not capital_setting:
            capital_setting = Setting(
                key="total_capital",
                value=100000.0,
                description="Total trading capital"
            )
            db.add(capital_setting)
            db.commit()
        
        logger.info(f"✓ Trading capital set to ₹{capital_setting.value:,.2f}")
        
        # Run signal generation pipeline (without broker)
        logger.info("\n3. Running signal generation pipeline...")
        pipeline = TradeCardPipeline(db, broker=None)
        
        symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
        result = await pipeline.run_pipeline(
            symbols=symbols,
            strategies=None,
            max_trade_cards=5
        )
        
        logger.info("\n" + "=" * 70)
        logger.info("PIPELINE RESULTS:")
        logger.info("=" * 70)
        logger.info(f"  Signals generated:   {result['signals_generated']}")
        logger.info(f"  Signals analyzed:    {result['analyzed_signals']}")
        logger.info(f"  Trade cards created: {result['trade_cards_created']}")
        logger.info(f"  Trade card IDs:      {result['trade_card_ids']}")
        logger.info("=" * 70)
        
        if result['trade_cards_created'] > 0:
            logger.info("\n✓ Demo completed successfully!")
            logger.info("\nNext steps:")
            logger.info("  1. Start the server: uvicorn backend.app.main:app --reload")
            logger.info("  2. Open http://localhost:8000 in your browser")
            logger.info("  3. Review and approve/reject the trade cards")
        else:
            logger.info("\n⚠ No trade cards were created")
            logger.info("  This can happen if no signals meet the criteria")
            logger.info("  Try running the demo again or adjust strategy parameters")
        
    except Exception as e:
        logger.error(f"\n✗ Demo failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        logger.info("\nDemo interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

