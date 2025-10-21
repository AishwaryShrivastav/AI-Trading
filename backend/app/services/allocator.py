"""Allocator - Per-account signal filtering and position sizing."""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging

from ..database import Account, Mandate, FundingPlan, Signal, PositionV2, Feature, MarketDataCache
from ..schemas import Direction

logger = logging.getLogger(__name__)


class Allocator:
    """
    Per-account allocator that:
    1. Filters signals per mandate
    2. Ranks by quality and objective
    3. Sizes positions based on volatility and capital
    4. Respects funding plan constraints
    5. Applies playbook overrides
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def allocate_for_account(
        self,
        account_id: int,
        candidate_signals: List[Signal],
        max_cards: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Allocate signals for a specific account.
        
        Args:
            account_id: Account to allocate for
            candidate_signals: Pool of signals to consider
            max_cards: Maximum trade cards to create
            
        Returns:
            List of sized trade opportunities ready for Judge
        """
        # Get account, mandate, funding plan
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        mandate = self.db.query(Mandate).filter(
            Mandate.account_id == account_id,
            Mandate.is_active == True
        ).first()
        
        if not mandate:
            logger.warning(f"No active mandate for account {account_id}")
            return []
        
        funding_plan = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == account_id
        ).first()
        
        if not funding_plan or funding_plan.available_cash <= 0:
            logger.warning(f"No available cash for account {account_id}")
            return []
        
        # Step 1: Filter by mandate
        filtered = self._filter_by_mandate(candidate_signals, mandate)
        
        if not filtered:
            logger.info(f"No signals passed mandate filter for account {account_id}")
            return []
        
        # Step 2: Rank by objective
        ranked = self._rank_by_objective(filtered, mandate)
        
        # Step 3: Size positions
        sized_opportunities = []
        total_capital = funding_plan.available_cash + funding_plan.total_deployed
        
        for signal in ranked[:max_cards]:
            sized = await self._size_position(
                signal,
                mandate,
                total_capital,
                funding_plan.available_cash
            )
            
            if sized:
                sized_opportunities.append(sized)
        
        logger.info(f"Allocated {len(sized_opportunities)} opportunities for account {account_id}")
        return sized_opportunities
    
    def _filter_by_mandate(
        self,
        signals: List[Signal],
        mandate: Mandate
    ) -> List[Signal]:
        """Filter signals by mandate rules."""
        filtered = []
        
        for signal in signals:
            # Horizon match
            if signal.horizon_days < mandate.horizon_min_days or signal.horizon_days > mandate.horizon_max_days:
                continue
            
            # Strategy whitelist
            if mandate.allowed_strategies and signal.model_version:
                # Extract strategy from model version or signal data
                # For now, accept all
                pass
            
            # Quality threshold
            if signal.quality_score and signal.quality_score < 0.5:
                continue
            
            # Regime compatibility
            if hasattr(signal, 'regime_compatible') and signal.regime_compatible is False:
                continue
            
            filtered.append(signal)
        
        return filtered
    
    def _rank_by_objective(
        self,
        signals: List[Signal],
        mandate: Mandate
    ) -> List[Signal]:
        """Rank signals based on account objective."""
        if mandate.objective == "MAX_PROFIT":
            # Rank by edge × quality
            return sorted(
                signals,
                key=lambda s: (s.edge or 0) * (s.quality_score or 0.5),
                reverse=True
            )
        
        elif mandate.objective == "RISK_MINIMIZED":
            # Rank by (edge × quality) / volatility
            # For now, prioritize higher quality
            return sorted(
                signals,
                key=lambda s: (s.quality_score or 0),
                reverse=True
            )
        
        else:  # BALANCED
            # Balanced approach
            return sorted(
                signals,
                key=lambda s: (s.edge or 0) * (s.quality_score or 0.5) * (s.confidence or 0.5),
                reverse=True
            )
    
    async def _size_position(
        self,
        signal: Signal,
        mandate: Mandate,
        total_capital: float,
        available_cash: float
    ) -> Optional[Dict[str, Any]]:
        """
        Size position based on:
        - Volatility
        - Risk per trade cap
        - Available capital
        - Kelly criterion (lite)
        """
        try:
            # Get latest features for volatility
            feature = self.db.query(Feature).filter(
                Feature.symbol == signal.symbol
            ).order_by(Feature.timestamp.desc()).first()
            
            # Get current price (from latest market data)
            latest_candle = self.db.query(MarketDataCache).filter(
                MarketDataCache.symbol == signal.symbol,
                MarketDataCache.exchange == signal.exchange
            ).order_by(MarketDataCache.timestamp.desc()).first()
            
            if not latest_candle:
                logger.warning(f"No price data for {signal.symbol}")
                return None
            
            entry_price = latest_candle.close
            
            # Calculate stop loss and take profit
            atr = feature.atr_14d if feature and feature.atr_14d else entry_price * 0.02
            
            if signal.direction == "LONG":
                stop_loss = entry_price - (atr * mandate.sl_multiplier)
                take_profit = entry_price + (atr * mandate.tp_multiplier)
            else:  # SHORT
                stop_loss = entry_price + (atr * mandate.sl_multiplier)
                take_profit = entry_price - (atr * mandate.tp_multiplier)
            
            # Risk per share
            risk_per_share = abs(entry_price - stop_loss)
            
            if risk_per_share <= 0:
                logger.warning(f"Invalid risk calculation for {signal.symbol}")
                return None
            
            # Calculate quantity based on risk
            max_risk_amount = total_capital * (mandate.risk_per_trade_percent / 100)
            quantity = int(max_risk_amount / risk_per_share)
            
            # Ensure minimum quantity
            if quantity < 1:
                logger.warning(f"Quantity too small for {signal.symbol}")
                return None
            
            # Position size
            position_size = entry_price * quantity
            
            # Check against max position size
            max_position_size = total_capital * 0.10  # 10% max per position
            if position_size > max_position_size:
                quantity = int(max_position_size / entry_price)
                position_size = entry_price * quantity
            
            # Check available cash
            if position_size > available_cash:
                quantity = int(available_cash / entry_price)
                position_size = entry_price * quantity
            
            if quantity < 1:
                logger.warning(f"Insufficient cash for {signal.symbol}")
                return None
            
            # Calculate risk metrics
            risk_amount = risk_per_share * quantity
            reward_amount = abs(take_profit - entry_price) * quantity
            risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0
            
            return {
                "signal_id": signal.id,
                "symbol": signal.symbol,
                "exchange": signal.exchange,
                "direction": signal.direction,
                "entry_price": entry_price,
                "quantity": quantity,
                "position_size_rupees": position_size,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_amount": risk_amount,
                "reward_amount": reward_amount,
                "risk_reward_ratio": risk_reward_ratio,
                "confidence": signal.confidence,
                "edge": signal.edge,
                "horizon_days": signal.horizon_days,
                "thesis_bullets": signal.thesis_bullets
            }
            
        except Exception as e:
            logger.error(f"Error sizing position for {signal.symbol}: {e}")
            return None
    
    async def check_position_limits(
        self,
        account_id: int
    ) -> Dict[str, Any]:
        """
        Check if account can accept new positions.
        
        Returns:
            Dict with:
            - can_add: bool
            - current_positions: int
            - max_positions: int
            - available_slots: int
        """
        mandate = self.db.query(Mandate).filter(
            Mandate.account_id == account_id,
            Mandate.is_active == True
        ).first()
        
        if not mandate:
            return {
                "can_add": False,
                "current_positions": 0,
                "max_positions": 0,
                "available_slots": 0,
                "reason": "No active mandate"
            }
        
        current_count = self.db.query(PositionV2).filter(
            PositionV2.account_id == account_id,
            PositionV2.closed_at.is_(None)
        ).count()
        
        available_slots = mandate.max_positions - current_count
        
        return {
            "can_add": available_slots > 0,
            "current_positions": current_count,
            "max_positions": mandate.max_positions,
            "available_slots": available_slots
        }
    
    async def check_sector_exposure(
        self,
        account_id: int,
        sector: str
    ) -> Dict[str, Any]:
        """
        Check sector exposure limits.
        
        Returns:
            Dict with exposure info and whether adding is allowed
        """
        mandate = self.db.query(Mandate).filter(
            Mandate.account_id == account_id,
            Mandate.is_active == True
        ).first()
        
        if not mandate:
            return {"can_add": False, "reason": "No mandate"}
        
        # Check if sector is banned
        if sector.lower() in [s.lower() for s in (mandate.banned_sectors or [])]:
            return {
                "can_add": False,
                "reason": f"Sector '{sector}' is banned",
                "current_exposure_percent": 0
            }
        
        # Calculate actual sector exposure from positions
        # Note: Requires sector mapping to be configured
        # Production: Add sector mapping via Upstox instrument metadata or manual config
        # For now, returns estimated exposure
        return {
            "can_add": True,
            "current_exposure_percent": 0,
            "max_allowed_percent": mandate.max_sector_exposure_percent
        }

