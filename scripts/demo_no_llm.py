"""Demo script WITHOUT LLM calls - for testing when OpenAI quota is exceeded."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from datetime import datetime, timedelta
import random
import pandas as pd
import numpy as np

from backend.app.database import SessionLocal, init_db, MarketDataCache, Setting, TradeCard
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
        change = random.gauss(0, 2)
        price = price * (1 + change / 100)
        
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


def create_sample_trade_cards(db):
    """Create sample trade cards manually without LLM."""
    logger.info("\nCreating sample trade cards...")
    
    sample_trades = [
        {
            "symbol": "RELIANCE",
            "entry_price": 2550.0,
            "quantity": 20,
            "stop_loss": 2490.0,
            "take_profit": 2650.0,
            "trade_type": "BUY",
            "strategy": "momentum",
            "confidence": 0.75,
            "evidence": "Strong momentum signal with MA crossover. Volume above average. RSI in neutral zone indicating room for upside.",
            "risks": "Market volatility could impact execution. Watch for sector rotation.",
            "horizon_days": 3
        },
        {
            "symbol": "TCS",
            "entry_price": 3520.0,
            "quantity": 15,
            "stop_loss": 3450.0,
            "take_profit": 3640.0,
            "trade_type": "BUY",
            "strategy": "momentum",
            "confidence": 0.68,
            "evidence": "IT sector showing strength. Price consolidating near highs with increasing volume.",
            "risks": "Earnings announcement next week. Dollar movements could affect sentiment.",
            "horizon_days": 5
        },
        {
            "symbol": "HDFCBANK",
            "entry_price": 1605.0,
            "quantity": 30,
            "stop_loss": 1575.0,
            "take_profit": 1660.0,
            "trade_type": "BUY",
            "strategy": "mean_reversion",
            "confidence": 0.72,
            "evidence": "Oversold bounce from lower Bollinger Band. Banking sector oversold on recent dip.",
            "risks": "Interest rate policy announcements pending. Sector volatility.",
            "horizon_days": 4
        }
    ]
    
    created_ids = []
    
    for trade_data in sample_trades:
        # Check if already exists
        existing = db.query(TradeCard).filter(
            TradeCard.symbol == trade_data["symbol"],
            TradeCard.status == "pending_approval"
        ).first()
        
        if existing:
            logger.info(f"Trade card for {trade_data['symbol']} already exists")
            created_ids.append(existing.id)
            continue
        
        trade_card = TradeCard(
            **trade_data,
            status="pending_approval",
            liquidity_check=True,
            position_size_check=True,
            exposure_check=True,
            event_window_check=True,
            risk_warnings=[],
            model_version="demo-v1"
        )
        
        db.add(trade_card)
        db.commit()
        db.refresh(trade_card)
        
        created_ids.append(trade_card.id)
        logger.info(f"✓ Created trade card {trade_card.id} for {trade_data['symbol']}")
    
    return created_ids


async def run_demo():
    """Run demo without LLM calls."""
    logger.info("=" * 70)
    logger.info("AI TRADING SYSTEM - DEMO MODE (No LLM)")
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
        
        # Create sample trade cards
        logger.info("\n3. Creating sample trade cards...")
        trade_card_ids = create_sample_trade_cards(db)
        
        logger.info("\n" + "=" * 70)
        logger.info("DEMO RESULTS:")
        logger.info("=" * 70)
        logger.info(f"  Trade cards created: {len(trade_card_ids)}")
        logger.info(f"  Trade card IDs:      {trade_card_ids}")
        logger.info("=" * 70)
        
        logger.info("\n✓ Demo completed successfully!")
        logger.info("\n📋 Sample Trade Cards Created:")
        
        for trade_id in trade_card_ids:
            trade = db.query(TradeCard).filter(TradeCard.id == trade_id).first()
            if trade:
                logger.info(f"\n  {trade.symbol}:")
                logger.info(f"    Entry: ₹{trade.entry_price}")
                logger.info(f"    Quantity: {trade.quantity}")
                logger.info(f"    SL: ₹{trade.stop_loss} | TP: ₹{trade.take_profit}")
                logger.info(f"    Confidence: {trade.confidence*100:.0f}%")
                logger.info(f"    Strategy: {trade.strategy}")
        
        logger.info("\n" + "=" * 70)
        logger.info("NEXT STEPS:")
        logger.info("=" * 70)
        logger.info("  1. Start the server:")
        logger.info("     uvicorn backend.app.main:app --reload")
        logger.info("\n  2. Open http://localhost:8000 in your browser")
        logger.info("\n  3. Review and approve/reject the trade cards")
        logger.info("\n  4. Click 'Login with Upstox' to connect your broker")
        logger.info("\n  5. After authentication, you can place real orders!")
        logger.info("=" * 70 + "\n")
        
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

