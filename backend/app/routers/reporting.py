"""Reporting endpoints for Step 7: performance, trust scores, regime, reflections."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import (
    get_db, BacktestResult, PositionV2, TradeCardV2,
    StrategyTrustScore, WeeklyReflection,
)
from ..services.trust_scoring import get_all_trust_scores, update_trust_scores
from ..services.regime_classifier import RegimeClassifier
from ..services.self_reflection import approve_reflection, reject_reflection

router = APIRouter(prefix="/api/reporting", tags=["reporting"])
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ performance

@router.get("/performance")
async def strategy_performance(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Aggregate per-strategy metrics from backtest results + live paper trades."""
    rows = db.query(BacktestResult).all()

    # Group backtest metrics by strategy (last result per strategy wins)
    bt_by_strategy: Dict[str, Dict] = {}
    for r in rows:
        existing = bt_by_strategy.get(r.strategy)
        if not existing or r.created_at > existing.get("_ts", datetime.min):
            bt_by_strategy[r.strategy] = {
                "strategy": r.strategy,
                "backtest_cagr": r.cagr,
                "backtest_sharpe": r.sharpe,
                "backtest_max_dd": r.max_drawdown,
                "backtest_win_rate": r.win_rate,
                "backtest_trades": r.num_trades,
                "_ts": r.created_at,
            }

    # Enrich with paper trading actuals
    closed = db.query(PositionV2).filter(
        PositionV2.is_paper == True,  # noqa: E712
        PositionV2.closed_at.isnot(None),
    ).all()

    paper_by_strategy: Dict[str, Dict] = {}
    for pos in closed:
        strategy = "unknown"
        if pos.trade_card_id:
            card = db.query(TradeCardV2).filter(TradeCardV2.id == pos.trade_card_id).first()
            if card and card.strategy:
                strategy = card.strategy
        s = paper_by_strategy.setdefault(strategy, {
            "pnl": 0.0, "invested": 0.0, "wins": 0, "count": 0,
        })
        s["pnl"] += float(pos.realized_pnl or 0)
        s["invested"] += float((pos.average_entry_price or 0) * (pos.quantity or 0))
        s["wins"] += 1 if (pos.realized_pnl or 0) > 0 else 0
        s["count"] += 1

    # Merge
    all_strategies = set(bt_by_strategy.keys()) | set(paper_by_strategy.keys())
    results = []
    for strategy in sorted(all_strategies):
        entry: Dict[str, Any] = {"strategy": strategy}
        if strategy in bt_by_strategy:
            bt = bt_by_strategy[strategy]
            entry.update({k: v for k, v in bt.items() if not k.startswith("_")})
        if strategy in paper_by_strategy:
            p = paper_by_strategy[strategy]
            ret_pct = (p["pnl"] / p["invested"] * 100.0) if p["invested"] > 0 else 0.0
            entry.update({
                "paper_trades": p["count"],
                "paper_win_rate": round(p["wins"] / p["count"], 4) if p["count"] else 0,
                "paper_return_pct": round(ret_pct, 4),
                "paper_total_pnl_inr": round(p["pnl"], 2),
            })
        results.append(entry)

    return {"strategies": results, "as_of": datetime.utcnow().isoformat()}


# ------------------------------------------------------------------ attribution

