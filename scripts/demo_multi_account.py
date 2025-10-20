"""Demo script for Multi-Account AI Trader - Phase 1."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal, Account, Mandate, FundingPlan
from backend.app.services.intake_agent import intake_agent
from backend.app.schemas import (
    AccountType, IntakeAnswer, IntakeSessionCreate
)
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def print_header(text):
    """Print section header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


async def demo_intake_agent():
    """Demo: Conversational Intake Agent."""
    print_header("DEMO: INTAKE AGENT - Conversational Mandate Capture")
    
    print("\n📋 Scenario: Setting up an aggressive SIP account")
    print("   Account Name: SIP—Aggressive (24m)")
    print("   Type: SIP")
    
    # Start session
    print("\n1️⃣  Starting intake session...")
    session = intake_agent.start_session(
        account_name="SIP—Aggressive (24m)",
        account_type=AccountType.SIP,
        user_id="demo_user"
    )
    
    print(f"   ✅ Session started: {session.session_id}")
    print(f"   📊 Total questions: {session.total_questions}")
    
    # Answer questions
    answers_demo = {
        "objective": "MAX_PROFIT",
        "risk_per_trade_percent": 2.0,
        "max_positions": 8,
        "horizon": "3-7",
        "banned_sectors": "none",
        "liquidity_floor_adv": 1500000,
        "sip_amount": 15000,
        "sip_frequency": "MONTHLY",
        "sip_duration_months": 24
    }
    
    print(f"\n2️⃣  Answering {len(answers_demo)} questions...")
    
    for i, (question_id, answer_value) in enumerate(answers_demo.items(), 1):
        # Get current question
        current_q = session.current_question
        
        print(f"\n   Q{i}: {current_q.question_text}")
        print(f"   💬 Answer: {answer_value}")
        
        # Submit answer
        answer = IntakeAnswer(
            question_id=current_q.question_id,
            answer=answer_value
        )
        
        session = intake_agent.answer_question(session.session_id, answer)
        
        if session.is_complete:
            break
    
    # Generate mandate and plan
    print("\n3️⃣  Generating mandate and funding plan...")
    result = intake_agent.generate_mandate_and_plan(session.session_id)
    
    print("\n   ✅ Mandate Generated:")
    mandate = result["mandate_data"]
    print(f"      • Objective: {mandate['objective']}")
    print(f"      • Risk per trade: {mandate['risk_per_trade_percent']}%")
    print(f"      • Max positions: {mandate['max_positions']}")
    print(f"      • Horizon: {mandate['horizon_min_days']}-{mandate['horizon_max_days']} days")
    
    print("\n   ✅ Funding Plan Generated:")
    plan = result["funding_plan_data"]
    print(f"      • Type: {plan['funding_type']}")
    print(f"      • SIP Amount: ₹{plan['sip_amount']:,.0f}")
    print(f"      • Frequency: {plan['sip_frequency']}")
    print(f"      • Duration: {plan['sip_duration_months']} months")
    print(f"      • Available Cash: ₹{plan['available_cash']:,.0f}")
    
    print("\n   📝 Summary for Confirmation:")
    print(f"      {result['summary']}")
    
    # Clean up
    intake_agent.clear_session(session.session_id)
    
    return result


