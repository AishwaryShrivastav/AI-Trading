"""Orchestrator — the Claude decision brain (TradeHarness Step 2a).

Turns the prior "rules decide, LLM explains" flow into "the orchestrator
decides, with conviction tiers." Responsibilities:

  1. assemble_context  — gather regime, candidate signals, open positions,
                          risk budget and recent decisions from the DB.
  2. decide            — call the LLM's orchestrate_decisions, validate the
                          JSON, deterministically assign AUTO/HIL/SKIP tiers,
                          track per-day cost, and fall back to a rule-based
                          plan on any failure (cost cap, LLM error, bad JSON).

Tiers are assigned here (not by the model) so routing is deterministic:
  conviction < hil_min                       -> SKIP
  conviction >= auto and no risk flags       -> AUTO
  otherwise                                  -> HIL
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import Setting, Signal, PositionV2, RiskSnapshot, TradeCardV2
from .llm import get_llm_provider

logger = logging.getLogger(__name__)

# Rough public pricing (USD per million tokens) for cost estimation. Keyed by a
# substring of the model id. Conservative; only used for the daily cost cap.
_PRICING_USD_PER_MTOK = {
    "claude-opus": (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (0.80, 4.0),
    "gpt-4": (10.0, 30.0),
}
_USD_INR = 83.0
_VALID_DIRECTIONS = {"LONG", "SHORT"}


class Orchestrator:
    def __init__(self, db: Session, llm=None, settings=None, agent_llm=None):
        self.db = db
        self.settings = settings or get_settings()
        self._llm = llm  # lazily resolved so tests can inject a mock
        self._agent_llm = agent_llm  # specialist-agent LLM (Haiku); None -> default

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    # ------------------------------------------------------------- context
    def assemble_context(self, symbols: List[str], account_id: Optional[int] = None) -> Dict[str, Any]:
        """Build the decision context the orchestrator reasons over."""
        signals = (
            self.db.query(Signal)
            .filter(Signal.symbol.in_(symbols), Signal.status == "ACTIVE")
            .all()
        )
        candidate_signals = [
            {
                "symbol": s.symbol,
                "direction": s.direction,
                "edge": s.edge,
                "confidence": s.confidence,
                "quality_score": s.quality_score,
                "horizon_days": s.horizon_days,
                "regime_compatible": s.regime_compatible,
                "thesis_bullets": s.thesis_bullets or [],
            }
            for s in signals
        ]

        pos_q = self.db.query(PositionV2).filter(PositionV2.closed_at.is_(None))
        if account_id is not None:
            pos_q = pos_q.filter(PositionV2.account_id == account_id)
        open_positions = [
            {
                "symbol": p.symbol,
                "direction": p.direction,
                "quantity": p.quantity,
                "avg_entry": p.average_entry_price,
                "unrealized_pnl": p.unrealized_pnl,
            }
            for p in pos_q.all()
        ]

        snap_q = self.db.query(RiskSnapshot)
        if account_id is not None:
            snap_q = snap_q.filter(RiskSnapshot.account_id == account_id)
        snap = snap_q.order_by(RiskSnapshot.id.desc()).first()
        risk_budget = (
            {
                "total_open_risk": snap.total_open_risk,
                "daily_realized_pnl": snap.daily_realized_pnl,
                "daily_max_drawdown": snap.daily_max_drawdown,
                "portfolio_volatility": snap.portfolio_volatility,
            }
            if snap
            else {}
        )

        recent = (
            self.db.query(TradeCardV2)
            .order_by(TradeCardV2.id.desc())
            .limit(5)
            .all()
        )
        recent_decisions = [
            {"symbol": c.symbol, "direction": c.direction, "status": c.status, "confidence": c.confidence}
            for c in recent
        ]

        try:
            from .regime_classifier import RegimeClassifier
            regime_data = RegimeClassifier(self.db).get_all_weights()
        except Exception:
            regime_data = {"regime": "unknown", "strategy_weights": {}, "vix": None}

        try:
            from .trust_scoring import get_all_trust_scores
            trust_scores = get_all_trust_scores(self.db)
        except Exception:
            trust_scores = []

        return {
            "as_of": datetime.utcnow().isoformat(),
            "universe": symbols,
            "candidate_signals": candidate_signals,
            "open_positions": open_positions,
            "risk_budget": risk_budget,
            "recent_decisions": recent_decisions,
            "regime": regime_data.get("regime", "unknown"),
            "regime_weights": regime_data.get("strategy_weights", {}),
            "vix": regime_data.get("vix"),
            "trust_scores": trust_scores,
            "sentiment": {},
        }

    async def _enrich_context(self, context: Dict[str, Any], symbols: List[str]) -> None:
        """Enrich context in-place with specialist-agent output (Step 2b).

        Best-effort: agents degrade to neutral defaults, so failures here never
        block a decision. Skipped when disabled or when the cost cap is hit.
        """
        if not getattr(self.settings, "use_specialist_agents", False):
            return
        if self._cost_exceeded():
            return
        try:
            from .agents import run_specialist_agents

            enrichment = await run_specialist_agents(self.db, symbols, llm=self._agent_llm)
            context["sentiment"] = enrichment.get("sentiment", {})
            context["technical"] = enrichment.get("technical", {})
            context["regime"] = enrichment.get("regime", context.get("regime", "unknown"))
            context["sector_rotation"] = enrichment.get("sector_rotation", [])
            context["news_meta"] = enrichment.get("news_meta", {})
        except Exception as e:
            logger.warning(f"Context enrichment failed (continuing without): {e}")

    # ------------------------------------------------------------- decide
    async def decide(self, symbols: List[str], account_id: Optional[int] = None) -> Dict[str, Any]:
        context = self.assemble_context(symbols, account_id)
        await self._enrich_context(context, symbols)

        if self._cost_exceeded():
            logger.warning("LLM daily cost cap reached — using rule-based fallback.")
            return self._fallback(context, reason="cost_cap")

        try:
            raw = await self.llm.orchestrate_decisions(context)
        except Exception as e:
            logger.error(f"Orchestrator LLM call failed: {e}")
            return self._fallback(context, reason=f"llm_error: {e}")

        cleaned = self._validate(raw)
        if cleaned is None:
            logger.warning("Orchestrator returned invalid schema — using rule-based fallback.")
            return self._fallback(context, reason="invalid_schema")

        self._track_cost(raw.get("_usage"), raw.get("_model"))
        return self._route(cleaned, source=raw.get("_model", "llm"))

    # ------------------------------------------------------------- validation
    def _validate(self, raw: Any) -> Optional[Dict[str, Any]]:
        """Return a cleaned decision dict, or None if structurally invalid."""
        if not isinstance(raw, dict):
            return None
        recs = raw.get("trade_recommendations")
        if not isinstance(recs, list):
            return None

        clean_recs: List[Dict[str, Any]] = []
        for r in recs:
            if not isinstance(r, dict):
                return None
            instrument = r.get("instrument")
            direction = str(r.get("direction", "")).upper()
            conviction = r.get("conviction")
            if not instrument or direction not in _VALID_DIRECTIONS:
                return None
            if not isinstance(conviction, (int, float)) or not (0.0 <= conviction <= 1.0):
                return None
            clean_recs.append(
                {
                    "instrument": instrument,
                    "direction": direction,
                    "conviction": float(conviction),
                    "size_pct": float(r.get("size_pct") or 0.0),
                    "stop_loss": r.get("stop_loss"),
                    "reasoning": r.get("reasoning", ""),
                }
            )

        return {
            "market_thesis": str(raw.get("market_thesis", "")),
            "regime_assessment": str(raw.get("regime_assessment", "")),
            "risk_flags": [str(f) for f in (raw.get("risk_flags") or []) if f],
            "trade_recommendations": clean_recs,
        }

    # ------------------------------------------------------------- routing
    def _assign_tier(self, conviction: float, has_flags: bool) -> str:
        if conviction < self.settings.hil_min_conviction:
            return "SKIP"
        if conviction >= self.settings.auto_execute_conviction and not has_flags:
            return "AUTO"
        return "HIL"

    def _route(self, cleaned: Dict[str, Any], source: str) -> Dict[str, Any]:
        has_flags = bool(cleaned["risk_flags"])
        routed = []
        for rec in cleaned["trade_recommendations"]:
            rec = dict(rec)
            rec["tier"] = self._assign_tier(rec["conviction"], has_flags)
            routed.append(rec)
        return {
            "source": source,
            "fallback": False,
            "market_thesis": cleaned["market_thesis"],
            "regime_assessment": cleaned["regime_assessment"],
            "risk_flags": cleaned["risk_flags"],
            "trade_recommendations": routed,
            "tier_counts": self._tier_counts(routed),
        }

    @staticmethod
    def _tier_counts(routed: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"AUTO": 0, "HIL": 0, "SKIP": 0}
        for r in routed:
            counts[r["tier"]] = counts.get(r["tier"], 0) + 1
        return counts

    # ------------------------------------------------------------- fallback
    def _fallback(self, context: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """Rule-based plan when the LLM can't be used. Conservative: every
        candidate becomes at most a HIL (never AUTO) so a human still gates it."""
        recs = []
        for s in context.get("candidate_signals", []):
            conviction = float(s.get("confidence") or s.get("quality_score") or 0.5)
            direction = "LONG" if (s.get("direction") or "LONG").upper() in ("LONG", "BUY") else "SHORT"
            # Cap below AUTO threshold — rule-based never auto-executes.
            tier = "HIL" if conviction >= self.settings.hil_min_conviction else "SKIP"
            recs.append(
                {
                    "instrument": s["symbol"],
                    "direction": direction,
                    "conviction": min(conviction, self.settings.auto_execute_conviction - 0.01),
                    "size_pct": 0.0,
                    "stop_loss": None,
                    "reasoning": "Rule-based fallback (orchestrator unavailable).",
                    "tier": tier,
                }
            )
        return {
            "source": "rule_based",
            "fallback": True,
            "fallback_reason": reason,
            "market_thesis": "Rule-based fallback in effect; LLM orchestrator unavailable.",
            "regime_assessment": context.get("regime", "unknown"),
            "risk_flags": ["orchestrator_fallback"],
            "trade_recommendations": recs,
            "tier_counts": self._tier_counts(recs),
        }

    # ------------------------------------------------------------- cost
    def _cost_key(self) -> str:
        return f"llm_cost_{datetime.utcnow().strftime('%Y-%m-%d')}"

    def _today_cost(self) -> float:
        row = self.db.query(Setting).filter(Setting.key == self._cost_key()).first()
        try:
            return float(row.value) if row and row.value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _cost_exceeded(self) -> bool:
        return self._today_cost() >= self.settings.daily_llm_cost_cap_inr

    def _track_cost(self, usage: Optional[Dict[str, Any]], model: Optional[str]) -> None:
        if not usage:
            return
        in_tok = float(usage.get("input_tokens") or 0)
        out_tok = float(usage.get("output_tokens") or 0)
        in_price, out_price = (0.0, 0.0)
        for key, prices in _PRICING_USD_PER_MTOK.items():
            if model and key in model:
                in_price, out_price = prices
                break
        cost_inr = ((in_tok / 1e6) * in_price + (out_tok / 1e6) * out_price) * _USD_INR

        key = self._cost_key()
        row = self.db.query(Setting).filter(Setting.key == key).first()
        new_total = self._today_cost() + cost_inr
        if row:
            row.value = new_total
        else:
            self.db.add(Setting(key=key, value=new_total, description="Daily LLM cost (INR)"))
        self.db.commit()
        logger.info(f"LLM call cost ~₹{cost_inr:.2f} (today ₹{new_total:.2f}/{self.settings.daily_llm_cost_cap_inr})")
