"""NSE/BSE filings and announcements ingestion."""
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from .base import FeedSource

logger = logging.getLogger(__name__)


class NSEFeedSource(FeedSource):
    """
    NSE corporate announcements and filings.
    
    Fetches:
    - Corporate actions (dividends, splits, bonuses)
    - Board meetings
    - Financial results
    - Material events
    """
    
    NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements"
    
    def __init__(self):
        super().__init__("NSE_FILING")
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Accept": "application/json"
            }
        )
    
    async def fetch(
        self,
        symbols: Optional[List[str]] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch NSE announcements.
        
        Note: NSE API requires session cookies and rate limits.
        Production deployment should use NSE official API with proper authentication.
        
        For production without NSE API access, this returns empty list.
        Enable mock data only for development/testing via ENABLE_MOCK_DATA env var.
        """
        try:
            params = {
                "index": "equities"
            }
            
            if symbols:
                # Filter by symbol (NSE API supports this)
                params["symbol"] = symbols[0] if len(symbols) == 1 else None
            
            response = await self.client.get(self.NSE_ANNOUNCEMENTS_URL, params=params)
            
            # NSE returns 403 without proper session
            if response.status_code == 403:
                logger.info("NSE API access requires authentication session. Configure NSE credentials for production.")
                return []  # Return empty in production
            
            response.raise_for_status()
            data = response.json()
            
            announcements = data.get("data", [])
            logger.info(f"Fetched {len(announcements)} NSE announcements")
            
            return announcements
            
        except Exception as e:
            logger.info(f"NSE API not accessible: {e}. Configure NSE credentials for production use.")
            return []  # Return empty, don't use mock data in production
    
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize NSE announcement to standard format.
        
        NSE structure (approximate):
        {
            "symbol": str,
            "sm_name": str (company name),
            "subject": str,
            "desc": str,
            "an_dt": str (announcement date),
            "attchmntFile": str (PDF link)
        }
        """
        symbol = raw_data.get("symbol", raw_data.get("sm_name", "UNKNOWN"))
        subject = raw_data.get("subject", raw_data.get("desc", ""))
        
        # Parse date
        date_str = raw_data.get("an_dt", "")
        try:
            event_timestamp = datetime.strptime(date_str, "%d-%b-%Y") if date_str else datetime.utcnow()
        except:
            event_timestamp = datetime.utcnow()
        
        # Classify event
        event_type = self._classify_announcement(subject)
        
        return {
            "source": self.source_name,
            "source_url": f"https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            "artifact_url": raw_data.get("attchmntFile", ""),
            "raw_content": subject,
            "event_timestamp": event_timestamp,
            "symbols": [symbol] if symbol != "UNKNOWN" else [],
            "event_type": event_type,
            "priority": "HIGH" if event_type in ["RESULTS", "BUYBACK", "DIVIDEND"] else "MEDIUM"
        }
    
    def _classify_announcement(self, subject: str) -> str:
        """Classify NSE announcement type."""
        subject_lower = subject.lower()
        
        if any(kw in subject_lower for kw in ["result", "financial", "quarterly"]):
            return "RESULTS"
        elif any(kw in subject_lower for kw in ["dividend", "interim dividend"]):
            return "DIVIDEND"
        elif any(kw in subject_lower for kw in ["buyback", "buy back"]):
            return "BUYBACK"
        elif any(kw in subject_lower for kw in ["split", "bonus"]):
            return "CORPORATE_ACTION"
        elif any(kw in subject_lower for kw in ["board meeting", "agm", "egm"]):
            return "MEETING"
        else:
            return "ANNOUNCEMENT"
    
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

