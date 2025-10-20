"""Ingestion Manager - Orchestrates all feed sources."""
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from .base import FeedSource
from .news_feed import NewsFeedSource
from .nse_feed import NSEFeedSource
from ...database import Event

logger = logging.getLogger(__name__)


class IngestionManager:
    """
    Orchestrates data ingestion from multiple sources.
    
    Features:
    - Multi-source ingestion
    - Deduplication
    - Priority queuing
    - Continuous monitoring
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.sources: List[FeedSource] = []
        self._seen_keys = set()  # For deduplication
    
    def register_source(self, source: FeedSource):
        """Register a feed source."""
        self.sources.append(source)
        logger.info(f"Registered source: {source.source_name}")
    
    async def ingest_all(
        self,
        symbols: Optional[List[str]] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None
    ) -> int:
        """
        Ingest from all registered sources.
        
        Returns:
            Number of new events ingested
        """
        total_ingested = 0
        
        for source in self.sources:
            try:
                count = await self.ingest_from_source(
                    source,
                    symbols=symbols,
                    from_time=from_time,
                    to_time=to_time
                )
                total_ingested += count
            except Exception as e:
                logger.error(f"Error ingesting from {source.source_name}: {e}")
        
        logger.info(f"Total events ingested: {total_ingested}")
        return total_ingested
    
    async def ingest_from_source(
        self,
        source: FeedSource,
        symbols: Optional[List[str]] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None
    ) -> int:
        """Ingest from a specific source."""
        try:
            # Fetch raw data
            raw_items = await source.fetch(symbols, from_time, to_time)
            
            if not raw_items:
                return 0
            
            ingested_count = 0
            
            for item in raw_items:
                # Normalize
                normalized = source.normalize(item)
                
                # Deduplicate
                dedupe_key = source.dedupe_key(normalized)
                if dedupe_key in self._seen_keys:
                    continue
                
                # Check database for existing
                existing = self.db.query(Event).filter(
                    Event.source == normalized["source"],
                    Event.source_url == normalized["source_url"],
                    Event.event_timestamp == normalized["event_timestamp"]
                ).first()
                
                if existing:
                    self._seen_keys.add(dedupe_key)
                    continue
                
                # Create event
                event = Event(
                    source=normalized["source"],
                    source_url=normalized["source_url"],
                    artifact_url=normalized.get("artifact_url"),
                    raw_content=normalized["raw_content"],
                    normalized_content=normalized["raw_content"],  # Will be enhanced by NLP
                    event_type=normalized["event_type"],
                    priority=normalized["priority"],
                    symbols=normalized["symbols"],
                    event_timestamp=normalized["event_timestamp"],
                    ingested_at=datetime.utcnow(),
                    processing_status="PENDING"
                )
                
                self.db.add(event)
                self._seen_keys.add(dedupe_key)
                ingested_count += 1
            
            if ingested_count > 0:
                self.db.commit()
                logger.info(f"Ingested {ingested_count} events from {source.source_name}")
            
            return ingested_count
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error ingesting from {source.source_name}: {e}")
            return 0
    
    async def get_priority_queue(
        self,
        priority: str = "HIGH",
        limit: int = 50
    ) -> List[Event]:
        """
        Get high-priority events for hot path processing.
        
        Args:
            priority: Priority level (HIGH, MEDIUM, LOW)
            limit: Maximum events to return
            
        Returns:
            List of pending high-priority events
        """
        events = self.db.query(Event).filter(
            Event.priority == priority,
            Event.processing_status == "PENDING"
        ).order_by(Event.event_timestamp.desc()).limit(limit).all()
        
        return events
    
    async def mark_processed(self, event_id: int):
        """Mark an event as processed."""
        event = self.db.query(Event).filter(Event.id == event_id).first()
        if event:
            event.processing_status = "PROCESSED"
            event.processed_at = datetime.utcnow()
            self.db.commit()
    
    async def close_all(self):
        """Close all feed source connections."""
        for source in self.sources:
            if hasattr(source, 'close'):
                await source.close()

