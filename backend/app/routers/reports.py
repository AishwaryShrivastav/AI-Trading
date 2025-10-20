"""Reports router for EOD and monthly reports."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import logging

from ..database import get_db, TradeCard, Order, Position
from ..schemas import EODReportResponse, MonthlyReportResponse
from sqlalchemy import func

router = APIRouter(prefix="/api/reports", tags=["reports"])
logger = logging.getLogger(__name__)


@router.get("/eod", response_model=EODReportResponse)
async def get_eod_report(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    """Generate End-of-Day report."""
    try:
        # Parse date or use today
        if date:
            report_date = datetime.strptime(date, "%Y-%m-%d").date()
        else:
            report_date = datetime.utcnow().date()
        
        # Get trades for the day
        trades = db.query(TradeCard).filter(
            func.date(TradeCard.created_at) == report_date
        ).all()
        
        # Get open positions
        open_positions = db.query(Position).filter(
            Position.closed_at.is_(None)
        ).all()
        
        # Get closed positions for the day
        closed_positions = db.query(Position).filter(
            func.date(Position.closed_at) == report_date
        ).all()
        
        # Calculate P&L
        realized_pnl = sum(p.realized_pnl or 0 for p in closed_positions)
        unrealized_pnl = sum(p.unrealized_pnl or 0 for p in open_positions)
        total_pnl = realized_pnl + unrealized_pnl
        
        # Calculate win rate
        winning_trades = len([p for p in closed_positions if (p.realized_pnl or 0) > 0])
        total_closed = len(closed_positions)
        win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0.0
        
        # Guardrail hits
        guardrail_hits = {
            "liquidity_failed": len([t for t in trades if not t.liquidity_check]),
            "position_size_failed": len([t for t in trades if not t.position_size_check]),
            "exposure_failed": len([t for t in trades if not t.exposure_check])
        }
        
        # Top performers
        top_performers = sorted(
            [{"symbol": p.symbol, "pnl": p.realized_pnl} for p in closed_positions if p.realized_pnl],
            key=lambda x: x["pnl"],
            reverse=True
        )[:5]
        
        # Worst performers
        worst_performers = sorted(
            [{"symbol": p.symbol, "pnl": p.realized_pnl} for p in closed_positions if p.realized_pnl],
            key=lambda x: x["pnl"]
        )[:5]
        
        return EODReportResponse(
            date=report_date.isoformat(),
            total_trades=len(trades),
            open_positions=len(open_positions),
            closed_positions=len(closed_positions),
            realized_pnl=round(realized_pnl, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            total_pnl=round(total_pnl, 2),
            win_rate=round(win_rate, 2),
            guardrail_hits=guardrail_hits,
            top_performers=top_performers,
            worst_performers=worst_performers,
            upcoming_events=[]  # TODO: Implement events tracking
        )
        
    except Exception as e:
        logger.error(f"Error generating EOD report: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monthly", response_model=MonthlyReportResponse)
async def get_monthly_report(
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """Generate monthly performance report."""
    try:
        # Parse month or use current
        if month:
            year, month_num = map(int, month.split("-"))
            start_date = datetime(year, month_num, 1)
        else:
            now = datetime.utcnow()
            start_date = datetime(now.year, now.month, 1)
        
        # Calculate end date
        if start_date.month == 12:
            end_date = datetime(start_date.year + 1, 1, 1)
        else:
            end_date = datetime(start_date.year, start_date.month + 1, 1)
        
        # Get all trades for the month
        trades = db.query(TradeCard).filter(
            TradeCard.created_at >= start_date,
            TradeCard.created_at < end_date
        ).all()
        
        # Get closed positions
        closed_positions = db.query(Position).filter(
            Position.closed_at >= start_date,
            Position.closed_at < end_date
        ).all()
        
        # Calculate metrics
        total_trades = len(trades)
        winning_trades = len([p for p in closed_positions if (p.realized_pnl or 0) > 0])
        losing_trades = len([p for p in closed_positions if (p.realized_pnl or 0) < 0])
        
        win_rate = (winning_trades / len(closed_positions) * 100) if closed_positions else 0.0
        
        total_pnl = sum(p.realized_pnl or 0 for p in closed_positions)
        
        # Max drawdown (simplified)
        pnls = [p.realized_pnl or 0 for p in closed_positions]
        cumulative = []
        running_sum = 0
        for pnl in pnls:
            running_sum += pnl
            cumulative.append(running_sum)
        
        if cumulative:
            peak = cumulative[0]
            max_dd = 0
            for val in cumulative:
                if val > peak:
                    peak = val
                dd = peak - val
                if dd > max_dd:
                    max_dd = dd
        else:
            max_dd = 0
        
        # Strategy performance
        strategy_performance = {}
        for strategy in ["momentum", "mean_reversion"]:
            strategy_trades = [t for t in trades if t.strategy == strategy]
            strategy_performance[strategy] = {
                "total": len(strategy_trades),
                "avg_confidence": sum(t.confidence or 0 for t in strategy_trades) / len(strategy_trades) if strategy_trades else 0
            }
        
        # Compliance summary
        compliance_summary = {
            "total_checks": len(trades),
            "passed": len([t for t in trades if t.status != "rejected"]),
            "failed": len([t for t in trades if t.status == "rejected"])
        }
        
        # Best and worst trades
        if closed_positions:
            best_trade = max(closed_positions, key=lambda p: p.realized_pnl or 0)
            worst_trade = min(closed_positions, key=lambda p: p.realized_pnl or 0)
            
            best_trade_dict = {
                "symbol": best_trade.symbol,
                "pnl": best_trade.realized_pnl,
                "opened_at": best_trade.opened_at.isoformat()
            }
            worst_trade_dict = {
                "symbol": worst_trade.symbol,
                "pnl": worst_trade.realized_pnl,
                "opened_at": worst_trade.opened_at.isoformat()
            }
        else:
            best_trade_dict = None
            worst_trade_dict = None
        
        return MonthlyReportResponse(
            month=start_date.strftime("%Y-%m"),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=round(win_rate, 2),
            total_pnl=round(total_pnl, 2),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=None,  # TODO: Calculate Sharpe ratio
            strategy_performance=strategy_performance,
            compliance_summary=compliance_summary,
            best_trade=best_trade_dict,
            worst_trade=worst_trade_dict
        )
        
    except Exception as e:
        logger.error(f"Error generating monthly report: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

