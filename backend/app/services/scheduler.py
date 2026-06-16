"""Market-aware scheduler service (TradeHarness Step 5).

Wraps APScheduler's AsyncIOScheduler with the NSE trading timetable.
All job times are in IST (Asia/Kolkata).

Usage:
    svc = SchedulerService.get()
    svc.start()   # call from FastAPI lifespan startup
    svc.shutdown()  # call from FastAPI lifespan shutdown
"""
import logging
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_IST = "Asia/Kolkata"
_TOTAL_JOBS = 11  # 10 cron + 1 heartbeat interval


class SchedulerService:
    """Singleton scheduler — call :meth:`get` for the shared instance."""

    _instance: Optional["SchedulerService"] = None

    def __init__(self):
        self._sched = AsyncIOScheduler(timezone=_IST)
        self._running = False

    @classmethod
    def get(cls) -> "SchedulerService":
        """Return the process-wide singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------ control

    def start(self) -> None:
        """Register all market-hours jobs and start the underlying scheduler."""
        if self._running:
            logger.warning("[SCHEDULER] already running — ignoring duplicate start()")
            return
        self._register_jobs()
        self._sched.start()
        self._running = True
        logger.info("[SCHEDULER] Started — IST timetable active (%d jobs)", len(self._sched.get_jobs()))

    def shutdown(self) -> None:
        """Gracefully stop the scheduler (no wait for running jobs)."""
        if self._running:
            self._sched.shutdown(wait=False)
            self._running = False
            logger.info("[SCHEDULER] Stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def job_status(self) -> List[Dict[str, Any]]:
        """Return registered jobs with their next scheduled run times."""
        return [
            {
                "id": j.id,
                "name": j.name,
                "next_run": str(j.next_run_time) if j.next_run_time else None,
            }
            for j in self._sched.get_jobs()
        ]

    # ------------------------------------------------------------------ timetable

    def _register_jobs(self) -> None:
        from .market_jobs import (
            job_token_refresh,
            job_pre_market,
            job_morning_briefing,
            job_market_open,
            job_checkpoint,
            job_force_exit,
            job_eod_report,
            job_eod_reflection,
            job_heartbeat,
        )

        def _cron(hour: int, minute: int) -> CronTrigger:
            return CronTrigger(hour=hour, minute=minute, timezone=_IST)

        # NSE market timetable (all times IST)
        self._sched.add_job(job_token_refresh,   _cron(7,  55), id="token_refresh",    name="Token refresh 07:55")
        self._sched.add_job(job_pre_market,       _cron(8,  30), id="pre_market",       name="Pre-market 08:30")
        self._sched.add_job(job_morning_briefing, _cron(9,   0), id="morning_briefing", name="Morning briefing 09:00")
        self._sched.add_job(job_market_open,      _cron(9,  15), id="market_open",      name="Market open 09:15")
        self._sched.add_job(job_checkpoint,       _cron(11,  0), id="chk_1100",         name="Checkpoint 11:00")
        self._sched.add_job(job_checkpoint,       _cron(13,  0), id="chk_1300",         name="Checkpoint 13:00")
        self._sched.add_job(job_checkpoint,       _cron(14, 30), id="chk_1430",         name="Checkpoint 14:30")
        self._sched.add_job(job_force_exit,       _cron(15, 10), id="force_exit",       name="Force-exit 15:10")
        self._sched.add_job(job_eod_report,       _cron(15, 30), id="eod_report",       name="EOD report 15:30")
        self._sched.add_job(job_eod_reflection,   _cron(16, 30), id="eod_reflection",   name="EOD reflection 16:30")
        # Dead-man's switch heartbeat every 5 minutes
        self._sched.add_job(
            job_heartbeat,
            IntervalTrigger(minutes=5),
            id="heartbeat",
            name="Heartbeat 5min",
        )
