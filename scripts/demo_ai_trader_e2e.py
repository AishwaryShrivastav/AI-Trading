"""End-to-End Demo: Multi-Account AI Trader - Complete Workflow."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal, Account, Signal, TradeCardV2
from backend.app.services.trade_card_pipeline_v2 import TradeCardPipelineV2
from backend.app.services.treasury import Treasury
from backend.app.services.risk_monitor import RiskMonitor
from backend.app.services.playbook_manager import PlaybookManager
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def print_header(text, char="="):
    """Print section header."""
    print("\n" + char * 80)
    print(f"  {text}")
    print(char * 80)


async def demo_complete_workflow():
    """
    Complete AI Trader workflow demonstration.
    
    Shows:
    1. Multi-account setup (from Phase 1 demo)
    2. Data ingestion
    3. Feature building
    4. Signal generation
    5. Per-account allocation
    6. Trade card creation
    7. Approval and execution
    8. Risk monitoring
    """
    
    print_header("🤖 MULTI-ACCOUNT AI TRADER - END-TO-END DEMO")
    
    print("\n  This demo showcases the complete workflow:")
    print("    1️⃣  Accounts with different mandates")
    print("    2️⃣  Data ingestion (events, features)")
    print("    3️⃣  Signal generation with meta-labeling")
    print("    4️⃣  Per-account allocation")
    print("    5️⃣  Trade card generation")
    print("    6️⃣  Approval workflow")
    print("    7️⃣  Risk monitoring & kill switches")
    print("    8️⃣  Treasury management")
    
    db = SessionLocal()
    
    try:
        # ====================================================================
        # STEP 1: Verify Accounts Setup
        # ====================================================================
        print_header("STEP 1: Verify Multi-Account Setup")
        
        accounts = db.query(Account).filter(Account.user_id == "demo_user").all()
        
        if not accounts:
            print("  ⚠️  No accounts found. Run demo_multi_account.py first!")
            print("  Running: python scripts/demo_multi_account.py")
            return
        
        print(f"\n  ✅ Found {len(accounts)} accounts:\n")
        
        for acc in accounts:
            print(f"    • {acc.name} ({acc.account_type})")
        
        # ====================================================================
        # STEP 2: Initialize Components
        # ====================================================================
        print_header("STEP 2: Initialize AI Trader Components")
        
        pipeline = TradeCardPipelineV2(db)
        treasury = Treasury(db)
        risk_monitor = RiskMonitor(db)
        playbook_mgr = PlaybookManager(db)
        
        print("\n  ✅ Initialized:")
        print("    • Pipeline Orchestrator")
        print("    • Treasury Manager")
        print("    • Risk Monitor")
        print("    • Playbook Manager")
        
        # ====================================================================
        # STEP 3: Treasury Summary
        # ====================================================================
        print_header("STEP 3: Treasury - Portfolio Capital Summary")
        
        treasury_summary = await treasury.get_portfolio_summary()
        
        print(f"\n  💰 Portfolio Capital:")
        print(f"    • Total Capital: ₹{treasury_summary['total_capital']:,.0f}")
        print(f"    • Available: ₹{treasury_summary['total_available']:,.0f}")
        print(f"    • Deployed: ₹{treasury_summary['total_deployed']:,.0f}")
        print(f"    • Reserved: ₹{treasury_summary['total_reserved']:,.0f}")
        print(f"    • Utilization: {treasury_summary['utilization_percent']:.1f}%")
        print(f"    • Accounts: {treasury_summary['accounts_count']}")
        
        # ====================================================================
        # STEP 4: Run Complete Pipeline
        # ====================================================================
        print_header("STEP 4: Run AI Trading Pipeline")
        
        print("\n  🔄 Running pipeline for 5 symbols...")
        print("    (Ingestion → Features → Signals → Allocation → Trade Cards)")
        
        symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
        
        result = await pipeline.run_full_pipeline(
            symbols=symbols,
            user_id="demo_user"
        )
        
        print(f"\n  ✅ Pipeline Complete:")
        print(f"    • Events Ingested: {result['events_ingested']}")
        print(f"    • Features Built: {result['features_built']}")
        print(f"    • Signals Generated: {result['signals_generated']}")
        print(f"    • High-Quality Signals: {result['high_quality_signals']}")
        print(f"    • Accounts Processed: {result['accounts_processed']}")
        
        # ====================================================================
        # STEP 5: View Trade Cards Per Account
        # ====================================================================
        print_header("STEP 5: Trade Cards Generated Per Account")
        
        results_by_account = result.get('results_by_account', {})
        
        total_cards = 0
        for account_name, account_result in results_by_account.items():
            cards_count = account_result.get('cards_created', 0)
            total_cards += cards_count
            
            print(f"\n  📋 {account_name}:")
            print(f"    • Opportunities Found: {account_result.get('opportunities_found', 0)}")
            print(f"    • Cards Created: {cards_count}")
            
            if cards_count > 0:
                cards = account_result.get('cards', [])
                for i, card in enumerate(cards[:3], 1):  # Show first 3
                    print(f"      {i}. {card['symbol']} {card['direction']} (confidence: {card['confidence']:.0%})")
        
        print(f"\n  ✅ Total Trade Cards Created: {total_cards}")
        
        # ====================================================================
        # STEP 6: View Pending Approvals
        # ====================================================================
        print_header("STEP 6: Pending Trade Cards (Approval Queue)")
        
        pending_cards = db.query(TradeCardV2).filter(
            TradeCardV2.status == "PENDING"
        ).order_by(TradeCardV2.priority.desc()).all()
        
        if pending_cards:
            print(f"\n  📨 {len(pending_cards)} trade cards awaiting approval:\n")
            
            for i, card in enumerate(pending_cards[:5], 1):
                account = db.query(Account).filter(Account.id == card.account_id).first()
                
                print(f"    {i}. [{account.name}] {card.symbol} {card.direction}")
                print(f"       Entry: ₹{card.entry_price:.2f} × {card.quantity} = ₹{card.position_size_rupees:,.0f}")
                print(f"       SL: ₹{card.stop_loss:.2f} | TP: ₹{card.take_profit:.2f}")
                print(f"       Risk: ₹{card.risk_amount:,.0f} | Reward: ₹{card.reward_amount:,.0f}")
                print(f"       R:R = 1:{card.risk_reward_ratio:.1f}")
                print(f"       Confidence: {card.confidence:.0%} | Edge: {card.edge:.1f}%")
                print(f"       Priority: {card.priority} | Status: {card.status}")
                print(f"       Thesis: {card.thesis[:100]}...")
                print()
        else:
            print("\n  ℹ️  No pending trade cards")
        
        # ====================================================================
        # STEP 7: Risk Monitoring
        # ====================================================================
        print_header("STEP 7: Risk Monitoring & Kill Switches")
        
        metrics = await risk_monitor.get_risk_metrics()
        
        print(f"\n  🛡️  Portfolio Risk Metrics:")
        print(f"    • Total Capital: ₹{metrics['total_capital']:,.0f}")
        print(f"    • Open Risk: ₹{metrics['open_risk']:,.0f} ({metrics['open_risk_percent']:.1f}%)")
        print(f"    • Unrealized P&L: ₹{metrics['unrealized_pnl']:,.0f}")
        print(f"    • Open Positions: {metrics['open_positions']}")
        print(f"    • Daily P&L: ₹{metrics['daily_pnl']:,.0f}")
        print(f"    • Trading Paused: {metrics['is_paused']}")
        
        # Check kill switches
        triggered = await risk_monitor.check_kill_switches()
        
        if triggered:
            print(f"\n  ⚠️  {len(triggered)} kill switches triggered!")
            for switch in triggered:
                print(f"    • {switch['switch_type']}: {switch['message']}")
        else:
            print(f"\n  ✅ All kill switches OK")
        
        # ====================================================================
        # STEP 8: Demonstrate Approval
        # ====================================================================
        print_header("STEP 8: Approval Workflow (Simulation)")
        
        if pending_cards:
            card_to_approve = pending_cards[0]
            account = db.query(Account).filter(Account.id == card_to_approve.account_id).first()
            
            print(f"\n  👤 User reviews card #{card_to_approve.id}:")
            print(f"    Account: {account.name}")
            print(f"    Signal: {card_to_approve.symbol} {card_to_approve.direction}")
            print(f"    Investment: ₹{card_to_approve.position_size_rupees:,.0f}")
            print(f"    Risk/Reward: 1:{card_to_approve.risk_reward_ratio:.1f}")
            print(f"    Confidence: {card_to_approve.confidence:.0%}")
            
            print("\n  💡 User decision: APPROVE (simulated)")
            
            # Simulate approval (reserve cash)
            reserved = await treasury.reserve_cash(
                account_id=card_to_approve.account_id,
                amount=card_to_approve.position_size_rupees
            )
            
            if reserved:
                card_to_approve.status = "APPROVED"
                card_to_approve.approved_at = datetime.utcnow()
                card_to_approve.approved_by = "demo_user"
                db.commit()
                
                print(f"  ✅ Approved! Cash reserved: ₹{card_to_approve.position_size_rupees:,.0f}")
            else:
                print(f"  ❌ Cannot approve: Insufficient cash")
        else:
            print("\n  ℹ️  No cards to approve")
        
        # ====================================================================
        # STEP 9: Hot Path Demonstration
        # ====================================================================
        print_header("STEP 9: Hot Path - Breaking News Simulation")
        
        print("\n  🚨 Simulating: Breaking news event detected")
        print("    Event: RELIANCE announces major buyback")
        
        # Create mock high-priority event
        from backend.app.database import Event
        
        event = Event(
            source="NEWS_BREAKING",
            source_url="https://example.com/reliance-buyback",
            raw_content="Reliance Industries announces ₹10,000 crore buyback program",
            event_type="BUYBACK",
            priority="HIGH",
            symbols=["RELIANCE"],
            event_timestamp=datetime.utcnow(),
            processing_status="PENDING"
        )
        
        db.add(event)
        db.commit()
        db.refresh(event)
        
        print(f"  📥 Event ingested (ID: {event.id})")
        print("\n  ⚡ Hot path activated...")
        
        hot_result = await pipeline.run_hot_path(event_id=event.id)
        
        print(f"\n  ✅ Hot Path Complete:")
        print(f"    • Cards Created: {hot_result['cards_created']}")
        print(f"    • Accounts Notified: {hot_result.get('accounts_notified', 0)}")
        print(f"    • Latency: {hot_result.get('latency_ms', 0)}ms")
        
        # ====================================================================
        # SUMMARY
        # ====================================================================
        print_header("📊 DEMO SUMMARY", "=")
        
        print("\n  ✅ Demonstrated Complete AI Trader Workflow:")
        print("    1. ✅ Multi-account structure (3 accounts)")
        print("    2. ✅ Data ingestion (events, features)")
        print("    3. ✅ Signal generation (momentum, events)")
        print("    4. ✅ Meta-labeling (quality filtering)")
        print("    5. ✅ Per-account allocation (mandate-based)")
        print("    6. ✅ Trade card generation (with thesis)")
        print("    7. ✅ Approval workflow (manual control)")
        print("    8. ✅ Treasury management (cash tracking)")
        print("    9. ✅ Risk monitoring (kill switches)")
        print("   10. ✅ Hot path (breaking news → cards)")
        
        print("\n  📈 Results:")
        print(f"    • Accounts: {len(accounts)}")
        print(f"    • Trade Cards Created: {total_cards}")
        print(f"    • Pending Approvals: {len(pending_cards)}")
        print(f"    • Portfolio Capital: ₹{treasury_summary['total_capital']:,.0f}")
        
        print("\n  🎯 Next Steps:")
        print("    1. Review pending trade cards")
        print("    2. Approve high-confidence opportunities")
        print("    3. Execute via Upstox integration")
        print("    4. Monitor positions and P&L")
        print("    5. Review EOD reports")
        
        print("\n  🚀 To use via API:")
        print("    • Start: uvicorn backend.app.main:app --reload")
        print("    • Docs: http://localhost:8000/docs")
        print("    • Test: /api/ai-trader/pipeline/run")
        
        print("\n  📚 Documentation:")
        print("    • AI_TRADER_ARCHITECTURE.md - System design")
        print("    • AI_TRADER_PHASE1_COMPLETE.md - Phase 1 summary")
        print("    • UPSTOX_INTEGRATION_GUIDE.md - Broker integration")
        
    finally:
        db.close()


async def run_quick_test():
    """Quick test of all components."""
    print_header("🧪 QUICK COMPONENT TEST")
    
    db = SessionLocal()
    
    try:
        # Test 1: Treasury
        print("\n  1. Testing Treasury...")
        treasury = Treasury(db)
        summary = await treasury.get_portfolio_summary()
        print(f"    ✅ Treasury OK - Total Capital: ₹{summary['total_capital']:,.0f}")
        
        # Test 2: Risk Monitor
        print("\n  2. Testing Risk Monitor...")
        monitor = RiskMonitor(db)
        metrics = await monitor.get_risk_metrics()
        print(f"    ✅ Risk Monitor OK - Open Positions: {metrics['open_positions']}")
        
        # Test 3: Playbook Manager
        print("\n  3. Testing Playbook Manager...")
        playbook_mgr = PlaybookManager(db)
        from backend.app.database import Playbook
        playbooks = db.query(Playbook).count()
        print(f"    ✅ Playbook Manager OK - {playbooks} playbooks loaded")
        
        # Test 4: Pipeline
        print("\n  4. Testing Pipeline...")
        pipeline = TradeCardPipelineV2(db)
        print(f"    ✅ Pipeline OK - Components initialized")
        
        print("\n  ✅ All components operational!")
        
    finally:
        db.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI Trader End-to-End Demo")
    parser.add_argument("--quick", action="store_true", help="Run quick test only")
    args = parser.parse_args()
    
    try:
        if args.quick:
            asyncio.run(run_quick_test())
        else:
            asyncio.run(demo_complete_workflow())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    from datetime import datetime
    main()

