"""Risk Monitor - Real-time risk tracking and kill switches."""
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from ..database import (
    Account, PositionV2, RiskSnapshot, KillSwitch,
    Mandate, FundingPlan
)

logger = logging.getLogger(__name__)


class RiskMonitor:
    """
    Real-time risk monitoring with kill switches.
    
    Monitors:
    - Total open risk per account
    - Daily P&L and drawdown
    - Portfolio volatility
    - Sector concentration
    - Kill switch triggers
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._initialize_default_kill_switches()
    
    def _initialize_default_kill_switches(self):
        """Create default kill switches."""
        # Portfolio-wide kill switches
        default_switches = [
            {
                "account_id": None,  # Portfolio-wide
                "switch_type": "MAX_DAILY_LOSS",
                "threshold_value": 5.0,  # 5% daily loss
                "threshold_type": "PERCENTAGE",
                "action_on_trigger": {
                    "pause_new_entries": True,
                    "close_all": False,
                    "alert_user": True
                },
                "auto_reset_minutes": 60
            },
            {
                "account_id": None,
                "switch_type": "MAX_DRAWDOWN",
                "threshold_value": 15.0,  # 15% max drawdown
                "threshold_type": "PERCENTAGE",
                "action_on_trigger": {
                    "pause_new_entries": True,
                    "close_all": False,
                    "alert_user": True
                },
                "auto_reset_minutes": 1440  # 24 hours
            }
        ]
        
        for switch_data in default_switches:
            existing = self.db.query(KillSwitch).filter(
                KillSwitch.switch_type == switch_data["switch_type"],
                KillSwitch.account_id.is_(None)
            ).first()
            
            if not existing:
                switch = KillSwitch(**switch_data)
                self.db.add(switch)
        
        try:
            self.db.commit()
            logger.info("Initialized default kill switches")
        except:
            self.db.rollback()
    
    async def capture_snapshot(
        self,
        account_id: Optional[int] = None
    ) -> RiskSnapshot:
        """
        Capture current risk snapshot for an account or portfolio.
        
        Args:
            account_id: Specific account or None for portfolio-wide
            
        Returns:
            RiskSnapshot object
        """
        if account_id:
            positions = self.db.query(PositionV2).filter(
                PositionV2.account_id == account_id,
                PositionV2.closed_at.is_(None)
            ).all()
        else:
            positions = self.db.query(PositionV2).filter(
                PositionV2.closed_at.is_(None)
            ).all()
        
        # Calculate metrics
        total_open_risk = sum(p.risk_amount or 0 for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl or 0 for p in positions)
        open_positions_count = len(positions)
        
        # Daily metrics - calculate from today's closed positions
        from datetime import timedelta
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if account_id:
            today_closed = self.db.query(PositionV2).filter(
                PositionV2.account_id == account_id,
                PositionV2.closed_at >= today_start
            ).all()
        else:
            today_closed = self.db.query(PositionV2).filter(
                PositionV2.closed_at >= today_start
            ).all()
        
        daily_realized_pnl = sum(p.realized_pnl or 0 for p in today_closed)
        daily_new_risk = total_open_risk
        daily_max_drawdown = min(total_unrealized_pnl, 0)
        
        # Sector exposure calculation
        # Note: Requires sector mapping in production
        # Can be enhanced by integrating Upstox instrument sector data
        sector_exposures = {}
        
        # Kill switches
        active_switches = self.db.query(KillSwitch).filter(
            KillSwitch.is_active == True,
            KillSwitch.is_triggered == True
        ).all()
        
        kill_switches_active = [
            {
                "type": ks.switch_type,
                "triggered_at": ks.triggered_at.isoformat() if ks.triggered_at else None,
                "value": ks.triggered_value
            }
            for ks in active_switches
        ]
        
        # Create snapshot
        snapshot = RiskSnapshot(
            account_id=account_id,
            total_open_risk=total_open_risk,
            total_unrealized_pnl=total_unrealized_pnl,
            open_positions_count=open_positions_count,
            daily_new_risk=daily_new_risk,
            daily_realized_pnl=daily_realized_pnl,
            daily_max_drawdown=daily_max_drawdown,
            portfolio_volatility=0.0,  # Optional: Enhance with volatility calculation
            volatility_target=2.0,
            sector_exposures=sector_exposures,
            kill_switches_active=kill_switches_active,
            timestamp=datetime.utcnow()
        )
        
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        
        return snapshot
    
    async def check_kill_switches(
        self,
        account_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Check all kill switches and trigger if needed.
        
        Returns:
            List of triggered kill switches
        """
        # Get recent snapshot
        snapshot = await self.capture_snapshot(account_id)
        
        # Get applicable kill switches
        switches = self.db.query(KillSwitch).filter(
            KillSwitch.is_active == True,
            KillSwitch.is_triggered == False
        )
        
        if account_id:
            switches = switches.filter(KillSwitch.account_id == account_id)
        else:
            switches = switches.filter(KillSwitch.account_id.is_(None))
        
        switches = switches.all()
        
        triggered = []
        
        for switch in switches:
            should_trigger = False
            trigger_value = None
            
            if switch.switch_type == "MAX_DAILY_LOSS":
                # Check daily loss
                if snapshot.daily_realized_pnl + snapshot.total_unrealized_pnl < 0:
                    loss_amount = abs(snapshot.daily_realized_pnl + snapshot.total_unrealized_pnl)
                    
                    # Get total capital
                    total_capital = await self._get_total_capital(account_id)
                    
                    if total_capital > 0:
                        loss_percent = (loss_amount / total_capital) * 100
                        
                        if loss_percent >= switch.threshold_value:
                            should_trigger = True
                            trigger_value = loss_percent
            
            elif switch.switch_type == "MAX_DRAWDOWN":
                # Check max drawdown
                if snapshot.daily_max_drawdown < 0:
                    total_capital = await self._get_total_capital(account_id)
                    
                    if total_capital > 0:
                        drawdown_percent = (abs(snapshot.daily_max_drawdown) / total_capital) * 100
                        
                        if drawdown_percent >= switch.threshold_value:
                            should_trigger = True
                            trigger_value = drawdown_percent
            
            if should_trigger:
                # Trigger kill switch
                switch.is_triggered = True
                switch.triggered_at = datetime.utcnow()
                switch.triggered_value = trigger_value
                
                logger.warning(
                    f"Kill switch triggered: {switch.switch_type} "
                    f"(threshold: {switch.threshold_value}, actual: {trigger_value})"
                )
                
                triggered.append({
                    "switch_id": switch.id,
                    "switch_type": switch.switch_type,
                    "threshold": switch.threshold_value,
                    "actual_value": trigger_value,
                    "actions": switch.action_on_trigger,
                    "message": f"{switch.switch_type} breached: {trigger_value:.2f}% >= {switch.threshold_value}%"
                })
        
        if triggered:
            self.db.commit()
        
        return triggered
    
    async def _get_total_capital(self, account_id: Optional[int]) -> float:
        """Get total capital for account or portfolio."""
        if account_id:
            funding = self.db.query(FundingPlan).filter(
                FundingPlan.account_id == account_id
            ).first()
            
            if funding:
                return funding.available_cash + funding.total_deployed + funding.reserved_cash
        else:
            all_funding = self.db.query(FundingPlan).all()
            return sum(
                fp.available_cash + fp.total_deployed + fp.reserved_cash
                for fp in all_funding
            )
        
        return 0.0
    
    async def reset_kill_switch(
        self,
        switch_id: int
    ):
        """Reset a triggered kill switch."""
        switch = self.db.query(KillSwitch).filter(KillSwitch.id == switch_id).first()
        
        if switch:
            switch.is_triggered = False
            switch.triggered_at = None
            switch.triggered_value = None
            self.db.commit()
            
            logger.info(f"Reset kill switch: {switch.switch_type}")
    
    async def should_pause_new_entries(
        self,
        account_id: Optional[int] = None
    ) -> bool:
        """
        Check if new entries should be paused due to kill switches.
        
        Returns:
            True if new entries should be paused
        """
        query = self.db.query(KillSwitch).filter(
            KillSwitch.is_active == True,
            KillSwitch.is_triggered == True
        )
        
        if account_id:
            query = query.filter(KillSwitch.account_id == account_id)
        else:
            query = query.filter(KillSwitch.account_id.is_(None))
        
        triggered_switches = query.all()
        
        for switch in triggered_switches:
            actions = switch.action_on_trigger or {}
            if actions.get("pause_new_entries"):
                return True
        
        return False
    
    async def get_risk_metrics(
        self,
        account_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get current risk metrics.
        
        Returns:
            Dict with risk metrics and limits
        """
        snapshot = await self.capture_snapshot(account_id)
        
        # Check if paused
        is_paused = await self.should_pause_new_entries(account_id)
        
        total_capital = await self._get_total_capital(account_id)
        
        return {
            "total_capital": total_capital,
            "open_risk": snapshot.total_open_risk,
            "open_risk_percent": (snapshot.total_open_risk / total_capital * 100) if total_capital > 0 else 0,
            "unrealized_pnl": snapshot.total_unrealized_pnl,
            "unrealized_pnl_percent": (snapshot.total_unrealized_pnl / total_capital * 100) if total_capital > 0 else 0,
            "open_positions": snapshot.open_positions_count,
            "daily_pnl": snapshot.daily_realized_pnl + snapshot.total_unrealized_pnl,
            "is_paused": is_paused,
            "timestamp": snapshot.timestamp.isoformat()
        }

