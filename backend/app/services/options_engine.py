"""Options strategy generation (basic)."""
from typing import List, Dict, Any, Optional
from datetime import date
from sqlalchemy.orm import Session
from ..database import OptionChain, OptionStrategy


class OptionsEngine:
    def __init__(self, db: Session):
        self.db = db

    def _get_chain(self, symbol: str, expiry: date) -> List[Dict[str, Any]]:
        rows = self.db.query(OptionChain).filter(
            OptionChain.symbol == symbol,
            OptionChain.expiry == expiry
        ).order_by(OptionChain.strike).all()
        chain = []
        for r in rows:
            chain.append({
                "strike": r.strike,
                "ce_ltp": r.ce_ltp,
                "pe_ltp": r.pe_ltp,
                "spot_price": r.spot_price
            })
        return chain

    def generate_iron_condor(self, symbol: str, expiry: date, account_id: int, max_risk: float = 20000.0) -> Optional[Dict[str, Any]]:
        chain = self._get_chain(symbol, expiry)
        if not chain or len(chain) < 10:
            return None
        spot = chain[0]["spot_price"]
        if not spot:
            return None
        atm_idx = min(range(len(chain)), key=lambda i: abs(chain[i]["strike"] - spot))
        if atm_idx < 4 or atm_idx > len(chain) - 5:
            return None
        sell_call = chain[atm_idx + 2]
        buy_call = chain[atm_idx + 4]
        sell_put = chain[atm_idx - 2]
        buy_put = chain[atm_idx - 4]

        net_premium = (sell_call["ce_ltp"] or 0) + (sell_put["pe_ltp"] or 0) - (buy_call["ce_ltp"] or 0) - (buy_put["pe_ltp"] or 0)
        wing = buy_call["strike"] - sell_call["strike"]
        max_profit = max(0.0, net_premium * 100)
        max_loss = max(0.0, (wing - net_premium) * 100)
        if max_loss > max_risk:
            return None
        strategy = {
            "account_id": account_id,
            "strategy_type": "IRON_CONDOR",
            "underlying": symbol,
            "expiry": expiry,
            "legs": [
                {"type": "SELL", "option_type": "CE", "strike": sell_call["strike"], "premium": sell_call["ce_ltp"], "quantity": 1},
                {"type": "BUY", "option_type": "CE", "strike": buy_call["strike"], "premium": buy_call["ce_ltp"], "quantity": 1},
                {"type": "SELL", "option_type": "PE", "strike": sell_put["strike"], "premium": sell_put["pe_ltp"], "quantity": 1},
                {"type": "BUY", "option_type": "PE", "strike": buy_put["strike"], "premium": buy_put["pe_ltp"], "quantity": 1}
            ],
            "net_premium": round(net_premium, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven_upper": sell_call["strike"] + net_premium,
            "breakeven_lower": sell_put["strike"] - net_premium,
            "margin_required": max_loss,
            "pop": 0.65,
            "pnl_scenarios": []
        }
        return strategy

    def persist_strategy(self, strategy: Dict[str, Any]) -> OptionStrategy:
        obj = OptionStrategy(
            account_id=strategy.get("account_id"),
            strategy_type=strategy.get("strategy_type"),
            underlying=strategy.get("underlying"),
            expiry=strategy.get("expiry"),
            legs=strategy.get("legs"),
            net_premium=strategy.get("net_premium"),
            max_profit=strategy.get("max_profit"),
            max_loss=strategy.get("max_loss"),
            breakeven_upper=strategy.get("breakeven_upper"),
            breakeven_lower=strategy.get("breakeven_lower"),
            margin_required=strategy.get("margin_required"),
            pop=strategy.get("pop"),
            pnl_scenarios=strategy.get("pnl_scenarios"),
            status="PENDING"
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj


