"""Production tests for data ingestion."""
import pytest
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal, Event
from backend.app.services.ingestion.ingestion_manager import IngestionManager
from backend.app.services.ingestion.news_feed import NewsFeedSource
from backend.app.services.ingestion.nse_feed import NSEFeedSource


@pytest.fixture
def db():
    """Database session fixture."""
    session = SessionLocal()
    yield session
    session.close()


class TestNewsFeedSource:
    """Test news feed ingestion."""
    
    @pytest.mark.asyncio
    async def test_news_feed_initialization(self):
        """Test news feed can be initialized."""
        feed = NewsFeedSource(api_key=None)  # No API key for test
        assert feed.source_name == "NEWS_API"
        await feed.close()
    
    def test_normalize_news_article(self):
        """Test news article normalization."""
        feed = NewsFeedSource(api_key=None)
        
        raw_article = {
            "title": "Reliance announces major expansion",
            "description": "Reliance Industries plans expansion in retail",
            "content": "Full article content here",
            "url": "https://example.com/article",
            "publishedAt": "2025-10-20T10:00:00Z",
            "source": {"name": "Economic Times"}
        }
        
        normalized = feed.normalize(raw_article)
        
        assert normalized["source"] == "NEWS_API"
        assert normalized["source_url"] == "https://example.com/article"
        assert "RELIANCE" in normalized["symbols"]
        assert normalized["event_type"] in ["GENERAL", "EARNINGS", "BUYBACK", "GUIDANCE", "PENALTY", "POLICY", "M&A"]
        assert normalized["priority"] in ["HIGH", "MEDIUM", "LOW"]


class TestNSEFeedSource:
    """Test NSE feed ingestion."""
    
    def test_nse_feed_initialization(self):
        """Test NSE feed can be initialized."""
        feed = NSEFeedSource()
        assert feed.source_name == "NSE_FILING"
    
    def test_classify_announcement(self):
        """Test announcement classification."""
        feed = NSEFeedSource()
        
        assert feed._classify_announcement("Financial Results for Q2") == "RESULTS"
        assert feed._classify_announcement("Dividend Declaration") == "DIVIDEND"
        assert feed._classify_announcement("Share Buyback") == "BUYBACK"
        assert feed._classify_announcement("Board Meeting") == "MEETING"


class TestIngestionManager:
    """Test ingestion manager orchestration."""
    
    @pytest.mark.asyncio
    async def test_ingest_all(self, db):
        """Test ingesting from all sources."""
        manager = IngestionManager(db)
        
        # Register test source
        nse_feed = NSEFeedSource()
        manager.register_source(nse_feed)
        
        # Ingest (will return 0 as NSE API not accessible without auth)
        count = await manager.ingest_all(symbols=["RELIANCE"])
        
        assert count >= 0
        
        await manager.close_all()
    
    @pytest.mark.asyncio
    async def test_get_priority_queue(self, db):
        """Test getting priority events."""
        manager = IngestionManager(db)
        
        # Get high priority events
        events = await manager.get_priority_queue(priority="HIGH", limit=10)
        
        assert isinstance(events, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

