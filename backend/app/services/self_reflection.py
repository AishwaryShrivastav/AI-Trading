"""Weekly self-reflection engine (TradeHarness Step 7).

Every Friday at 17:00 IST the scheduler calls :func:`generate_weekly_reflection`
which:
  1. Aggregates the past 7 days of closed paper positions by strategy.
  2. Sends a structured prompt to Claude (or fallback LLM).
  3. Stores the LLM's response as a :class:`WeeklyReflection` with
     status=PENDING_REVIEW.
  4. The human reviews it via the HIL relay (/api/reporting/reflection) and
     either APPROVES or REJECTS.  The system never auto-applies suggestions.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database import PositionV2, TradeCardV2, WeeklyReflection

logger = logging.getLogger(__name__)


def _aggregate_week(db: Session, week_start: datetime, week_end: datetime) -> Dict[str, Any]:
    """Return per-strategy performance stats for the given period."""
    all_closed = (
        db.query(PositionV2)
        .filter(
            PositionV2.is_paper == True,  # noqa: E712
            PositionV2.closed_at.isnot(None),
            PositionV2.closed_at >= week_start,
            PositionV2.closed_at < week_end,
        )
        .all()
    )

    by_strategy: Dict[str, List[PositionV2]] = {}
    for pos in all_closed:
        strategy = "unknown"
        if pos.trade_card_id:
            card = db.query(TradeCardV2).filter(TradeCardV2.id == pos.trade_card_id).first()
            if card and card.strategy:
                strategy = card.strategy
        by_strategy.setdefault(strategy, []).append(pos)

    stats: Dict[str, Any] = {}
    for strategy, positions in by_strategy.items():
        winners = [p for p in positions if (p.realized_pnl or 0) > 0]
        total_pnl = sum(float(p.realized_pnl or 0) for p in positions)
        total_invested = sum(
            float((p.average_entry_price or 0) * (p.quantity or 0)) for p in positions
        )
        win_rate = len(winners) / len(positions)
        return_pct = (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0
        avg_hold_days = 0.0
        if any(p.opened_at and p.closed_at for p in positions):
            holds = [
                (p.closed_at - p.opened_at).total_seconds() / 86400.0
                for p in positions
                if p.opened_at and p.closed_at
            ]
            avg_hold_days = sum(holds) / len(holds) if holds else 0.0

        stats[strategy] = {
            "trade_count": len(positions),
            "win_rate": round(win_rate, 4),
            "total_pnl_inr": round(total_pnl, 2),
            "return_pct": round(return_pct, 4),
            "avg_hold_days": round(avg_hold_days, 2),
        }

    return {
        "period": f"{week_start.date()} → {week_end.date()}",
        "total_trades": len(all_closed),
        "total_pnl_inr": round(sum(float(p.realized_pnl or 0) for p in all_closed), 2),
        "by_strategy": stats,
    }


async def generate_weekly_reflection(
    db: Session,
    week_end: Optional[datetime] = None,
) -> Optional[WeeklyReflection]:
    """Aggregate the past 7 days, call LLM, and store a WeeklyReflection.

    Returns the new record or None if the LLM is not configured.
    """
    from ..config import get_settings
    settings = get_settings()
    if not settings.anthropic_api_key and not settings.openai_api_key:
        logger.info("[REFLECTION] No LLM key configured — skipping weekly reflection")
        return None

    week_end = week_end or datetime.utcnow()
    week_start = week_end - timedelta(days=7)

    perf = _aggregate_week(db, week_start, week_end)

    from .llm import get_llm_provider
    llm = get_llm_provider()

    system_prompt = (
        "You are a trading system analyst reviewing one week of paper trading results. "
        "Be concise and critical — the goal is continuous improvement. "
        "Return JSON with keys: "
        "observations (list of strings, max 5), "
        "strategy_suggestions (dict mapping strategy name → string suggestion), "
        "risk_notes (string), "
        "regime_hypothesis (string: what market regime we appear to be in and why), "
        "next_week_focus (string: one thing to watch or improve)."
    )

    reflection_data = await llm.complete_json(
        system=system_prompt,
        user=f"Weekly paper trading performance:\n{json.dumps(perf, indent=2)}",
        max_tokens=800,
    )

    record = WeeklyReflection(
        week_start=week_start,
        week_end=week_end,
        performance_data=perf,
        reflection=reflection_data,
        status="PENDING_REVIEW",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(
        "[REFLECTION] Weekly reflection created (id=%d) for %s → %s",
        record.id, week_start.date(), week_end.date(),
    )
    return record


def approve_reflection(
    db: Session, reflection_id: int, reviewed_by: str = "human"
) -> WeeklyReflection:
    """Mark a reflection as APPROVED. Does NOT auto-apply suggestions."""
    rec = db.query(WeeklyReflection).filter(WeeklyReflection.id == reflection_id).first()
    if not rec:
        raise ValueError(f"Reflection {reflection_id} not found")
    rec.status = "APPROVED"
    rec.reviewed_at = datetime.utcnow()
    rec.reviewed_by = reviewed_by
    db.commit()
    return rec


def reject_reflection(
    db: Session, reflection_id: int, reviewed_by: str = "human"
) -> WeeklyReflection:
    """Mark a reflection as REJECTED."""
    rec = db.query(WeeklyReflection).filter(WeeklyReflection.id == reflection_id).first()
    if not rec:
        raise ValueError(f"Reflection {reflection_id} not found")
    rec.status = "REJECTED"
    rec.reviewed_at = datetime.utcnow()
    rec.reviewed_by = reviewed_by
    db.commit()
    return rec
