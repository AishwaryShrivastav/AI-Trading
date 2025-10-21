"""Options API endpoints (real data only)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from ..database import get_db, OptionStrategy
from ..services.upstox_service import UpstoxService
from ..services.ingestion.options_chain_feed import OptionsChainFeed
from ..services.options_engine import OptionsEngine


router = APIRouter(prefix="/api/options", tags=["Options"])


@router.get("/chain")
async def get_option_chain(
    symbol: str = Query(..., min_length=1, max_length=20),
    exchange: str = Query("NSE"),
    expiry: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Return live option chain via Upstox for the given underlying."""
    try:
        # Fetch from Upstox and store in DB for consistency
        feed = OptionsChainFeed(db)
        await feed.fetch_and_store(symbol, exchange, expiry)

        svc = UpstoxService(db)
        broker = svc._get_broker()
        instrument_key = broker._get_instrument_key(symbol, exchange)
        data = await broker.get_option_chain(instrument_key=instrument_key, expiry_date=expiry)
        if not data:
            raise HTTPException(status_code=404, detail="Option chain not available")
        return {"symbol": symbol, "exchange": exchange, "expiry": expiry, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Upstream error: {e}")


class StrategyGenerateRequest(BaseModel):
    symbol: str
    expiry: date
    account_id: int
    strategy_type: str = "IRON_CONDOR"
    max_risk: float = 50000.0


@router.post("/strategy/generate")
async def generate_strategy(
    payload: StrategyGenerateRequest,
    db: Session = Depends(get_db)
):
    try:
        # Ensure chain exists for this symbol/expiry. Try to fetch live first.
        feed = OptionsChainFeed(db)
        await feed.fetch_and_store(payload.symbol, "NSE", payload.expiry.strftime("%Y-%m-%d"))

        engine = OptionsEngine(db)
        if payload.strategy_type.upper() == "IRON_CONDOR":
            strat = engine.generate_iron_condor(payload.symbol, payload.expiry, payload.account_id, payload.max_risk)
        else:
            raise HTTPException(status_code=400, detail="Unsupported strategy_type")

        if not strat:
            raise HTTPException(status_code=404, detail="Unable to generate strategy for given inputs")

        obj = engine.persist_strategy(strat)
        return {"strategy_id": obj.id, "strategy_type": obj.strategy_type}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Strategy generation failed: {e}")


class StrategyExecuteRequest(BaseModel):
    strategy_id: int


@router.post("/strategy/execute")
async def execute_strategy(
    payload: StrategyExecuteRequest,
    db: Session = Depends(get_db)
):
    try:
        # Validate existence
        obj = db.query(OptionStrategy).filter(OptionStrategy.id == payload.strategy_id).first()
        if not obj:
            raise HTTPException(status_code=404, detail="Strategy not found")

        svc = UpstoxService(db)
        result = await svc.execute_option_strategy(payload.strategy_id)
        return result
    except HTTPException:
        raise
    except RuntimeError as e:
        # Broker not authenticated or placement failed
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {e}")


