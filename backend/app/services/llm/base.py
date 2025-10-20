"""Abstract base class for LLM providers."""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime


class LLMBase(ABC):
    """Abstract base class for LLM integrations."""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
    
    @abstractmethod
    async def generate_trade_analysis(
        self,
        signal: Dict[str, Any],
        market_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze a trade signal and generate a comprehensive trade card.
        
        Args:
            signal: Signal candidate from strategy
            market_data: Current market data (OHLCV, indicators, etc.)
            context: Additional context (news, events, macro data)
            
        Returns:
            Dict containing:
                - confidence: float (0.0 to 1.0)
                - evidence: str (reasoning)
                - risks: str (identified risks)
                - suggested_entry: float
                - suggested_sl: float
                - suggested_tp: float
                - horizon_days: int
                - tags: List[str]
        """
        pass
    
    @abstractmethod
    async def rank_signals(
        self,
        signals: List[Dict[str, Any]],
        max_selections: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Rank and filter multiple signals to select top opportunities.
        
        Args:
            signals: List of signal candidates
            max_selections: Maximum number to return
            
        Returns:
            Sorted list of top signals with rankings
        """
        pass
    
    def get_model_version(self) -> str:
        """Return the model version/name being used."""
        return self.model

