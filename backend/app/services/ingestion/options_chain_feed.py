"""Fetch and store option chain data from Upstox into OptionChain table."""
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from ..upstox_service import UpstoxService
from ...database import OptionChain


class OptionsChainFeed:
    def __init__(self, db: Session):
        self.db = db
        self.svc = UpstoxService(db)

    async def fetch_and_store(self, symbol: str, exchange: str = "NSE", expiry: str | None = None) -> Dict[str, Any]:
        broker = self.svc._get_broker()
        instrument_key = broker._get_instrument_key(symbol, exchange)
        data = await broker.get_option_chain(instrument_key=instrument_key, expiry_date=expiry)
        if not data:
            return {"stored": 0}

        # Expected structure: data["expiry_dates"], data["data"][strike]["call"|"put"] ...
        # Normalize commonly returned structure
        strikes = data.get("strikes") or []
        stored = 0
        spot = data.get("spot_price") or 0
        pcr = 0
        atm_iv = None
        for s in strikes:
            strike = float(s.get("strike"))
            call = s.get("call", {})
            put = s.get("put", {})
            row = OptionChain(
                symbol=symbol,
                exchange=exchange,
                expiry=datetime.strptime((expiry or data.get("nearest_expiry")), "%Y-%m-%d").date(),
                strike=strike,
                ce_ltp=call.get("ltp"),
                ce_oi=call.get("oi"),
                ce_iv=call.get("iv"),
                pe_ltp=put.get("ltp"),
                pe_oi=put.get("oi"),
                pe_iv=put.get("iv"),
                spot_price=spot,
                atm_iv=atm_iv,
                pcr=pcr,
                ts=datetime.utcnow()
            )
            self.db.merge(row)
            stored += 1
        self.db.commit()
        return {"stored": stored}


