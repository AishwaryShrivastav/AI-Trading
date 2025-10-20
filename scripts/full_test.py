"""Complete end-to-end test with REAL market data and REAL AI analysis."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from datetime import datetime
import pandas as pd

from backend.app.database import SessionLocal, MarketDataCache, TradeCard
from backend.app.services.signals import MomentumStrategy, MeanReversionStrategy
from backend.app.services.llm.openai_provider import OpenAIProvider
from backend.app.services.risk_checks import RiskChecker
from backend.app.services.audit import AuditLogger
from backend.app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


async def full_test():
    """Complete end-to-end test with real data and AI."""
    logger.info("=" * 70)
    logger.info("COMPLETE END-TO-END TEST - REAL DATA + REAL AI")
    logger.info("=" * 70)
    
    db = SessionLocal()
    
    try:
        # Step 1: Check market data
        logger.info("\n📊 Step 1: Checking Market Data...")
        symbols_query = db.query(MarketDataCache.symbol).distinct().all()
        symbols = [s[0] for s in symbols_query]
        
        if not symbols:
            logger.error("❌ No market data found!")
            logger.info("Run: python scripts/fetch_market_data.py")
            return
        
        logger.info(f"✅ Found data for {len(symbols)} symbols: {', '.join(symbols)}")
        
        # Step 2: Prepare market data
        logger.info("\n📈 Step 2: Loading Market Data...")
        market_data = {}
        
        for symbol in symbols:
            candles = db.query(MarketDataCache).filter(
                MarketDataCache.symbol == symbol,
                MarketDataCache.interval == "1D"
            ).order_by(MarketDataCache.timestamp).all()
            
            if len(candles) >= 50:
                df = pd.DataFrame([{
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume
                } for c in candles])
                market_data[symbol] = df
                logger.info(f"  ✅ {symbol}: {len(df)} candles")
        
        # Step 3: Run trading strategies
        logger.info("\n🔍 Step 3: Running Trading Strategies...")
        momentum = MomentumStrategy()
        mean_rev = MeanReversionStrategy()
        
        all_signals = []
        
        momentum_signals = await momentum.generate_signals(
            list(market_data.keys()),
            market_data
        )
        logger.info(f"  Momentum: {len(momentum_signals)} signals")
        all_signals.extend(momentum_signals)
        
        mean_rev_signals = await mean_rev.generate_signals(
            list(market_data.keys()),
            market_data
        )
        logger.info(f"  Mean Reversion: {len(mean_rev_signals)} signals")
        all_signals.extend(mean_rev_signals)
        
        if not all_signals:
            logger.info("\n✓ Strategies executed successfully!")
            logger.info("  No signals found (market conditions don't match criteria)")
            logger.info("\n💡 This is normal professional behavior:")
            logger.info("  - Not all stocks have setups every day")
            logger.info("  - Strategies wait for high-probability setups")
            logger.info("  - Quality over quantity")
            logger.info("\n  Try running again tomorrow or with more symbols")
            return
        
        logger.info(f"\n✅ Total signals found: {len(all_signals)}")
        
        # Step 4: AI Analysis (REAL OpenAI)
        logger.info("\n🤖 Step 4: AI Analysis with GPT-4...")
        llm = OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        )
        
        analyzed_signals = []
        
        for i, signal in enumerate(all_signals[:3], 1):  # Analyze top 3 to save API costs
            logger.info(f"\n  Analyzing {i}/{min(3, len(all_signals))}: {signal['symbol']}...")
            
            # Prepare market summary
            symbol_df = market_data[signal['symbol']]
            latest = symbol_df.iloc[-1]
            
            market_summary = {
                "latest_close": float(latest["close"]),
                "latest_volume": int(latest["volume"]),
                "recent_prices": symbol_df.tail(5)["close"].tolist()
            }
            
            # Call OpenAI API
            analysis = await llm.generate_trade_analysis(
                signal=signal,
                market_data=market_summary,
                context={"market": "NSE", "sector": "various"}
            )
            
            logger.info(f"    Confidence: {analysis.get('confidence', 0):.2f}")
            logger.info(f"    Evidence: {analysis.get('evidence', '')[:80]}...")
            
            # Merge analysis with signal
            analyzed_signal = {
                **signal,
                "llm_analysis": analysis,
                "confidence": analysis.get("confidence", signal.get("score", 0.5)),
                "evidence": analysis.get("evidence", signal.get("reasoning", "")),
                "risks": analysis.get("risks", "Standard market risks apply."),
                "model_version": analysis.get("model_version", settings.openai_model)
            }
            
            analyzed_signals.append(analyzed_signal)
        
        logger.info(f"\n✅ AI analyzed {len(analyzed_signals)} signals with GPT-4")
        
        # Step 5: Risk Checks
        logger.info("\n🛡️  Step 5: Running Risk Checks...")
        risk_checker = RiskChecker(db)
        
        passed = 0
        failed = 0
        
        for signal in analyzed_signals:
            quantity = 10  # Test quantity
            
            checks_ok, warnings = await risk_checker.run_all_checks(
                symbol=signal['symbol'],
                quantity=quantity,
                entry_price=signal['entry_price'],
                stop_loss=signal['suggested_sl'],
                trade_type=signal['trade_type']
            )
            
            if checks_ok:
                passed += 1
                logger.info(f"  ✅ {signal['symbol']}: PASS")
            else:
                failed += 1
                logger.info(f"  ⚠️  {signal['symbol']}: {len(warnings)} warnings")
        
        logger.info(f"\n  Risk checks: {passed} passed, {failed} with warnings")
        
        # Step 6: Create Trade Cards
        logger.info("\n💳 Step 6: Creating Trade Cards...")
        audit_logger = AuditLogger(db)
        
        created_ids = []
        
        for signal in analyzed_signals:
            quantity = 10
            
            # Final risk check
            checks_ok, warnings = await risk_checker.run_all_checks(
                symbol=signal['symbol'],
                quantity=quantity,
                entry_price=signal['entry_price'],
                stop_loss=signal['suggested_sl'],
                trade_type=signal['trade_type']
            )
            
            # Create trade card
            trade_card = TradeCard(
                symbol=signal['symbol'],
                entry_price=signal['entry_price'],
                quantity=quantity,
                stop_loss=signal['suggested_sl'],
                take_profit=signal['suggested_tp'],
                trade_type=signal['trade_type'],
                strategy=signal['strategy'],
                confidence=signal['confidence'],
                evidence=signal['evidence'],
                risks=signal['risks'],
                horizon_days=signal.get('llm_analysis', {}).get('horizon_days', 3),
                status="pending_approval",
                liquidity_check=checks_ok,
                position_size_check=checks_ok,
                exposure_check=checks_ok,
                event_window_check=True,
                risk_warnings=warnings,
                model_version=signal.get('model_version', 'gpt-4-turbo-preview')
            )
            
            db.add(trade_card)
            db.commit()
            db.refresh(trade_card)
            
            # Log audit trail
            audit_logger.log_trade_card_created(
                trade_card_id=trade_card.id,
                trade_card_data={
                    "symbol": signal['symbol'],
                    "entry_price": signal['entry_price'],
                    "quantity": quantity
                },
                signal_data=signal,
                llm_analysis=signal.get('llm_analysis', {}),
                risk_checks={"passed": checks_ok, "warnings": warnings}
            )
            
            created_ids.append(trade_card.id)
            logger.info(f"  ✅ Trade Card #{trade_card.id}: {signal['symbol']}")
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("🎉 END-TO-END TEST COMPLETE!")
        logger.info("=" * 70)
        logger.info(f"\n✅ Market Data: {len(symbols)} stocks with real prices")
        logger.info(f"✅ Signals Generated: {len(all_signals)} by strategies")
        logger.info(f"✅ AI Analysis: {len(analyzed_signals)} analyzed by GPT-4")
        logger.info(f"✅ Trade Cards Created: {len(created_ids)}")
        logger.info(f"✅ Audit Logs: {len(created_ids)} entries created")
        
        logger.info("\n📋 TRADE CARDS READY FOR APPROVAL:")
        logger.info("=" * 70)
        
        for trade_id in created_ids:
            trade = db.query(TradeCard).filter(TradeCard.id == trade_id).first()
            logger.info(f"\n#{trade.id} - {trade.symbol} ({trade.strategy.upper()})")
            logger.info(f"  Entry: ₹{trade.entry_price:.2f} | SL: ₹{trade.stop_loss:.2f} | TP: ₹{trade.take_profit:.2f}")
            logger.info(f"  Qty: {trade.quantity} | Confidence: {trade.confidence*100:.0f}%")
            logger.info(f"  Evidence: {trade.evidence[:100]}...")
            logger.info(f"  Risks: {trade.risks[:100]}...")
        
        logger.info("\n" + "=" * 70)
        logger.info("🌐 NEXT STEPS:")
        logger.info("=" * 70)
        logger.info("\n1. Open browser: http://localhost:8000")
        logger.info("2. View trade cards in 'Pending Approvals' tab")
        logger.info("3. Click 'Login with Upstox' to authenticate")
        logger.info("4. Review AI-generated evidence and risks")
        logger.info("5. Click 'Approve' to place order with Upstox")
        logger.info("6. Monitor execution in 'Orders' tab")
        logger.info("\n" + "=" * 70 + "\n")
        
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


async def main():
    """Main entry point."""
    await full_test()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


