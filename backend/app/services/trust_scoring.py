"""Strategy trust scoring engine (TradeHarness Step 7).

After each trading day the EOD job calls :func:`update_trust_scores` which:
  1. Collects all paper positions closed today, grouped by strategy.
  2. Computes a raw day-score: 50 % win-rate + 50 % normalised return.
  3. EMA-smooths it into the rolling trust score (α = 0.3 by default).
  4. Persists the result to :class:`StrategyTrustScore`.

The trust scores are fed into the orchestrator context so Claude can factor in
each strategy's recent track record when deciding conviction tiers.
"""
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database import PositionV2, TradeCardV2, StrategyTrustScore

logger = logging.getLogger(__name__)

_EMA_ALPHA = 0.3          # weight given to the latest day vs history
_RETURN_SCALE = 10.0      # ±5 % return maps to 0–1 score band
_NEUTRAL_TRUST = 0.5      # starting score for a new strategy


def _day_score(positions: List[PositionV2]) -> Optional[float]:
    """Compute a 0–1 score for a single strategy on a single day."""
    if not positions:
        return None
    winners = [p for p in positions if (p.realized_pnl or 0) > 0]
    win_rate = len(winners) / len(positions)

    total_pnl = sum(float(p.realized_pnl or 0) for p in positions)
    total_invested = sum(
        float((p.average_entry_price or 0) * (p.quantity or 0)) for p in positions
    )
    return_pct = (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0

    # Clamp return into [0, 1] — centred at 0 %, ±(_RETURN_SCALE/2)% spans the range.
    normalised_return = max(0.0, min(1.0, (return_pct + _RETURN_SCALE / 2) / _RETURN_SCALE))

    return 0.5 * win_rate + 0.5 * normalised_return


def _ema(old: float, new: float, alpha: float = _EMA_ALPHA) -> float:
    return (1 - alpha) * old + alpha * new


def update_trust_scores(db: Session, target_date: Optional[date] = None) -> Dict[str, Any]:
    """Update all strategy trust scores for the given date (defaults to today).

    Returns a dict mapping strategy → {trust_score, day_score, trade_count}.
    """
    target_date = target_date or datetime.utcnow().date()

    # Collect closed paper positions for the target date
    all_positions = (
        db.query(PositionV2)
        .filter(
            PositionV2.is_paper == True,  # noqa: E712
            PositionV2.closed_at.isnot(None),
        )
        .all()
    )
    today_closed = [p for p in all_positions if p.closed_at and p.closed_at.date() == target_date]

    # Group by strategy (look up via trade_card relationship)
    by_strategy: Dict[str, List[PositionV2]] = {}
    for pos in today_closed:
        strategy = "unknown"
        if pos.trade_card_id:
            card = db.query(TradeCardV2).filter(TradeCardV2.id == pos.trade_card_id).first()
            if card and card.strategy:
                strategy = card.strategy
        by_strategy.setdefault(strategy, []).append(pos)

    results: Dict[str, Any] = {}

    for strategy, positions in by_strategy.items():
        day_score = _day_score(positions)
        if day_score is None:
            continue

        row = db.query(StrategyTrustScore).filter(StrategyTrustScore.strategy == strategy).first()
        if row is None:
            row = StrategyTrustScore(
                strategy=strategy,
                trust_score=_NEUTRAL_TRUST,
                trade_count=0,
            )
            db.add(row)

        old_trust = float(row.trust_score or _NEUTRAL_TRUST)
        new_trust = _ema(old_trust, day_score)

        total_pnl = sum(float(p.realized_pnl or 0) for p in positions)
        total_invested = sum(float((p.average_entry_price or 0) * (p.quantity or 0)) for p in positions)
        win_rate = len([p for p in positions if (p.realized_pnl or 0) > 0]) / len(positions)
        return_pct = (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0

        row.trust_score = round(new_trust, 4)
        row.last_day_score = round(day_score, 4)
        row.rolling_win_rate = round(
            _ema(float(row.rolling_win_rate or win_rate), win_rate), 4
        )
        row.rolling_return_pct = round(
            _ema(float(row.rolling_return_pct or return_pct), return_pct), 4
        )
        row.trade_count = (row.trade_count or 0) + len(positions)
        row.last_updated = datetime.utcnow()
        row.details = {
            "date": target_date.isoformat(),
            "trade_count_today": len(positions),
            "win_rate_today": round(win_rate, 4),
            "return_pct_today": round(return_pct, 4),
            "day_score": round(day_score, 4),
        }

        results[strategy] = {
            "trust_score": row.trust_score,
            "day_score": row.last_day_score,
            "win_rate": row.rolling_win_rate,
            "return_pct": row.rolling_return_pct,
            "trade_count": row.trade_count,
        }

    if results:
        db.commit()
        logger.info("[TRUST] Updated scores for %d strategy/ies: %s", len(results), list(results.keys()))
    else:
        logger.debug("[TRUST] No closed paper positions today (%s)", target_date)

    return results


def get_all_trust_scores(db: Session) -> List[Dict[str, Any]]:
    """Return all stored trust scores, sorted descending by trust_score."""
    rows = db.query(StrategyTrustScore).order_by(StrategyTrustScore.trust_score.desc()).all()
    return [
        {
            "strategy": r.strategy,
            "trust_score": r.trust_score,
            "rolling_win_rate": r.rolling_win_rate,
            "rolling_return_pct": r.rolling_return_pct,
            "trade_count": r.trade_count,
            "last_updated": str(r.last_updated),
        }
        for r in rows
    ]


def get_trust_score(db: Session, strategy: str) -> float:
    """Return the current trust score for a strategy (default 0.5 if unknown)."""
    row = db.query(StrategyTrustScore).filter(StrategyTrustScore.strategy == strategy).first()
    return float(row.trust_score) if row else _NEUTRAL_TRUST
