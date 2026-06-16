"""Scheduler status endpoint (Step 5)."""
from fastapi import APIRouter
from typing import Any, Dict

from ..services.scheduler import SchedulerService

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status")
async def scheduler_status() -> Dict[str, Any]:
    """Return whether the scheduler is running and all registered jobs with next fire times."""
    svc = SchedulerService.get()
    return {
        "running": svc.is_running,
        "jobs": svc.job_status(),
    }
