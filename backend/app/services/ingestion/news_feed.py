"""News feed ingestion from NewsAPI and RSS feeds."""
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
from .base import FeedSource

logger = logging.getLogger(__name__)


class NewsFeedSource(FeedSource):
    """
    News feed ingestion from NewsAPI.
    
    Fetches:
    - Financial news
    - Company-specific news
    - Market news
    - Regulatory announcements
    """
    
    NEWS_API_URL = "https://newsapi.org/v2/everything"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__("NEWS_API")
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def fetch(
        self,
        symbols: Optional[List[str]] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch news articles.
        
        Args:
            symbols: List of stock symbols to fetch news for
            from_time: Start datetime
            to_time: End datetime
            
        Returns:
            List of raw articles
        """
        if not self.api_key:
            logger.warning("NewsAPI key not configured, returning empty")
            return []
        
        try:
            # Build query
            if symbols:
                # Search for company names
                query = " OR ".join(symbols)
            else:
                # General market news
                query = "india stock market OR nse OR bse OR sebi"
            
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "apiKey": self.api_key
            }
            
            if from_time:
                params["from"] = from_time.isoformat()
            else:
                # Default to last 24 hours
                params["from"] = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            
            if to_time:
                params["to"] = to_time.isoformat()
            
            response = await self.client.get(self.NEWS_API_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            articles = data.get("articles", [])
            logger.info(f"Fetched {len(articles)} news articles")
            
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return []
    
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize NewsAPI article to standard format.
        
        Article structure:
        {
            "title": str,
            "description": str,
            "content": str,
            "url": str,
            "publishedAt": str (ISO),
            "source": {"name": str}
        }
        """
        # Extract content
        title = raw_data.get("title", "")
        description = raw_data.get("description", "")
        content = raw_data.get("content", "")
        
        full_content = f"{title}. {description}. {content}"
        
        # Parse timestamp
        published_str = raw_data.get("publishedAt", "")
        try:
            event_timestamp = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except:
            event_timestamp = datetime.utcnow()
        
        # Extract symbols (basic keyword matching)
        symbols = self._extract_symbols(full_content)
        
        # Classify event type (basic)
        event_type = self._classify_event(full_content)
        
        # Determine priority
        priority = self._determine_priority(event_type, symbols)
        
        return {
            "source": self.source_name,
            "source_url": raw_data.get("url", ""),
            "artifact_url": raw_data.get("url", ""),
            "raw_content": full_content,
            "event_timestamp": event_timestamp,
            "symbols": symbols,
            "event_type": event_type,
            "priority": priority
        }
    
    def _extract_symbols(self, text: str) -> List[str]:
        """Extract stock symbols from text (basic keyword matching)."""
        # Common Indian stock keywords
        text_upper = text.upper()
        known_symbols = [
            "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
            "SBIN", "BAJFINANCE", "ITC", "WIPRO", "LT",
            "AXISBANK", "BHARTIARTL", "ASIANPAINT", "MARUTI", "KOTAKBANK"
        ]
        
        found = []
        for symbol in known_symbols:
            if symbol in text_upper:
                found.append(symbol)
        
        return found
    
    def _classify_event(self, text: str) -> str:
        """Basic event classification."""
        text_lower = text.lower()
        
        if any(kw in text_lower for kw in ["buyback", "share buyback"]):
            return "BUYBACK"
        elif any(kw in text_lower for kw in ["earnings", "results", "quarterly"]):
            return "EARNINGS"
        elif any(kw in text_lower for kw in ["guidance", "forecast", "outlook"]):
            return "GUIDANCE"
        elif any(kw in text_lower for kw in ["penalty", "fine", "sebi action"]):
            return "PENALTY"
        elif any(kw in text_lower for kw in ["rbi", "policy", "rate cut", "rate hike"]):
            return "POLICY"
        elif any(kw in text_lower for kw in ["merger", "acquisition", "deal"]):
            return "M&A"
        else:
            return "GENERAL"
    
    def _determine_priority(self, event_type: str, symbols: List[str]) -> str:
        """Determine event priority."""
        high_priority_events = ["BUYBACK", "EARNINGS", "M&A", "PENALTY"]
        
        if event_type in high_priority_events:
            return "HIGH"
        elif symbols:  # Has specific stock mentions
            return "MEDIUM"
        else:
            return "LOW"
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

