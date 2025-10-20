"""Base classes for data ingestion."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FeedSource(ABC):
    """Abstract base class for feed sources."""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
    
    @abstractmethod
    async def fetch(
        self,
        symbols: Optional[List[str]] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch data from source.
        
        Returns:
            List of raw events/data items
        """
        pass
    
    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw data to standard format.
        
        Returns:
            {
                "source": str,
                "source_url": str,
                "raw_content": str,
                "event_timestamp": datetime,
                "symbols": List[str],
                "event_type": str,
                "priority": str  # HIGH, MEDIUM, LOW
            }
        """
        pass
    
    def dedupe_key(self, data: Dict[str, Any]) -> str:
        """Generate unique key for deduplication."""
        return f"{self.source_name}:{data.get('source_url', '')}:{data.get('event_timestamp', '')}"

