"""Test REAL signal generation with actual market data (no LLM needed)."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from datetime import datetime, timedelta
import pandas as pd

from backend.app.database import SessionLocal, MarketDataCache, TradeCard
from backend.app.services.signals import MomentumStrategy, MeanReversionStrategy
from backend.app.services.risk_checks import RiskChecker
from backend.app.services.audit import AuditLogger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_real_signal_generation():
    """Test real signal generation without LLM."""
    logger.info("=" * 70)
    logger.info("TESTING REAL SIGNAL GENERATION (No LLM)")
    logger.info("=" * 70)
    
    db = SessionLocal()
    
    try:
        # Check if we have market data
        data_count = db.query(MarketDataCache).count()
        logger.info(f"\n📊 Market data in database: {data_count} candles")
        
        if data_count == 0:
            logger.warning("\n⚠️  No market data available!")
            logger.info("To get real market data, you need to:")
            logger.info("  1. Complete Upstox OAuth authentication")
            logger.info("  2. Run the signal generator which fetches from Upstox")
            logger.info("\nFor now, I'll show you what the strategies would do...")
            return
        
        # Get symbols we have data for
        symbols = db.query(MarketDataCache.symbol).distinct().all()
        symbols = [s[0] for s in symbols]
        logger.info(f"📈 Symbols with data: {symbols}")
        
        # Prepare market data
        market_data = {}
        for symbol in symbols:
            candles = db.query(MarketDataCache).filter(
                MarketDataCache.symbol == symbol,
                MarketDataCache.interval == "1D"
            ).order_by(MarketDataCache.timestamp).all()
            
            if len(candles) >= 50:  # Need at least 50 candles for indicators
                df = pd.DataFrame([{
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume
                } for c in candles])
                market_data[symbol] = df
                logger.info(f"  {symbol}: {len(df)} candles")
        
        if not market_data:
            logger.warning("\n⚠️  Not enough data for analysis (need 50+ candles)")
            return
        
        # Initialize strategies
        logger.info("\n🔍 Running Trading Strategies...")
        momentum = MomentumStrategy()
        mean_rev = MeanReversionStrategy()
        
        # Generate signals
        logger.info("\n1️⃣  Momentum Strategy (MA Crossover)...")
        momentum_signals = await momentum.generate_signals(
            list(market_data.keys()),
            market_data
        )
        logger.info(f"   Found {len(momentum_signals)} momentum signals")
        
        logger.info("\n2️⃣  Mean Reversion Strategy (Bollinger Bands)...")
        mean_rev_signals = await mean_rev.generate_signals(
            list(market_data.keys()),
            market_data
        )
        logger.info(f"   Found {len(mean_rev_signals)} mean reversion signals")
        
        # Combine all signals
        all_signals = momentum_signals + mean_rev_signals
        
        if not all_signals:
            logger.info("\n✓ Strategies ran successfully!")
            logger.info("  No signals found (no setups matching criteria)")
            logger.info("\n💡 This is normal - strategies only trigger when specific")
            logger.info("   technical conditions are met. Try with different stocks")
            logger.info("   or wait for different market conditions.")
            return
        
        # Display signals
        logger.info(f"\n📋 SIGNALS GENERATED: {len(all_signals)}")
        logger.info("=" * 70)
        
        for i, signal in enumerate(all_signals, 1):
            logger.info(f"\n{i}. {signal['symbol']} - {signal['trade_type']}")
            logger.info(f"   Strategy: {signal['strategy']}")
            logger.info(f"   Entry: ₹{signal['entry_price']:.2f}")
            logger.info(f"   Stop Loss: ₹{signal['suggested_sl']:.2f}")
            logger.info(f"   Take Profit: ₹{signal['suggested_tp']:.2f}")
            logger.info(f"   Score: {signal['score']:.2f}")
            logger.info(f"   Reasoning: {signal['reasoning'][:100]}...")
        
        # Run risk checks
        logger.info("\n🛡️  Running Risk Checks...")
        risk_checker = RiskChecker(db)
        
        passed = 0
        failed = 0
        
        for signal in all_signals:
            quantity = 10  # Simple quantity for testing
            checks_ok, warnings = await risk_checker.run_all_checks(
                symbol=signal['symbol'],
                quantity=quantity,
                entry_price=signal['entry_price'],
                stop_loss=signal['suggested_sl'],
                trade_type=signal['trade_type']
            )
            
            if checks_ok:
                passed += 1
                logger.info(f"  ✅ {signal['symbol']} - PASS")
            else:
                failed += 1
                logger.info(f"  ❌ {signal['symbol']} - FAIL: {warnings}")
        
        logger.info(f"\n Risk Checks: {passed} passed, {failed} failed")
        
        # Create trade cards (without LLM analysis)
        logger.info("\n💳 Creating Trade Cards...")
        
        created = 0
        for signal in all_signals:
            quantity = 10
            
            # Run checks
            checks_ok, warnings = await risk_checker.run_all_checks(
                symbol=signal['symbol'],
                quantity=quantity,
                entry_price=signal['entry_price'],
                stop_loss=signal['suggested_sl'],
                trade_type=signal['trade_type']
            )
            
            if checks_ok:
                # Create trade card
                trade_card = TradeCard(
                    symbol=signal['symbol'],
                    entry_price=signal['entry_price'],
                    quantity=quantity,
                    stop_loss=signal['suggested_sl'],
                    take_profit=signal['suggested_tp'],
                    trade_type=signal['trade_type'],
                    strategy=signal['strategy'],
                    confidence=signal['score'],
                    evidence=signal['reasoning'],
                    risks="Auto-generated by strategy. Manual review recommended.",
                    horizon_days=3,
                    status="pending_approval",
                    liquidity_check=True,
                    position_size_check=True,
                    exposure_check=True,
                    event_window_check=True,
                    risk_warnings=warnings,
                    model_version="strategy_only"
                )
                
                db.add(trade_card)
                db.commit()
                db.refresh(trade_card)
                
                created += 1
                logger.info(f"  ✓ Created trade card #{trade_card.id} for {signal['symbol']}")
        
        logger.info(f"\n✅ Created {created} trade cards!")
        
        if created > 0:
            logger.info("\n" + "=" * 70)
            logger.info("SUCCESS! Trade cards are ready in the UI")
            logger.info("=" * 70)
            logger.info("\n📱 Next Steps:")
            logger.info("  1. Refresh the browser at http://localhost:8000")
            logger.info("  2. View the trade cards in 'Pending Approvals' tab")
            logger.info("  3. Click 'Login with Upstox' to connect your broker")
            logger.info("  4. Review and approve trades")
            logger.info("  5. Orders will be placed with Upstox!")
            logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"\n❌ Error: {e}", exc_info=True)
        raise
    finally:
        db.close()


async def main():
    """Main entry point."""
    await test_real_signal_generation()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

