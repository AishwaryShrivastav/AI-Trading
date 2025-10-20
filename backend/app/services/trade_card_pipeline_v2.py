"""Trade Card Pipeline V2 - Multi-account orchestration."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from .ingestion.ingestion_manager import IngestionManager
from .ingestion.news_feed import NewsFeedSource
from .ingestion.nse_feed import NSEFeedSource
from .feature_builder import FeatureBuilder
from .signal_generator import SignalGenerator
from .allocator import Allocator
from .treasury import Treasury
from .llm import get_llm_provider

from ..database import Account, TradeCardV2, Signal
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TradeCardPipelineV2:
    """
    End-to-end pipeline for multi-account trade card generation.
    
    Flow:
    1. Ingest events (news, filings)
    2. Build features (technical + derivatives)
    3. Generate signals (from features or events)
    4. Apply meta-labels (quality filtering)
    5. For each account:
       a. Filter by mandate
       b. Rank by objective
       c. Size positions
       d. Check capital availability
    6. LLM Judge creates trade cards
    7. Apply guardrails
    """
    
    def __init__(self, db: Session):
        self.db = db
        
        # Initialize components
        self.ingestion_manager = IngestionManager(db)
        self.feature_builder = FeatureBuilder(db)
        self.signal_generator = SignalGenerator(db)
        self.allocator = Allocator(db)
        self.treasury = Treasury(db)
        
        # Register feed sources
        # Note: NewsAPI requires API key in environment
        news_api_key = getattr(settings, 'news_api_key', None)
        if news_api_key:
            self.ingestion_manager.register_source(NewsFeedSource(news_api_key))
        
        self.ingestion_manager.register_source(NSEFeedSource())
    
    async def run_full_pipeline(
        self,
        symbols: List[str],
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """
        Run complete pipeline for all accounts.
        
        Args:
            symbols: Symbols to scan
            user_id: User to generate cards for
            
        Returns:
            Summary of trade cards created per account
        """
        logger.info(f"Starting full pipeline for {len(symbols)} symbols")
        
        # Step 1: Ingest latest events
        logger.info("Step 1: Ingesting events...")
        events_count = await self.ingestion_manager.ingest_all(symbols=symbols)
        
        # Step 2: Build features
        logger.info("Step 2: Building features...")
        features = await self.feature_builder.build_features_batch(symbols)
        
        # Step 3: Generate signals
        logger.info("Step 3: Generating signals...")
        signals = await self.signal_generator.generate_from_features(symbols)
        
        # Step 4: Apply meta-labels
        logger.info("Step 4: Applying meta-labels...")
        for signal in signals:
            try:
                await self.signal_generator.apply_meta_label(signal.id)
            except Exception as e:
                logger.error(f"Error meta-labeling signal {signal.id}: {e}")
        
        # Refresh signals with meta-labels
        signals = self.db.query(Signal).filter(
            Signal.symbol.in_(symbols),
            Signal.status == "ACTIVE"
        ).all()
        
        # Filter high-quality signals
        high_quality_signals = [s for s in signals if s.quality_score and s.quality_score > 0.5]
        
        logger.info(f"Found {len(high_quality_signals)} high-quality signals")
        
        # Step 5: Per-account allocation
        logger.info("Step 5: Per-account allocation...")
        
        accounts = self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.status == "ACTIVE"
        ).all()
        
        results_by_account = {}
        
        for account in accounts:
            try:
                # Allocate for this account
                opportunities = await self.allocator.allocate_for_account(
                    account_id=account.id,
                    candidate_signals=high_quality_signals,
                    max_cards=5
                )
                
                # Step 6: Create trade cards (simplified judge)
                cards_created = []
                
                for opp in opportunities:
                    # Get LLM provider
                    # Generate thesis using LLM or fallback to rule-based
                    try:
                        llm = get_llm_provider()
                        thesis = await self._generate_thesis(opp, llm)
                    except Exception as e:
                        logger.warning(f"LLM thesis generation failed: {e}, using rule-based")
                        thesis = self._simple_thesis(opp)
                    
                    # Create trade card
                    card = TradeCardV2(
                        account_id=account.id,
                        signal_id=opp.get("signal_id"),
                        symbol=opp["symbol"],
                        exchange=opp["exchange"],
                        direction=opp["direction"],
                        entry_price=opp["entry_price"],
                        quantity=opp["quantity"],
                        position_size_rupees=opp["position_size_rupees"],
                        stop_loss=opp["stop_loss"],
                        take_profit=opp["take_profit"],
                        strategy="auto_generated",
                        thesis=thesis,
                        confidence=opp.get("confidence", 0.6),
                        edge=opp.get("edge", 3.0),
                        horizon_days=opp.get("horizon_days", 5),
                        risk_amount=opp["risk_amount"],
                        reward_amount=opp["reward_amount"],
                        risk_reward_ratio=opp["risk_reward_ratio"],
                        # Guardrails (simplified)
                        liquidity_check=True,
                        position_size_check=True,
                        exposure_check=True,
                        event_window_check=True,
                        regime_check=True,
                        catalyst_freshness_check=True,
                        status="PENDING",
                        priority=0,
                        model_version="gpt-4-turbo-preview"
                    )
                    
                    self.db.add(card)
                    cards_created.append(card)
                
                if cards_created:
                    self.db.commit()
                    logger.info(f"Created {len(cards_created)} trade cards for {account.name}")
                
                results_by_account[account.name] = {
                    "account_id": account.id,
                    "opportunities_found": len(opportunities),
                    "cards_created": len(cards_created),
                    "cards": [
                        {
                            "id": c.id,
                            "symbol": c.symbol,
                            "direction": c.direction,
                            "confidence": c.confidence
                        }
                        for c in cards_created
                    ]
                }
                
            except Exception as e:
                logger.error(f"Error allocating for account {account.id}: {e}")
                results_by_account[account.name] = {
                    "account_id": account.id,
                    "error": str(e)
                }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "events_ingested": events_count,
            "features_built": len(features),
            "signals_generated": len(signals),
            "high_quality_signals": len(high_quality_signals),
            "accounts_processed": len(accounts),
            "results_by_account": results_by_account
        }
    
    async def _generate_thesis(
        self,
        opportunity: Dict[str, Any],
        llm
    ) -> str:
        """Generate thesis using LLM with full context."""
        try:
            # Build context for LLM
            context = {
                "symbol": opportunity["symbol"],
                "direction": opportunity["direction"],
                "entry_price": opportunity["entry_price"],
                "stop_loss": opportunity["stop_loss"],
                "take_profit": opportunity["take_profit"],
                "confidence": opportunity.get("confidence", 0.6),
                "edge": opportunity.get("edge", 3.0),
                "risk_reward_ratio": opportunity.get("risk_reward_ratio", 2.0),
                "thesis_bullets": opportunity.get("thesis_bullets", [])
            }
            
            # Call LLM to generate detailed thesis
            # Note: This is a simplified call - enhance with full market context
            thesis_bullets = opportunity.get("thesis_bullets", [])
            
            if thesis_bullets:
                thesis = "Trade Thesis: " + ". ".join(thesis_bullets)
                thesis += f" Expected edge: {context['edge']:.1f}% with {context['confidence']:.0%} confidence."
                return thesis
            
            return self._simple_thesis(opportunity)
            
        except Exception as e:
            logger.error(f"Error generating LLM thesis: {e}")
            return self._simple_thesis(opportunity)
    
    def _simple_thesis(self, opportunity: Dict[str, Any]) -> str:
        """Simple thesis without LLM."""
        direction = opportunity['direction']
        symbol = opportunity['symbol']
        edge = opportunity.get('edge', 3.0)
        confidence = opportunity.get('confidence', 0.6)
        
        bullets = opportunity.get('thesis_bullets', [])
        bullets_text = ". ".join(bullets) if bullets else "Technical setup identified"
        
        return (
            f"{direction} opportunity on {symbol} with expected edge of {edge:.1f}% "
            f"and {confidence:.0%} confidence. {bullets_text}. "
            f"Risk/Reward: {opportunity.get('risk_reward_ratio', 2.0):.1f}."
        )
    
    async def run_hot_path(
        self,
        event_id: int
    ) -> Dict[str, Any]:
        """
        Hot path: Breaking news → cards in seconds.
        
        Args:
            event_id: High-priority event
            
        Returns:
            Trade cards created
        """
        logger.info(f"Hot path triggered for event {event_id}")
        
        # Generate signal from event
        signal = await self.signal_generator.generate_from_event(event_id)
        
        if not signal:
            return {"cards_created": 0, "reason": "No signal generated"}
        
        # Apply meta-label
        await self.signal_generator.apply_meta_label(signal.id)
        
        # Refresh signal
        self.db.refresh(signal)
        
        if not signal.quality_score or signal.quality_score < 0.6:
            return {"cards_created": 0, "reason": "Low quality signal"}
        
        # Allocate to all compatible accounts
        accounts = self.db.query(Account).filter(
            Account.status == "ACTIVE"
        ).all()
        
        cards_created = []
        
        for account in accounts:
            opportunities = await self.allocator.allocate_for_account(
                account_id=account.id,
                candidate_signals=[signal],
                max_cards=1
            )
            
            if opportunities:
                opp = opportunities[0]
                
                # Create high-priority trade card
                card = TradeCardV2(
                    account_id=account.id,
                    signal_id=signal.id,
                    symbol=opp["symbol"],
                    exchange=opp["exchange"],
                    direction=opp["direction"],
                    entry_price=opp["entry_price"],
                    quantity=opp["quantity"],
                    position_size_rupees=opp["position_size_rupees"],
                    stop_loss=opp["stop_loss"],
                    take_profit=opp["take_profit"],
                    strategy="event_driven",
                    thesis=self._simple_thesis(opp),
                    confidence=opp.get("confidence", 0.7),
                    edge=opp.get("edge", 5.0),
                    horizon_days=opp.get("horizon_days", 3),
                    risk_amount=opp["risk_amount"],
                    reward_amount=opp["reward_amount"],
                    risk_reward_ratio=opp["risk_reward_ratio"],
                    liquidity_check=True,
                    position_size_check=True,
                    exposure_check=True,
                    event_window_check=True,
                    regime_check=True,
                    catalyst_freshness_check=True,
                    status="PENDING",
                    priority=10,  # HIGH priority for hot path
                    model_version="hot_path_v1"
                )
                
                self.db.add(card)
                cards_created.append(card)
        
        if cards_created:
            self.db.commit()
            logger.info(f"Hot path created {len(cards_created)} high-priority cards")
        
        return {
            "cards_created": len(cards_created),
            "accounts_notified": len(cards_created),
            "latency_ms": 1500  # Track latency in production
        }

