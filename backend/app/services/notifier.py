"""SSE broadcaster for the HIL relay (TradeHarness Step 6).

Call Notifier.get().send(event_type, data) from anywhere (jobs, pipeline, risk
governor) to push real-time events to all connected /api/hil/stream clients.
Stale queues (full = client too slow / disconnected) are pruned automatically.
"""
import asyncio
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Canonical event types emitted by the system
NEW_CARD = "new_card"
CARD_APPROVED = "card_approved"
CARD_REJECTED = "card_rejected"
RISK_ALERT = "risk_alert"
MORNING_BRIEFING = "morning_briefing"
FORCE_EXIT = "force_exit"
EOD_REPORT = "eod_report"
HEARTBEAT_ALERT = "heartbeat_alert"


class Notifier:
    """Process-wide pub/sub broadcaster. One queue per SSE client.

    Each call to :meth:`subscribe` returns a new ``asyncio.Queue``;
    :meth:`send` pushes to every live queue. Full queues (client lagging) are
    dropped automatically to avoid blocking the caller.
    """

    _instance: "Notifier | None" = None

    def __init__(self) -> None:
        self._queues: List[asyncio.Queue] = []

    @classmethod
    def get(cls) -> "Notifier":
        """Return the process-wide singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------ pub/sub

    def subscribe(self) -> asyncio.Queue:
        """Register a new SSE client. Returns the queue to read events from."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Deregister an SSE client (called when the HTTP connection closes)."""
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    async def send(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcast an event to all connected clients.

        Full queues (client disconnected or too slow) are silently removed.
        """
        if not self._queues:
            return
        payload = {"type": event_type, "data": data}
        stale: List[asyncio.Queue] = []
        for q in self._queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                stale.append(q)
        for q in stale:
            self.unsubscribe(q)
        live = len(self._queues)
        if live:
            logger.debug("[NOTIFIER] '%s' → %d client(s)", event_type, live)

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)