@router.get("/attribution")
async def pnl_attribution(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """P&L contribution per strategy over the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    closed = db.query(PositionV2).filter(
        PositionV2.is_paper == True,  # noqa: E712
        PositionV2.closed_at.isnot(None),
        PositionV2.closed_at >= since,
    ).all()

    by_strategy: Dict[str, float] = {}
    total_pnl = 0.0
    for pos in closed:
        strategy = "unknown"
        if pos.trade_card_id:
            card = db.query(TradeCardV2).filter(TradeCardV2.id == pos.trade_card_id).first()
            if card and card.strategy:
                strategy = card.strategy
        pnl = float(pos.realized_pnl or 0)
        by_strategy[strategy] = by_strategy.get(strategy, 0.0) + pnl
        total_pnl += pnl

    attribution = [
        {
            "strategy": s,
            "pnl_inr": round(v, 2),
            "share_pct": round(v / total_pnl * 100, 2) if total_pnl != 0 else 0.0,
        }
        for s, v in sorted(by_strategy.items(), key=lambda x: -abs(x[1]))
    ]
    return {
        "days": days,
        "total_pnl_inr": round(total_pnl, 2),
        "attribution": attribution,
    }


# ------------------------------------------------------------------ trust scores

@router.get("/trust-scores")
async def trust_scores(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Return current rolling trust scores for all strategies."""
    scores = get_all_trust_scores(db)
    return {"trust_scores": scores, "as_of": datetime.utcnow().isoformat()}


@router.post("/trust-scores/refresh")
async def refresh_trust_scores(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD, defaults to today"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Manually trigger a trust-score update for the given date."""
    target = None
    if date:
        try:
            from datetime import date as date_type
            target = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    results = update_trust_scores(db, target_date=target)
    return {"updated": results, "count": len(results)}


# ------------------------------------------------------------------ regime

@router.get("/regime")
async def market_regime(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Return the current market regime and per-strategy weight multipliers."""
    classifier = RegimeClassifier(db)
    return classifier.get_all_weights()


# ------------------------------------------------------------------ equity curve

@router.get("/equity-curve")
async def equity_curve(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Daily paper P&L for the past N days (for sparkline charts)."""
    since = datetime.utcnow() - timedelta(days=days)
    closed = db.query(PositionV2).filter(
        PositionV2.is_paper == True,  # noqa: E712
        PositionV2.closed_at.isnot(None),
        PositionV2.closed_at >= since,
    ).all()

    daily: Dict[str, float] = {}
    for pos in closed:
        d = pos.closed_at.date().isoformat()
        daily[d] = daily.get(d, 0.0) + float(pos.realized_pnl or 0)

    # Build cumulative curve
    sorted_dates = sorted(daily.keys())
    cumulative, running = [], 0.0
    for d in sorted_dates:
        running += daily[d]
        cumulative.append({"date": d, "daily_pnl": round(daily[d], 2), "cumulative_pnl": round(running, 2)})

    return {"days": days, "curve": cumulative, "total_pnl_inr": round(running, 2)}


# ------------------------------------------------------------------ reflections

@router.get("/reflection")
async def list_reflections(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return weekly reflections, optionally filtered by status."""
    q = db.query(WeeklyReflection).order_by(WeeklyReflection.created_at.desc())
    if status:
        q = q.filter(WeeklyReflection.status == status.upper())
    rows = q.limit(10).all()
    return {
        "reflections": [
            {
                "id": r.id,
                "period": f"{r.week_start.date()} → {r.week_end.date()}" if r.week_start else None,
                "status": r.status,
                "total_trades": (r.performance_data or {}).get("total_trades"),
                "total_pnl_inr": (r.performance_data or {}).get("total_pnl_inr"),
                "reflection": r.reflection,
                "reviewed_at": str(r.reviewed_at) if r.reviewed_at else None,
                "reviewed_by": r.reviewed_by,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]
    }


@router.post("/reflection/{reflection_id}/approve")
async def approve_weekly_reflection(
    reflection_id: int,
    reviewed_by: str = Query(default="human"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Approve a weekly reflection (mark as APPROVED; suggestions are noted, not auto-applied)."""
    try:
        rec = approve_reflection(db, reflection_id, reviewed_by)
        return {"status": "approved", "id": rec.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reflection/{reflection_id}/reject")
async def reject_weekly_reflection(
    reflection_id: int,
    reviewed_by: str = Query(default="human"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Reject a weekly reflection."""
    try:
        rec = reject_reflection(db, reflection_id, reviewed_by)
        return {"status": "rejected", "id": rec.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
