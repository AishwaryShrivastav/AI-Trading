"""Playbook Manager - Event-specific tactical strategies."""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import logging

from ..database import Playbook, Event

logger = logging.getLogger(__name__)


class PlaybookManager:
    """
    Manages event playbooks for tactical strategy adjustments.
    
    Playbooks define how to handle specific events in specific regimes:
    - Priority adjustments
    - Tranche deployment strategies
    - Stop-loss / take-profit modifications
    - Sector rotation rules
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._initialize_default_playbooks()
    
    def _initialize_default_playbooks(self):
        """Create default playbooks if they don't exist."""
        default_playbooks = [
            {
                "name": "Buyback Bullish",
                "event_type": "BUYBACK",
                "regime_match": {"volatility": ["LOW", "MED"], "liquidity": ["HIGH", "MEDIUM"]},
                "priority_boost": 1.5,
                "tranche_plan": [{"percent": 50, "delay": 0}, {"percent": 50, "delay": 1}],
                "acceptable_gap_chase_percent": 2.0,
                "sl_multiplier_override": 1.8,
                "tp_multiplier_override": 4.5,
                "pause_smallcap": False,
                "pause_duration_hours": 0
            },
            {
                "name": "Earnings Beat Continuation",
                "event_type": "EARNINGS",
                "regime_match": {"volatility": ["LOW", "MED"]},
                "priority_boost": 1.3,
                "tranche_plan": [{"percent": 100, "delay": 0}],  # All at once
                "acceptable_gap_chase_percent": 1.5,
                "sl_multiplier_override": 2.0,
                "tp_multiplier_override": 4.0,
                "pause_smallcap": True,
                "pause_duration_hours": 2
            },
            {
                "name": "Regulatory Penalty",
                "event_type": "PENALTY",
                "regime_match": {"liquidity": ["HIGH"]},
                "priority_boost": 1.0,
                "tranche_plan": [{"percent": 33, "delay": 0}, {"percent": 33, "delay": 2}, {"percent": 34, "delay": 4}],
                "acceptable_gap_chase_percent": 1.0,
                "sl_multiplier_override": 2.5,
                "tp_multiplier_override": 3.5,
                "pause_smallcap": True,
                "pause_duration_hours": 24
            },
            {
                "name": "Policy Surprise",
                "event_type": "POLICY",
                "regime_match": {"volatility": ["LOW", "MED", "HIGH"]},
                "priority_boost": 1.4,
                "tranche_plan": [{"percent": 100, "delay": 0}],
                "acceptable_gap_chase_percent": 2.5,
                "sl_multiplier_override": 2.2,
                "tp_multiplier_override": 5.0,
                "pause_smallcap": False,
                "pause_duration_hours": 0
            }
        ]
        
        for pb_data in default_playbooks:
            existing = self.db.query(Playbook).filter(
                Playbook.name == pb_data["name"]
            ).first()
            
            if not existing:
                playbook = Playbook(**pb_data)
                self.db.add(playbook)
        
        try:
            self.db.commit()
            logger.info("Initialized default playbooks")
        except:
            self.db.rollback()
    
    async def get_playbook_for_event(
        self,
        event_type: str,
        regime: Dict[str, str]
    ) -> Optional[Playbook]:
        """
        Find matching playbook for event and regime.
        
        Args:
            event_type: Type of event (BUYBACK, EARNINGS, etc.)
            regime: Current regime {"volatility": "MED", "liquidity": "HIGH"}
            
        Returns:
            Matching playbook or None
        """
        playbooks = self.db.query(Playbook).filter(
            Playbook.event_type == event_type,
            Playbook.is_active == True
        ).all()
        
        for pb in playbooks:
            if self._regime_matches(pb.regime_match, regime):
                return pb
        
        return None
    
    def _regime_matches(
        self,
        playbook_regime: Dict[str, List[str]],
        current_regime: Dict[str, str]
    ) -> bool:
        """Check if current regime matches playbook requirements."""
        if not playbook_regime:
            return True  # Match all regimes
        
        for key, allowed_values in playbook_regime.items():
            if key in current_regime:
                if current_regime[key] not in allowed_values:
                    return False
        
        return True
    
    async def apply_playbook_overrides(
        self,
        opportunity: Dict[str, Any],
        playbook: Playbook
    ) -> Dict[str, Any]:
        """
        Apply playbook overrides to an opportunity.
        
        Modifies:
        - Entry sizing (tranches)
        - Stop loss / take profit
        - Priority
        """
        modified = opportunity.copy()
        
        # Apply priority boost
        if "priority" in modified:
            modified["priority"] = int(modified["priority"] * playbook.priority_boost)
        
        # Apply SL/TP overrides
        if playbook.sl_multiplier_override:
            # Recalculate SL
            entry = modified["entry_price"]
            direction = modified["direction"]
            # Would need ATR here, simplified for now
            pass
        
        # Add tranche config
        modified["tranche_config"] = playbook.tranche_plan
        modified["playbook_id"] = playbook.id
        modified["playbook_name"] = playbook.name
        
        logger.info(f"Applied playbook '{playbook.name}' to {opportunity['symbol']}")
        
        return modified
    
    async def create_playbook(
        self,
        name: str,
        event_type: str,
        config: Dict[str, Any]
    ) -> Playbook:
        """Create a custom playbook."""
        playbook = Playbook(
            name=name,
            event_type=event_type,
            regime_match=config.get("regime_match"),
            priority_boost=config.get("priority_boost", 1.0),
            tranche_plan=config.get("tranche_plan"),
            acceptable_gap_chase_percent=config.get("acceptable_gap_chase_percent"),
            sl_multiplier_override=config.get("sl_multiplier_override"),
            tp_multiplier_override=config.get("tp_multiplier_override"),
            pause_smallcap=config.get("pause_smallcap", False),
            pause_duration_hours=config.get("pause_duration_hours", 0),
            is_active=True
        )
        
        self.db.add(playbook)
        self.db.commit()
        self.db.refresh(playbook)
        
        logger.info(f"Created playbook: {name}")
        return playbook

