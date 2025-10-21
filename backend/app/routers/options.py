"""Options API endpoints (real data only)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..services.upstox_service import UpstoxService


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