async def demo_create_multiple_accounts():
    """Demo: Creating multiple accounts with different strategies."""
    print_header("DEMO: MULTIPLE ACCOUNTS - Different Strategies")
    
    db = SessionLocal()
    
    try:
        # Account 1: SIP Aggressive
        print("\n1️⃣  Creating Account 1: SIP—Aggressive (24m)")
        
        account1 = Account(
            user_id="demo_user",
            name="SIP—Aggressive (24m)",
            account_type="SIP",
            description="Aggressive growth SIP for long-term wealth creation",
            status="ACTIVE"
        )
        db.add(account1)
        db.flush()
        
        mandate1 = Mandate(
            account_id=account1.id,
            version=1,
            objective="MAX_PROFIT",
            risk_per_trade_percent=2.0,
            max_positions=8,
            max_sector_exposure_percent=30.0,
            horizon_min_days=3,
            horizon_max_days=7,
            banned_sectors=[],
            earnings_blackout_days=2,
            liquidity_floor_adv=1500000,
            min_market_cap=100.0,
            allowed_strategies=["momentum", "mean_reversion", "event_driven"],
            sl_multiplier=2.0,
            tp_multiplier=4.0,
            trailing_stop_enabled=False,
            summary="Aggressive SIP focused on maximizing returns through momentum and event-driven opportunities.",
            is_active=True
        )
        db.add(mandate1)
        
        funding1 = FundingPlan(
            account_id=account1.id,
            funding_type="SIP",
            sip_amount=15000,
            sip_frequency="MONTHLY",
            sip_start_date=datetime.utcnow(),
            sip_duration_months=24,
            carry_forward_enabled=True,
            max_carry_forward_percent=20.0,
            emergency_buffer_percent=5.0,
            total_deployed=0.0,
            available_cash=15000.0,  # First installment
            reserved_cash=0.0
        )
        db.add(funding1)
        
        print(f"   ✅ Created: {account1.name}")
        print(f"      • Objective: MAX_PROFIT")
        print(f"      • Risk/Trade: 2.0%")
        print(f"      • SIP: ₹15,000/month for 24 months")
        
        # Account 2: Lump Sum Conservative
        print("\n2️⃣  Creating Account 2: Lump-Sum—Conservative (4m)")
        
        account2 = Account(
            user_id="demo_user",
            name="Lump-Sum—Conservative (4m)",
            account_type="LUMP_SUM",
            description="Conservative lump sum deployment with capital preservation focus",
            status="ACTIVE"
        )
        db.add(account2)
        db.flush()
        
        mandate2 = Mandate(
            account_id=account2.id,
            version=1,
            objective="RISK_MINIMIZED",
            risk_per_trade_percent=1.0,
            max_positions=12,
            max_sector_exposure_percent=25.0,
            horizon_min_days=5,
            horizon_max_days=10,
            banned_sectors=["banking", "pharma"],
            earnings_blackout_days=3,
            liquidity_floor_adv=2000000,
            min_market_cap=500.0,
            allowed_strategies=["mean_reversion"],
            sl_multiplier=1.5,
            tp_multiplier=3.0,
            trailing_stop_enabled=True,
            summary="Conservative lump sum with focus on capital preservation and mean-reversion opportunities.",
            is_active=True
        )
        db.add(mandate2)
        
        funding2 = FundingPlan(
            account_id=account2.id,
            funding_type="LUMP_SUM",
            lump_sum_amount=500000,
            lump_sum_date=datetime.utcnow(),
            tranche_plan=[
                {"percent": 33, "trigger": "immediate", "delay_days": 0},
                {"percent": 33, "trigger": "time_based", "delay_days": 7},
                {"percent": 34, "trigger": "time_based", "delay_days": 14}
            ],
            carry_forward_enabled=True,
            max_carry_forward_percent=15.0,
            emergency_buffer_percent=10.0,
            total_deployed=0.0,
            available_cash=165000.0,  # First tranche (33%)
            reserved_cash=0.0
        )
        db.add(funding2)
        
        print(f"   ✅ Created: {account2.name}")
        print(f"      • Objective: RISK_MINIMIZED")
        print(f"      • Risk/Trade: 1.0%")
        print(f"      • Lump Sum: ₹5,00,000 (staged deployment)")
        print(f"      • Available Now: ₹1,65,000 (33%)")
        
        # Account 3: Event Tactical
        print("\n3️⃣  Creating Account 3: Event—Tactical")
        
        account3 = Account(
            user_id="demo_user",
            name="Event—Tactical",
            account_type="EVENT_TACTICAL",
            description="Opportunistic event-driven trading",
            status="ACTIVE"
        )
        db.add(account3)
        db.flush()
        
        mandate3 = Mandate(
            account_id=account3.id,
            version=1,
            objective="BALANCED",
            risk_per_trade_percent=1.5,
            max_positions=5,
            max_sector_exposure_percent=40.0,
            horizon_min_days=1,
            horizon_max_days=5,
            banned_sectors=[],
            earnings_blackout_days=0,  # Events often around earnings
            liquidity_floor_adv=5000000,  # High liquidity for quick exits
            min_market_cap=1000.0,
            allowed_strategies=["event_driven"],
            sl_multiplier=1.8,
            tp_multiplier=3.5,
            trailing_stop_enabled=False,
            summary="Tactical account for high-conviction event-driven opportunities with short holding periods.",
            is_active=True
        )
        db.add(mandate3)
        
        funding3 = FundingPlan(
            account_id=account3.id,
            funding_type="LUMP_SUM",
            lump_sum_amount=200000,
            lump_sum_date=datetime.utcnow(),
            tranche_plan=[{"percent": 100, "trigger": "event_based"}],
            carry_forward_enabled=True,
            max_carry_forward_percent=50.0,
            emergency_buffer_percent=10.0,
            total_deployed=0.0,
            available_cash=200000.0,  # All available for events
            reserved_cash=0.0
        )
        db.add(funding3)
        
        print(f"   ✅ Created: {account3.name}")
        print(f"      • Objective: BALANCED")
        print(f"      • Risk/Trade: 1.5%")
        print(f"      • Capital: ₹2,00,000 (event-based deployment)")
        print(f"      • Horizon: 1-5 days")
        
        db.commit()
        
        print("\n" + "=" * 70)
        print("✅ Successfully created 3 accounts with different strategies!")
        print("=" * 70)
        
        # Summary table
        print("\n📊 ACCOUNT SUMMARY:")
        print("\n   {:<30} {:<15} {:<20} {:<15}".format(
            "Account", "Type", "Objective", "Capital"
        ))
        print("   " + "-" * 80)
        print("   {:<30} {:<15} {:<20} ₹{:>14,}".format(
            account1.name, "SIP", "MAX_PROFIT", 15000
        ))
        print("   {:<30} {:<15} {:<20} ₹{:>14,}".format(
            account2.name, "LUMP_SUM", "RISK_MINIMIZED", 165000
        ))
        print("   {:<30} {:<15} {:<20} ₹{:>14,}".format(
            account3.name, "EVENT_TACTICAL", "BALANCED", 200000
        ))
        print("\n   Total Available Capital: ₹{:,}".format(15000 + 165000 + 200000))
        
        return [account1, account2, account3]
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating accounts: {e}")
        raise
    finally:
        db.close()


