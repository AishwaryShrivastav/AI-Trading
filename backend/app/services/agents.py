"""Specialist agents (TradeHarness Step 2b).

Cheap, focused Claude-Haiku agents that enrich the orchestrator's decision
context. Each reads real DB state and returns a small structured dict:

  - NewsAgent      -> per-symbol/sector sentiment from recent Events
  - TechnicalAgent -> per-symbol technical posture from latest Features
  - MacroAgent     -> market regime + sector rotation (best-effort until
                      Step 3 adds VIX/FII-DII feeds)

All agents degrade gracefully: on any LLM/data error they return a neutral
default so the orchestrator always gets a well-formed context.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..database import Event, Feature
from .llm import get_agent_llm

logger = logging.getLogger(__name__)


class _BaseAgent:
    name = "agent"

    def __init__(self, db: Session, llm=None):
        self.db = db
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_agent_llm()
        return self._llm


class NewsAgent(_BaseAgent):
    name = "news"

    async def analyze(self, symbols: List[str], lookback_hours: int = 24) -> Dict[str, Any]:
        since = datetime.utcnow() - timedelta(hours=lookback_hours)
        events = (
            self.db.query(Event)
            .filter(Event.event_timestamp >= since)
            .order_by(Event.event_timestamp.desc())
            .limit(50)
            .all()
        )
        sym_set = {s.upper() for s in symbols}
        relevant = []
        for e in events:
            esyms = [str(s).upper() for s in (e.symbols or [])]
            if sym_set.intersection(esyms):
                relevant.append({
                    "symbols": esyms,
                    "event_type": e.event_type,
                    "priority": e.priority,
                    "sector": e.sector,
                    "content": (e.normalized_content or e.raw_content or "")[:400],
                    "ts": e.event_timestamp.isoformat() if e.event_timestamp else None,
                })

        if not relevant:
            return {"sentiment": {}, "events_considered": 0, "note": "no recent news"}

        try:
            result = await self.llm.complete_json(
                system="You are a financial news sentiment analyst for Indian equities.",
                user=(
                    "Score sentiment for each affected symbol from the news items below, "
                    "from -1.0 (very bearish) to +1.0 (very bullish), with a confidence 0..1.\n\n"
                    f"News items:\n{json.dumps(relevant, indent=2, default=str)}\n\n"
                    'Respond as JSON: {"sentiment": {"SYMBOL": {"score": <float>, '
                    '"confidence": <float>, "rationale": "<short>"}}}'
                ),
                max_tokens=1200,
            )
            sentiment = result.get("sentiment", {}) if isinstance(result, dict) else {}
            return {"sentiment": sentiment, "events_considered": len(relevant)}
        except Exception as e:
            logger.warning(f"NewsAgent failed: {e}")
            return {"sentiment": {}, "events_considered": len(relevant), "error": str(e)}


class TechnicalAgent(_BaseAgent):
    name = "technical"

    def _latest_features(self, symbols: List[str]) -> List[Dict[str, Any]]:
        out = []
        for sym in symbols:
            f = (
                self.db.query(Feature)
                .filter(Feature.symbol == sym)
                .order_by(Feature.timestamp.desc())
                .first()
            )
            if f:
                out.append({
                    "symbol": sym,
                    "momentum_20d": getattr(f, "momentum_20d", None),
                    "rsi_14": getattr(f, "rsi_14", None),
                    "atr_percent": getattr(f, "atr_percent", None),
                    "regime_label": getattr(f, "regime_label", None),
                    "liquidity_regime": getattr(f, "liquidity_regime", None),
                })
        return out

    async def analyze(self, symbols: List[str]) -> Dict[str, Any]:
        feats = self._latest_features(symbols)
        if not feats:
            return {"technical": {}, "symbols_considered": 0, "note": "no features"}
        try:
            result = await self.llm.complete_json(
                system="You are a technical analyst for Indian equities.",
                user=(
                    "For each symbol, give a posture (BULLISH/BEARISH/NEUTRAL) and a 0..1 "
                    "strength based on these indicators.\n\n"
                    f"{json.dumps(feats, indent=2, default=str)}\n\n"
                    'Respond as JSON: {"technical": {"SYMBOL": {"posture": "...", '
                    '"strength": <float>}}}'
                ),
                max_tokens=1000,
            )
            tech = result.get("technical", {}) if isinstance(result, dict) else {}
            return {"technical": tech, "symbols_considered": len(feats)}
        except Exception as e:
            logger.warning(f"TechnicalAgent failed: {e}")
            return {"technical": {}, "symbols_considered": len(feats), "error": str(e)}


class MacroAgent(_BaseAgent):
    name = "macro"

    async def analyze(self, symbols: List[str]) -> Dict[str, Any]:
        # Aggregate regime hints from latest features (proxy until Step 3 adds
        # India VIX / FII-DII / index breadth feeds).
        regimes: Dict[str, int] = {}
        for sym in symbols:
            f = (
                self.db.query(Feature)
                .filter(Feature.symbol == sym)
                .order_by(Feature.timestamp.desc())
                .first()
            )
            label = getattr(f, "regime_label", None) if f else None
            if label:
                regimes[label] = regimes.get(label, 0) + 1

        if not regimes:
            return {"regime": "unknown", "sector_rotation": [], "note": "no regime data"}

        try:
            result = await self.llm.complete_json(
                system="You are a macro strategist for Indian markets.",
                user=(
                    "Given this distribution of per-stock volatility regimes, classify the "
                    "overall market regime (trending-up/trending-down/ranging/high-volatility) "
                    "and name up to 3 sectors to overweight.\n\n"
                    f"Regime distribution: {json.dumps(regimes)}\n\n"
                    'Respond as JSON: {"regime": "<label>", "sector_rotation": ["..."], '
                    '"rationale": "<short>"}'
                ),
                max_tokens=600,
            )
            return {
                "regime": result.get("regime", "unknown"),
                "sector_rotation": result.get("sector_rotation", []),
                "rationale": result.get("rationale", ""),
            }
        except Exception as e:
            logger.warning(f"MacroAgent failed: {e}")
            return {"regime": "unknown", "sector_rotation": [], "error": str(e)}


async def run_specialist_agents(db: Session, symbols: List[str], llm=None) -> Dict[str, Any]:
    """Run all specialist agents and return a merged enrichment dict."""
    news = await NewsAgent(db, llm).analyze(symbols)
    technical = await TechnicalAgent(db, llm).analyze(symbols)
    macro = await MacroAgent(db, llm).analyze(symbols)
    return {
        "sentiment": news.get("sentiment", {}),
        "news_meta": {"events_considered": news.get("events_considered", 0)},
        "technical": technical.get("technical", {}),
        "regime": macro.get("regime", "unknown"),
        "sector_rotation": macro.get("sector_rotation", []),
    }
