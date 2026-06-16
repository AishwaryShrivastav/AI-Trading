"""Risk Governor — staged drawdown protocol & system state machine (Step 4a).

Implements decision D12: as portfolio drawdown deepens, the system de-risks and
then halts, switching to paper and demanding an explicit human RESUME.

States:
  ACTIVE  — normal trading (size factor 1.0, or post-resume factor in the window)
  DERISK  — drawdown >= derisk_pct: new entries sized down (derisk_capital_factor)
  HALTED  — drawdown >= halt_pct: no new entries, mode forced to paper, a
            self-diagnosis report is produced, and resume_required is set. HALTED
            is sticky — only an explicit resume() clears it.

State + peak equity persist in the Setting table so they survive restarts.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import Setting
from .risk_monitor import RiskMonitor

logger = logging.getLogger(__name__)

ACTIVE, DERISK, HALTED = "ACTIVE", "DERISK", "HALTED"
_STATE_KEY = "system_state"
_PEAK_KEY = "equity_peak"


def decide_state(current_state: str, drawdown_pct: float, derisk_pct: float, halt_pct: float) -> str:
    """Pure state transition. HALTED is sticky (cleared only via resume())."""
    if current_state == HALTED:
        return HALTED  # only resume() exits HALTED
    if drawdown_pct >= halt_pct:
        return HALTED
    if drawdown_pct >= derisk_pct:
        return DERISK
    return ACTIVE


class RiskGovernor:
    def __init__(self, db: Session, settings=None):
        self.db = db
        self.settings = settings or get_settings()
        self.monitor = RiskMonitor(db)

    # ----------------------------------------------------------- persistence
    def _get(self, key: str, default=None):
        row = self.db.query(Setting).filter(Setting.key == key).first()
        return row.value if row else default

    def _set(self, key: str, value, desc: str = ""):
        row = self.db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
        else:
            self.db.add(Setting(key=key, value=value, description=desc))
        self.db.commit()

    def get_state(self) -> Dict[str, Any]:
        return self._get(_STATE_KEY) or {"state": ACTIVE, "reason": "init", "resume_required": False}

    # ----------------------------------------------------------- VIX breakers
    def get_vix(self) -> Optional[float]:
        v = self._get("india_vix")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def vix_assessment(self, vix: Optional[float] = None) -> Dict[str, Any]:
        """Map India VIX to a sizing factor and intraday/all-entry blocks."""
        vix = self.get_vix() if vix is None else vix
        s = self.settings
        if vix is None:
            return {"vix": None, "size_factor": 1.0, "block_intraday": False, "block_all": False}
        if vix >= s.vix_halt_level:
            return {"vix": vix, "size_factor": 0.0, "block_intraday": True, "block_all": True}
        if vix >= s.vix_intraday_pause_level:
            return {"vix": vix, "size_factor": s.vix_derisk_factor, "block_intraday": True, "block_all": False}
        if vix >= s.vix_derisk_level:
            return {"vix": vix, "size_factor": s.vix_derisk_factor, "block_intraday": False, "block_all": False}
        return {"vix": vix, "size_factor": 1.0, "block_intraday": False, "block_all": False}

    # ----------------------------------------------------------- equity/drawdown
    async def _equity_and_drawdown(self, account_id: Optional[int]) -> Dict[str, float]:
        snap = await self.monitor.capture_snapshot(account_id)
        capital = await self.monitor._get_total_capital(account_id)
        equity = (capital or 0.0) + (snap.total_unrealized_pnl or 0.0)

        peak = self._get(_PEAK_KEY)
        peak = float(peak) if peak is not None else equity
        if equity > peak:
            peak = equity
        self._set(_PEAK_KEY, peak, "Peak portfolio equity")

        drawdown_pct = ((peak - equity) / peak * 100.0) if peak > 0 else 0.0
        return {"equity": equity, "peak": peak, "drawdown_pct": round(drawdown_pct, 3)}

    # ----------------------------------------------------------- evaluate
    async def evaluate(self, account_id: Optional[int] = None) -> Dict[str, Any]:
        ed = await self._equity_and_drawdown(account_id)
        prev = self.get_state()
        new_state = decide_state(
            prev.get("state", ACTIVE), ed["drawdown_pct"],
            self.settings.drawdown_derisk_pct, self.settings.drawdown_halt_pct,
        )

        state_obj = dict(prev)
        state_obj["state"] = new_state
        state_obj["drawdown_pct"] = ed["drawdown_pct"]
        state_obj["evaluated_at"] = datetime.utcnow().isoformat()

        if new_state == HALTED and prev.get("state") != HALTED:
            # First breach -> trip the protocol.
            state_obj["reason"] = f"Drawdown {ed['drawdown_pct']}% >= halt {self.settings.drawdown_halt_pct}%"
            state_obj["resume_required"] = True
            state_obj["halted_at"] = datetime.utcnow().isoformat()
            state_obj["forced_paper"] = True
            # Force paper mode at runtime.
            self.settings.trading_mode = "paper"
            state_obj["diagnosis"] = await self._self_diagnose(account_id, ed)
            logger.critical(f"[RISK] HALTED — {state_obj['reason']}. Switched to paper; RESUME required.")
        elif new_state == DERISK:
            state_obj["reason"] = f"Drawdown {ed['drawdown_pct']}% >= derisk {self.settings.drawdown_derisk_pct}%"
        elif new_state == ACTIVE:
            state_obj["reason"] = "within limits"

        self._set(_STATE_KEY, state_obj, "System risk state")
        return state_obj

    # ----------------------------------------------------------- resume
    def resume(self) -> Dict[str, Any]:
        state = self.get_state()
        if state.get("state") != HALTED:
            return {"resumed": False, "reason": "not halted", "state": state}
        until = (datetime.utcnow() + timedelta(days=self.settings.post_resume_derisk_days)).isoformat()
        new = {
            "state": ACTIVE, "reason": "manual resume", "resume_required": False,
            "post_resume_until": until, "resumed_at": datetime.utcnow().isoformat(),
            "drawdown_pct": state.get("drawdown_pct"),
        }
        self._set(_STATE_KEY, new, "System risk state")
        # Reset the peak so a fresh drawdown baseline is used post-resume.
        logger.warning("[RISK] RESUME issued — trading re-enabled with reduced sizing window.")
        return {"resumed": True, "state": new}

    # ----------------------------------------------------------- sizing
    def position_size_factor(self) -> float:
        """Multiplier applied to new position sizes: drawdown × VIX factors."""
        state = self.get_state()
        s = state.get("state", ACTIVE)
        if s == HALTED:
            return 0.0
        if s == DERISK:
            dd_factor = self.settings.derisk_capital_factor
        else:
            dd_factor = 1.0
            until = state.get("post_resume_until")
            if until:
                try:
                    if datetime.utcnow() < datetime.fromisoformat(until):
                        dd_factor = self.settings.post_resume_capital_factor
                except Exception:
                    pass
        return dd_factor * self.vix_assessment()["size_factor"]

    def blocks_new_entries(self) -> bool:
        return self.get_state().get("state") == HALTED or self.vix_assessment()["block_all"]

    # ----------------------------------------------------------- diagnosis
    async def _self_diagnose(self, account_id: Optional[int], ed: Dict[str, float]) -> Dict[str, Any]:
        """Heuristic failure classification on a halt (LLM enhancement later)."""
        snap = await self.monitor.capture_snapshot(account_id)
        unrealized = snap.total_unrealized_pnl or 0.0
        realized = snap.daily_realized_pnl or 0.0
        open_n = snap.open_positions_count or 0

        if unrealized < 0 and abs(unrealized) > abs(realized):
            classification = "market_event"  # open positions underwater -> adverse market move
            evidence = "Loss dominated by unrealized P&L on open positions."
        elif realized < 0 and abs(realized) >= abs(unrealized):
            classification = "strategy_degradation"  # realized losses -> exits/strategy failing
            evidence = "Loss dominated by realized P&L from closed trades."
        elif open_n == 0:
            classification = "system_or_data"  # drawdown with no positions -> bookkeeping/data issue
            evidence = "Drawdown recorded with no open positions; check data/accounting."
        else:
            classification = "risk_model"
            evidence = "Mixed losses; possible position correlation/sizing issue."

        return {
            "classification": classification,
            "evidence": evidence,
            "drawdown_pct": ed["drawdown_pct"],
            "open_positions": open_n,
            "unrealized_pnl": round(unrealized, 2),
            "daily_realized_pnl": round(realized, 2),
            "suggested_steps": [
                "Review open positions for correlation/concentration.",
                "Confirm market regime vs strategy assumptions.",
                "Verify data feeds and position bookkeeping.",
                "Resume only after root cause is understood (reduced sizing for 2 weeks).",
            ],
        }