async def demo_intake_flow():
    """Demo: Complete intake flow for one account."""
    print_header("DEMO: INTAKE FLOW - Step-by-Step")
    
    print("\n📱 User wants to create: 'Balanced Growth SIP'")
    
    # Step 1: Start session
    print("\n1️⃣  Starting intake session...")
    session_create = IntakeSessionCreate(
        account_name="Balanced Growth SIP",
        account_type=AccountType.SIP,
        user_id="demo_user"
    )
    
    session = intake_agent.start_session(
        account_name=session_create.account_name,
        account_type=session_create.account_type,
        user_id=session_create.user_id
    )
    
    print(f"   ✅ Session: {session.session_id[:8]}...")
    print(f"   📊 Questions to ask: {session.total_questions}")
    
    # Step 2: Answer questions interactively
    print("\n2️⃣  Interactive Q&A...")
    
    demo_answers = [
        ("MAX_PROFIT", "Objective"),
        (1.5, "Risk per trade %"),
        (10, "Max positions"),
        ("3-7", "Horizon (days)"),
        ("none", "Banned sectors"),
        (1000000, "Liquidity floor"),
        (10000, "SIP amount"),
        ("MONTHLY", "SIP frequency"),
        (24, "SIP duration (months)")
    ]
    
    for i, (answer_value, description) in enumerate(demo_answers, 1):
        if session.is_complete:
            break
        
        question = session.current_question
        print(f"\n   Q{i}: {question.question_text}")
        
        if question.options:
            print(f"      Options: {', '.join(question.options)}")
        if question.default_value:
            print(f"      Default: {question.default_value}")
        
        print(f"   💬 User answers: {answer_value}")
        
        answer = IntakeAnswer(
            question_id=question.question_id,
            answer=answer_value
        )
        
        session = intake_agent.answer_question(session.session_id, answer)
        print(f"   ✅ Accepted ({session.answers_collected}/{session.total_questions} answered)")
    
    # Step 3: Generate summary
    print("\n3️⃣  Generating mandate and summary...")
    result = intake_agent.generate_mandate_and_plan(session.session_id)
    
    print("\n   📝 MANDATE SUMMARY:")
    print(f"   {result['summary']}")
    
    print("\n   💰 FUNDING DETAILS:")
    plan = result["funding_plan_data"]
    print(f"      • Monthly SIP: ₹{plan['sip_amount']:,.0f}")
    print(f"      • Duration: {plan['sip_duration_months']} months")
    print(f"      • Total Investment: ₹{plan['sip_amount'] * plan['sip_duration_months']:,.0f}")
    print(f"      • First Installment Available: ₹{plan['available_cash']:,.0f}")
    
    print("\n   ✅ User can now confirm and create the account!")
    
    # Clean up
    intake_agent.clear_session(session.session_id)
    
    return result


