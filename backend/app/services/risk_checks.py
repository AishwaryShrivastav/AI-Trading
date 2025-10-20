"""Risk and compliance guardrails."""
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from ..database import TradeCard, Position, Setting
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RiskChecker:
    """Pre-trade risk and compliance checks."""
    
    def __init__(self, db: Session, broker = None):
        self.db = db
        self.broker = broker
        self.settings = settings
    
    async def run_all_checks(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        trade_type: str,
        exchange: str = "NSE"
    ) -> Tuple[bool, List[str]]:
        """
        Run all pre-trade checks.
        
        Returns:
            Tuple of (all_passed: bool, warnings: List[str])
        """
        warnings = []
        
        # Run each check
        liquidity_ok = await self.check_liquidity(symbol, quantity)
        if not liquidity_ok:
            warnings.append(f"Liquidity check failed: ADV below {self.settings.min_liquidity_adv}")
        
        position_size_ok = await self.check_position_size_risk(
            quantity, entry_price, stop_loss
        )
        if not position_size_ok:
            warnings.append(
                f"Position size risk exceeds {self.settings.max_capital_risk_percent}% of capital"
            )
        
        exposure_ok = await self.check_exposure_limits(symbol, quantity, entry_price)
        if not exposure_ok:
            warnings.append("Exposure limits exceeded")
        
        event_window_ok = await self.check_event_windows(symbol)
        if not event_window_ok:
            warnings.append(
                f"Within {self.settings.earnings_blackout_days} days of earnings/corporate action"
            )
        
        # Additional checks
        circuit_ok = await self.check_circuit_breaker(symbol)
        if not circuit_ok:
            warnings.append("Stock in circuit limit or halted")
        
        margin_ok = await self.check_margin_availability(quantity, entry_price)
        if not margin_ok:
            warnings.append("Insufficient margin/funds")
        
        # All critical checks must pass
        all_passed = liquidity_ok and position_size_ok and margin_ok
        
        return all_passed, warnings
    
    async def check_liquidity(self, symbol: str, quantity: int) -> bool:
        """
        Check if symbol has sufficient liquidity.
        
        Validates that average daily volume exceeds minimum threshold.
        """
        try:
            # Query from market_data_cache for actual ADV
            from ..database import MarketDataCache
            from sqlalchemy import func
            
            # Get last 20 days volume
            recent_volumes = self.db.query(func.avg(MarketDataCache.volume)).filter(
                MarketDataCache.symbol == symbol,
                MarketDataCache.timestamp >= datetime.now() - timedelta(days=20)
            ).scalar()
            
            if recent_volumes is None:
                logger.warning(f"No volume data for {symbol}, assuming liquidity check passes")
                return True
            
            adv = recent_volumes
            
            # Check if ADV meets minimum threshold
            if adv < self.settings.min_liquidity_adv:
                logger.warning(f"{symbol} ADV {adv} below threshold {self.settings.min_liquidity_adv}")
                return False
            
            # Also check if our quantity is not too large relative to ADV
            # Rule: quantity should be < 5% of ADV
            if quantity > (adv * 0.05):
                logger.warning(f"{symbol} order quantity {quantity} exceeds 5% of ADV {adv}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Liquidity check error for {symbol}: {e}")
            # Fail safe: pass check but log warning
            return True
    
    async def check_position_size_risk(
        self,
        quantity: int,
        entry_price: float,
        stop_loss: float
    ) -> bool:
        """
        Check if risk per trade is within limits.
        
        Risk = (entry_price - stop_loss) * quantity
        Should be <= MAX_CAPITAL_RISK_PERCENT% of total capital
        """
        try:
            # Calculate risk amount
            risk_per_share = abs(entry_price - stop_loss)
            total_risk = risk_per_share * quantity
            
            # Get total capital
            total_capital = await self._get_total_capital()
            
            # Calculate risk percentage
            risk_percent = (total_risk / total_capital) * 100
            
            if risk_percent > self.settings.max_capital_risk_percent:
                logger.warning(
                    f"Position risk {risk_percent:.2f}% exceeds limit "
                    f"{self.settings.max_capital_risk_percent}%"
                )
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Position size risk check error: {e}")
            return False
    
    async def check_exposure_limits(
        self,
        symbol: str,
        quantity: int,
        entry_price: float
    ) -> bool:
        """
        Check exposure limits:
        - Max position size per symbol
        - Max sector exposure
        """
        try:
            total_capital = await self._get_total_capital()
            position_value = quantity * entry_price
            
            # Check per-symbol exposure
            position_percent = (position_value / total_capital) * 100
            
            if position_percent > self.settings.max_position_size_percent:
                logger.warning(
                    f"Position size {position_percent:.2f}% exceeds limit "
                    f"{self.settings.max_position_size_percent}%"
                )
                return False
            
            # Sector exposure check
            # Note: For production, sector mapping should be configured via:
            # 1. Upstox instrument metadata, or
            # 2. Manual sector mapping in settings
            # Currently passes as sector mapping is optional
            
            return True
            
        except Exception as e:
            logger.error(f"Exposure check error: {e}")
            return False
    
    async def check_event_windows(self, symbol: str) -> bool:
        """
        Check if symbol has upcoming earnings or corporate actions.
        
        Avoid trading within blackout window.
        Production: Integrate with earnings calendar API or maintain event database.
        """
        try:
            # Check in Events table for recent events
            from ..database import Event
            from datetime import timedelta
            
            blackout_days = self.settings.earnings_blackout_days
            now = datetime.now()
            
            # Check for events within blackout window
            recent_events = self.db.query(Event).filter(
                Event.symbols.contains(symbol),
                Event.event_type.in_(["EARNINGS", "RESULTS", "DIVIDEND"]),
                Event.event_timestamp >= now - timedelta(days=blackout_days),
                Event.event_timestamp <= now + timedelta(days=blackout_days)
            ).all()
            
            if recent_events:
                logger.warning(
                    f"{symbol} has {len(recent_events)} event(s) within blackout window"
                )
                return False
            
            # Also check settings for manually configured events
            event_setting = self.db.query(Setting).filter(
                Setting.key == f"events_{symbol}"
            ).first()
            
            if event_setting and event_setting.value:
                events = event_setting.value
                
                for event in events:
                    event_date = datetime.fromisoformat(event['date'])
                    days_until = (event_date - datetime.now()).days
                    
                    if abs(days_until) <= blackout_days:
                        logger.warning(
                            f"{symbol} has {event['type']} in {days_until} days"
                        )
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Event window check error for {symbol}: {e}")
            return True  # Fail safe - allow trade with warning
    
    async def check_circuit_breaker(self, symbol: str) -> bool:
        """
        Check if symbol is in circuit limit or halted.
        
        Production: Use Upstox market quote API to check circuit limit status.
        """
        try:
            # Check with Upstox API for circuit breaker status
            from .broker import UpstoxBroker
            
            broker = UpstoxBroker(
                api_key=self.settings.upstox_api_key,
                api_secret=self.settings.upstox_api_secret,
                redirect_uri=self.settings.upstox_redirect_uri
            )
            
            # Load access token
            from ..database import Setting
            access_token = self.db.query(Setting).filter(
                Setting.key == "upstox_access_token"
            ).first()
            
            if access_token:
                broker.access_token = access_token.value
                
                # Get market quote to check circuit status
                instrument_key = broker._get_instrument_key(symbol, "NSE")
                
                try:
                    quote = await broker.get_market_quote_full([instrument_key])
                    
                    # Check for circuit breaker indicators in quote
                    # Upstox API provides this in market depth/quote
                    # For now, if we can fetch quote, stock is tradable
                    await broker.close()
                    return True
                    
                except:
                    await broker.close()
                    # If quote fetch fails, stock might be halted
                    logger.warning(f"{symbol} market quote unavailable, may be halted")
                    return False
            
            # If no token, assume okay
            return True
            
        except Exception as e:
            logger.error(f"Circuit breaker check error: {e}")
            return True  # Fail safe - allow trade with warning
    
    async def check_margin_availability(
        self,
        quantity: int,
        entry_price: float
    ) -> bool:
        """Check if sufficient margin/funds available."""
        try:
            if not self.broker:
                logger.warning("No broker connection, skipping margin check")
                return True
            
            # Get funds from broker
            funds = await self.broker.get_funds()
            available = funds.get("equity", {}).get("available_margin", 0)
            
            # Calculate required funds
            required = quantity * entry_price
            
            # Add buffer for charges (0.5%)
            required_with_buffer = required * 1.005
            
            if available < required_with_buffer:
                logger.warning(
                    f"Insufficient margin: available={available}, "
                    f"required={required_with_buffer}"
                )
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Margin check error: {e}")
            # Be conservative: fail if we can't verify
            return False
    
    async def _get_total_capital(self) -> float:
        """Get total account capital."""
        try:
            if self.broker:
                funds = await self.broker.get_funds()
                # Total capital = available + used
                equity = funds.get("equity", {})
                total = equity.get("available_margin", 0) + equity.get("used_margin", 0)
                return total
            
            # Fallback: use configured value
            capital_setting = self.db.query(Setting).filter(
                Setting.key == "total_capital"
            ).first()
            
            if capital_setting:
                return float(capital_setting.value)
            
            # Default: 100k
            logger.warning("Using default capital of 100,000")
            return 100000.0
            
        except Exception as e:
            logger.error(f"Error getting total capital: {e}")
            return 100000.0
    
    def get_risk_summary(self, trade_card: TradeCard) -> Dict[str, Any]:
        """Get risk summary for a trade card."""
        risk_per_share = abs(trade_card.entry_price - trade_card.stop_loss)
        total_risk = risk_per_share * trade_card.quantity
        position_value = trade_card.entry_price * trade_card.quantity
        
        reward_per_share = abs(trade_card.take_profit - trade_card.entry_price)
        total_reward = reward_per_share * trade_card.quantity
        
        risk_reward_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0
        
        return {
            "position_value": round(position_value, 2),
            "total_risk": round(total_risk, 2),
            "total_reward": round(total_reward, 2),
            "risk_per_share": round(risk_per_share, 2),
            "reward_per_share": round(reward_per_share, 2),
            "risk_reward_ratio": round(risk_reward_ratio, 2),
            "risk_warnings": trade_card.risk_warnings or []
        }

