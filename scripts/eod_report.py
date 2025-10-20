"""End-of-day report generation script."""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime, date
from backend.app.database import SessionLocal, TradeCard, Order, Position
from sqlalchemy import func

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_eod_report(report_date=None):
    """Generate end-of-day report."""
    db = SessionLocal()
    
    try:
        if report_date is None:
            report_date = date.today()
        elif isinstance(report_date, str):
            report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
        
        logger.info("=" * 70)
        logger.info(f"END-OF-DAY REPORT - {report_date.strftime('%Y-%m-%d')}")
        logger.info("=" * 70)
        
        # Get trade cards created today
        trades_created = db.query(TradeCard).filter(
            func.date(TradeCard.created_at) == report_date
        ).all()
        
        # Get trade cards approved/rejected today
        trades_approved = db.query(TradeCard).filter(
            func.date(TradeCard.approved_at) == report_date
        ).count()
        
        trades_rejected = db.query(TradeCard).filter(
            func.date(TradeCard.rejected_at) == report_date
        ).count()
        
        # Get orders placed today
        orders_placed = db.query(Order).filter(
            func.date(Order.placed_at) == report_date
        ).all()
        
        # Get current positions
        open_positions = db.query(Position).filter(
            Position.closed_at.is_(None)
        ).all()
        
        # Get positions closed today
        closed_positions = db.query(Position).filter(
            func.date(Position.closed_at) == report_date
        ).all()
        
        # Calculate P&L
        realized_pnl = sum(p.realized_pnl or 0 for p in closed_positions)
        unrealized_pnl = sum(p.unrealized_pnl or 0 for p in open_positions)
        total_pnl = realized_pnl + unrealized_pnl
        
        # Print report
        print("\n" + "=" * 70)
        print("TRADE CARD ACTIVITY")
        print("=" * 70)
        print(f"  Trade cards created: {len(trades_created)}")
        print(f"  Trade cards approved: {trades_approved}")
        print(f"  Trade cards rejected: {trades_rejected}")
        print(f"  Pending approval: {len([t for t in trades_created if t.status == 'pending_approval'])}")
        
        print("\n" + "=" * 70)
        print("ORDERS")
        print("=" * 70)
        print(f"  Orders placed: {len(orders_placed)}")
        for order in orders_placed:
            print(f"    • {order.symbol} - {order.transaction_type} {order.quantity} @ ₹{order.price}")
        
        print("\n" + "=" * 70)
        print("POSITIONS")
        print("=" * 70)
        print(f"  Open positions: {len(open_positions)}")
        print(f"  Closed positions: {len(closed_positions)}")
        
        if open_positions:
            print("\n  Open Positions:")
            for pos in open_positions:
                print(f"    • {pos.symbol}: {pos.quantity} @ ₹{pos.average_price:.2f} | P&L: ₹{pos.unrealized_pnl or 0:.2f}")
        
        if closed_positions:
            print("\n  Closed Positions:")
            for pos in closed_positions:
                print(f"    • {pos.symbol}: P&L: ₹{pos.realized_pnl or 0:.2f}")
        
        print("\n" + "=" * 70)
        print("P&L SUMMARY")
        print("=" * 70)
        print(f"  Realized P&L:   ₹{realized_pnl:>12.2f}")
        print(f"  Unrealized P&L: ₹{unrealized_pnl:>12.2f}")
        print(f"  Total P&L:      ₹{total_pnl:>12.2f}")
        
        # Win rate for closed positions
        if closed_positions:
            winning = len([p for p in closed_positions if (p.realized_pnl or 0) > 0])
            win_rate = (winning / len(closed_positions)) * 100
            print(f"  Win Rate:       {win_rate:>12.1f}%")
        
        print("\n" + "=" * 70)
        print("RISK COMPLIANCE")
        print("=" * 70)
        
        # Check risk warnings
        liquidity_fails = len([t for t in trades_created if not t.liquidity_check])
        position_size_fails = len([t for t in trades_created if not t.position_size_check])
        exposure_fails = len([t for t in trades_created if not t.exposure_check])
        
        print(f"  Liquidity check failures:     {liquidity_fails}")
        print(f"  Position size check failures: {position_size_fails}")
        print(f"  Exposure check failures:      {exposure_fails}")
        
        if trades_created:
            compliance_rate = ((len(trades_created) - liquidity_fails - position_size_fails) / len(trades_created)) * 100
            print(f"  Overall compliance rate:      {compliance_rate:.1f}%")
        
        print("\n" + "=" * 70)
        print("STRATEGY BREAKDOWN")
        print("=" * 70)
        
        strategies = {}
        for trade in trades_created:
            strategy = trade.strategy or "unknown"
            if strategy not in strategies:
                strategies[strategy] = {"count": 0, "avg_confidence": []}
            strategies[strategy]["count"] += 1
            if trade.confidence:
                strategies[strategy]["avg_confidence"].append(trade.confidence)
        
        for strategy, data in strategies.items():
            avg_conf = sum(data["avg_confidence"]) / len(data["avg_confidence"]) if data["avg_confidence"] else 0
            print(f"  {strategy.upper()}: {data['count']} trades, avg confidence: {avg_conf * 100:.1f}%")
        
        print("\n" + "=" * 70)
        print(f"Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70 + "\n")
        
        logger.info("EOD report generated successfully")
        
    except Exception as e:
        logger.error(f"Failed to generate EOD report: {e}", exc_info=True)
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    import sys
    
    # Allow passing date as argument
    report_date = sys.argv[1] if len(sys.argv) > 1 else None
    
    try:
        generate_eod_report(report_date)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