async def demo_view_accounts():
    """Demo: View created accounts."""
    print_header("DEMO: VIEW ACCOUNTS")
    
    db = SessionLocal()
    
    try:
        accounts = db.query(Account).filter(
            Account.user_id == "demo_user"
        ).all()
        
        if not accounts:
            print("\n   ℹ️  No accounts found. Run demo_create_multiple_accounts() first.")
            return
        
        print(f"\n   Found {len(accounts)} account(s):\n")
        
        for i, account in enumerate(accounts, 1):
            print(f"   {i}. {account.name}")
            print(f"      • ID: {account.id}")
            print(f"      • Type: {account.account_type}")
            print(f"      • Status: {account.status}")
            print(f"      • Created: {account.created_at.strftime('%Y-%m-%d %H:%M')}")
            
            # Get mandate
            mandate = db.query(Mandate).filter(
                Mandate.account_id == account.id,
                Mandate.is_active == True
            ).first()
            
            if mandate:
                print(f"      • Objective: {mandate.objective}")
                print(f"      • Risk/Trade: {mandate.risk_per_trade_percent}%")
                print(f"      • Max Positions: {mandate.max_positions}")
            
            # Get funding
            funding = db.query(FundingPlan).filter(
                FundingPlan.account_id == account.id
            ).first()
            
            if funding:
                print(f"      • Available Cash: ₹{funding.available_cash:,.0f}")
                print(f"      • Total Deployed: ₹{funding.total_deployed:,.0f}")
            
            print()
        
    finally:
        db.close()


async def run_all_demos():
    """Run all Phase 1 demos."""
    print("\n" + "=" * 70)
    print("  🤖 MULTI-ACCOUNT AI TRADER - PHASE 1 DEMO")
    print("=" * 70)
    print("\n  This demo showcases the foundation:")
    print("    • Multi-account structure")
    print("    • Conversational intake agent")
    print("    • Mandate and funding plan management")
    print("    • Per-account capital tracking")
    
    # Demo 1: Intake Agent
    await demo_intake_flow()
    
    # Demo 2: Create Multiple Accounts
    await demo_create_multiple_accounts()
    
    # Demo 3: View Accounts
    await demo_view_accounts()
    
    print("\n" + "=" * 70)
    print("  ✅ PHASE 1 DEMO COMPLETE!")
    print("=" * 70)
    
    print("\n  📚 What's Next:")
    print("    • Phase 2: Data ingestion (news, filings, market data)")
    print("    • Phase 3: Signal generation with meta-labeling")
    print("    • Phase 4: Per-account allocation")
    print("    • Phase 5: Execution with bracket orders")
    
    print("\n  🚀 To test via API:")
    print("    1. Start server: uvicorn backend.app.main:app --reload")
    print("    2. Visit: http://localhost:8000/docs")
    print("    3. Try /api/accounts endpoints")
    
    print("\n  📖 Documentation:")
    print("    • AI_TRADER_ARCHITECTURE.md - Complete system design")
    print("    • UPSTOX_INTEGRATION_GUIDE.md - Broker integration")


def main():
    """Main entry point."""
    try:
        asyncio.run(run_all_demos())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    from datetime import datetime
    main()

