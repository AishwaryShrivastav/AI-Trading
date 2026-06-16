"""Risk governor API — drawdown protocol state, evaluation, and RESUME (Step 4a)."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.risk_governor import RiskGovernor

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/state")
def get_state(db: Session = Depends(get_db)):
    """Current system risk state (ACTIVE / DERISK / HALTED) + last diagnosis."""
    return RiskGovernor(db).get_state()


@router.post("/evaluate")
async def evaluate(account_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Recompute drawdown and advance the state machine. Returns the new state."""
    return await RiskGovernor(db).evaluate(account_id=account_id)


@router.post("/resume")
def resume(db: Session = Depends(get_db)):
    """Human RESUME — clears a HALTED state and starts the reduced-sizing window."""
    return RiskGovernor(db).resume()
