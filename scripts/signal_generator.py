"""Daily signal generation script."""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from datetime import datetime
from backend.app.database import SessionLocal
from backend.app.services.pipeline import TradeCardPipeline
from backend.app.services.broker import UpstoxBroker
from backend.app.config import get_settings
from backend.app.database import Setting

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Default symbols to scan
DEFAULT_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "ULTRACEMCO", "BAJFINANCE", "NESTLEIND", "HCLTECH",
    "WIPRO", "ONGC", "NTPC", "POWERGRID", "TECHM",
    "M&M", "TATAMOTORS", "BAJAJFINSV", "DIVISLAB", "ADANIPORTS",
    "TATASTEEL", "HINDALCO", "JSWSTEEL", "COALINDIA", "GRASIM"
]


async def run_signal_generation():
    """Run signal generation pipeline."""
    db = SessionLocal()
    
    try:
        logger.info("=" * 60)
        logger.info(f"Starting signal generation at {datetime.now()}")
        logger.info("=" * 60)
        
        # Initialize broker
        broker = None
        try:
            broker = UpstoxBroker(
                api_key=settings.upstox_api_key,
                api_secret=settings.upstox_api_secret,
                redirect_uri=settings.upstox_redirect_uri
            )
            
            # Load access token from database
            access_token_setting = db.query(Setting).filter(
                Setting.key == "upstox_access_token"
            ).first()
            
            if access_token_setting and access_token_setting.value:
                broker.access_token = access_token_setting.value
                logger.info("Broker initialized with saved token")
            else:
                logger.warning("No broker token found, will use cached data only")
                broker = None
                
        except Exception as e:
            logger.warning(f"Broker initialization failed: {e}")
            broker = None
        
        # Initialize pipeline
        pipeline = TradeCardPipeline(db, broker)
        
        # Run pipeline
        logger.info(f"Scanning {len(DEFAULT_SYMBOLS)} symbols...")
        result = await pipeline.run_pipeline(
            symbols=DEFAULT_SYMBOLS,
            strategies=None,  # Run all strategies
            max_trade_cards=5
        )
        
        logger.info("=" * 60)
        logger.info("Signal Generation Results:")
        logger.info(f"  Signals generated: {result['signals_generated']}")
        logger.info(f"  Signals analyzed: {result['analyzed_signals']}")
        logger.info(f"  Trade cards created: {result['trade_cards_created']}")
        logger.info(f"  Trade card IDs: {result['trade_card_ids']}")
        logger.info("=" * 60)
        
        if result['trade_cards_created'] > 0:
            logger.info("✓ Signal generation completed successfully!")
        else:
            logger.info("⚠ No trade cards created (no signals met criteria)")
            
        return result
        
    except Exception as e:
        logger.error(f"Signal generation failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    try:
        asyncio.run(run_signal_generation())
    except KeyboardInterrupt:
        logger.info("Signal generation interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

