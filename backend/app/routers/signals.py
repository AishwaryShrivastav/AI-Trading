"""Signal generation router."""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from ..database import get_db
from ..schemas import SignalGenerationRequest, SignalGenerationResponse
from ..services.pipeline import TradeCardPipeline
from ..services.broker import UpstoxBroker
from ..config import get_settings

router = APIRouter(prefix="/api/signals", tags=["signals"])
logger = logging.getLogger(__name__)
settings = get_settings()


# Default Indian stock symbols for scanning
DEFAULT_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "ULTRACEMCO", "BAJFINANCE", "NESTLEIND", "HCLTECH",
    "WIPRO", "ONGC", "NTPC", "POWERGRID", "TECHM",
    "M&M", "TATAMOTORS", "BAJAJFINSV", "DIVISLAB", "ADANIPORTS"
]


@router.post("/run", response_model=SignalGenerationResponse)
async def run_signal_generation(
    request: SignalGenerationRequest = SignalGenerationRequest(),
    db: Session = Depends(get_db)
):
    """
    Manually trigger signal generation pipeline.
    """
    try:
        # Get symbols to scan
        symbols = request.symbols or DEFAULT_SYMBOLS
        
        # Initialize broker if authenticated
        broker = None
        try:
            broker = UpstoxBroker(
                api_key=settings.upstox_api_key,
                api_secret=settings.upstox_api_secret,
                redirect_uri=settings.upstox_redirect_uri
            )
            
            from ..database import Setting
            access_token = db.query(Setting).filter(
                Setting.key == "upstox_access_token"
            ).first()
            
            if access_token:
                broker.access_token = access_token.value
        except Exception as e:
            logger.warning(f"Broker initialization failed: {e}")
        
        # Initialize pipeline
        pipeline = TradeCardPipeline(db, broker)
        
        # Run pipeline
        result = await pipeline.run_pipeline(
            symbols=symbols,
            strategies=request.strategies,
            max_trade_cards=5
        )
        
        from datetime import datetime
        return SignalGenerationResponse(
            candidates_found=result["signals_generated"],
            trade_cards_created=result["trade_cards_created"],
            timestamp=datetime.utcnow(),
            strategies_run=request.strategies or ["momentum", "mean_reversion"]
        )
        
    except Exception as e:
        logger.error(f"Signal generation failed: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-async")
async def run_signal_generation_async(
    background_tasks: BackgroundTasks,
    request: SignalGenerationRequest = SignalGenerationRequest(),
    db: Session = Depends(get_db)
):
    """
    Trigger signal generation in background.
    """
    def run_pipeline_task():
        # This would run in background
        # For now, just log
        logger.info("Background signal generation started")
    
    background_tasks.add_task(run_pipeline_task)
    
    return {
        "status": "started",
        "message": "Signal generation running in background"
    }


@router.get("/strategies")
async def list_strategies():
    """List available signal generation strategies."""
    return {
        "strategies": [
            {
                "name": "momentum",
                "description": "MA crossover with RSI and volume confirmation"
            },
            {
                "name": "mean_reversion",
                "description": "Bollinger Bands oversold/overbought reversions"
            }
        ]
    }

