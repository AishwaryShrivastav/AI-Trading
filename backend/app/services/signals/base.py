"""Abstract base class for signal generation strategies."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import pandas as pd


class SignalBase(ABC):
    """Abstract base class for trading signal generation."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def generate_signals(
        self,
        symbols: List[str],
        market_data: Dict[str, pd.DataFrame],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate trading signals for given symbols.
        
        Args:
            symbols: List of symbols to analyze
            market_data: Dict of symbol -> OHLCV DataFrame
            context: Additional context data
            
        Returns:
            List of signal dictionaries containing:
                - symbol: str
                - strategy: str
                - score: float (0.0 to 1.0)
                - entry_price: float
                - suggested_sl: float
                - suggested_tp: float
                - trade_type: str (BUY or SELL)
                - reasoning: str
                - metadata: Dict[str, Any]
        """
        pass
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        risk_amount: float
    ) -> int:
        """
        Calculate position size based on risk amount.
        
        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price
            risk_amount: Maximum amount to risk in rupees
            
        Returns:
            Quantity of shares
        """
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return 0
        
        quantity = int(risk_amount / risk_per_share)
        return max(1, quantity)  # At least 1 share
    
    def calculate_risk_reward(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> float:
        """
        Calculate risk/reward ratio.
        
        Returns:
            Risk/reward ratio (e.g., 2.0 means 1:2 risk/reward)
        """
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        
        if risk <= 0:
            return 0.0
        
        return reward / risk

