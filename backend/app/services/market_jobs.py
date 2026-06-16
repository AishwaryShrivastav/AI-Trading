"""Market-hours job functions for APScheduler (TradeHarness Step 5).

Each function is a standalone async callable invoked by the scheduler at its
scheduled time. All functions:
  - Guard against NSE holidays / weekends (return early if not a trading day).
  - Use a fresh SessionLocal() so they are independent of request context.
  - Swallow all exceptions — a job failure must never crash the scheduler.

Dead-man's switch: job_heartbeat fires every 5 minutes during market hours and
records a timestamp.  _check_heartbeat_staleness() logs CRITICAL if no heartbeat
was recorded for > heartbeat_max_age_minutes.
"""
import json
import logging
from datetime import date, datetime
from typing import Any, Dict, Optional

from ..database import SessionLocal, Setting, PositionV2
from .nse_calendar import is_nse_holiday, is_market_hours, ist_now
from .stop_engine import manage_trailing_stops, is_time_exit

logger = logging.getLogger(__name__)

_HEARTBEAT_KEY = "scheduler_heartbeat"
_MARKET_WINDOW_KEY = "market_window_open"


# ------------------------------------------------------------------ helpers

def _upsert(db, key: str, value) -> None:
    """Insert-or-update a Setting row."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value, description="set by scheduler"))
    db.commit()


def _record_heartbeat(db) -> None:
    _upsert(db, _HEARTBEAT_KEY, ist_now().isoformat())


def _check_heartbeat_staleness(db, max_age_minutes: Optional[int] = None) -> bool:
    """Return True (and log CRITICAL) if last heartbeat is too old."""
    from ..config import get_settings
    if max_age_minutes is None:
        max_age_minutes = get_settings().heartbeat_max_age_minutes

    row = db.query(Setting).filter(Setting.key == _HEARTBEAT_KEY).first()
    if not row or not row.value:
        return False  # no heartbeat yet; system just started

    try:
        last = datetime.fromisoformat(str(row.value))
        if last.tzinfo is None:
            from .nse_calendar import IST
            last = last.replace(tzinfo=IST)
        age_min = (ist_now() - last).total_seconds() / 60.0
        if age_min > max_age_minutes:
            logger.critical(
                "[DEAD-MAN'S SWITCH] Heartbeat is %.1f min old (limit %d min). "
                "Scheduler may have been down during market hours.",
                age_min, max_age_minutes,
            )
            return True
    except Exception:
        pass
    return False


def check_missed_heartbeat(db=None) -> Dict[str, Any]:
    """Called on app startup: alert if we missed heartbeats during market hours."""
    if not is_market_hours():
        return {"stale": False, "reason": "outside market hours"}
    close_db = db is None
    db = db or SessionLocal()
    try:
        stale = _check_heartbeat_staleness(db)
        return {"stale": stale, "reason": "heartbeat stale" if stale else "ok"}
    finally:
        if close_db:
            db.close()


# ------------------------------------------------------------------ jobs

async def job_token_refresh() -> None:
    """07:55 IST — Refresh Upstox access token from stored refresh token."""
    if is_nse_holiday():
        logger.debug("[JOB] token_refresh skipped — holiday/weekend")
        return
    db = SessionLocal()
    try:
        from ..config import get_settings
        from .broker.upstox import UpstoxBroker
        settings = get_settings()

        refresh_row = db.query(Setting).filter(Setting.key == "upstox_refresh_token").first()
        if not refresh_row or not refresh_row.value:
            logger.info("[JOB] token_refresh: no refresh token stored — skipping")
            return

        broker = UpstoxBroker(
            api_key=settings.upstox_api_key,
            api_secret=settings.upstox_api_secret,
            redirect_uri=settings.upstox_redirect_uri,
        )
        broker.refresh_token = refresh_row.value
        result = await broker.refresh_access_token()
        if result and result.get("access_token"):
            _upsert(db, "upstox_access_token", result["access_token"])
            logger.info("[JOB] token_refresh: access token refreshed OK")
        else:
            logger.warning("[JOB] token_refresh: no access_token in response: %s", result)
    except Exception as exc:
        logger.error("[JOB] token_refresh failed: %s", exc)
    finally:
        db.close()


async def job_pre_market() -> None:
    """08:30 IST — Pre-market prep: log watchlist and overnight open-position count."""
    if is_nse_holiday():
        logger.debug("[JOB] pre_market skipped — holiday/weekend")
        return
    db = SessionLocal()
    try:
        from ..config import get_settings
        settings = get_settings()
        watchlist = [s.strip() for s in settings.scheduler_watchlist.split(",") if s.strip()]
        open_n = db.query(PositionV2).filter(
            PositionV2.closed_at.is_(None), PositionV2.is_paper == True  # noqa: E712
        ).count()
        logger.info(
            "[JOB] pre_market: date=%s watchlist=%s open_paper_positions=%d",
            ist_now().date(), watchlist, open_n,
        )
        _upsert(db, "pre_market_run_at", ist_now().isoformat())
    except Exception as exc:
        logger.error("[JOB] pre_market failed: %s", exc)
    finally:
        db.close()


async def job_morning_briefing() -> None:
    """09:00 IST — Morning briefing: snapshot open positions and store to Setting."""
    if is_nse_holiday():
        logger.debug("[JOB] morning_briefing skipped — holiday/weekend")
        return
    db = SessionLocal()
    try:
        from ..config import get_settings
        settings = get_settings()
        positions = db.query(PositionV2).filter(PositionV2.closed_at.is_(None)).all()
        paper_syms = [p.symbol for p in positions if p.is_paper]
        total_unrealized = sum(float(p.unrealized_pnl or 0) for p in positions)
        briefing = {
            "date": ist_now().date().isoformat(),
            "open_paper_positions": len(paper_syms),
            "symbols": paper_syms,
            "total_unrealized_pnl": round(total_unrealized, 2),
            "trading_mode": settings.trading_mode,
        }
        _upsert(db, "morning_briefing", briefing)
        logger.info("[JOB] morning_briefing: %s", briefing)
        from .notifier import Notifier
        await Notifier.get().send("morning_briefing", briefing)
    except Exception as exc:
        logger.error("[JOB] morning_briefing failed: %s", exc)
    finally:
        db.close()


async def job_market_open() -> None:
    """09:15 IST — Mark trading window open."""
    if is_nse_holiday():
        logger.info("[JOB] market_open skipped — holiday/weekend")
        return
    db = SessionLocal()
    try:
        _upsert(db, _MARKET_WINDOW_KEY, True)
        logger.info("[JOB] market_open: trading window opened at %s IST", ist_now().strftime("%H:%M"))
    except Exception as exc:
        logger.error("[JOB] market_open failed: %s", exc)
    finally:
        db.close()


async def job_checkpoint() -> None:
    """11:00 / 13:00 / 14:30 IST — Ratchet trailing stops and re-evaluate risk state."""
    if is_nse_holiday():
        return
    db = SessionLocal()
    try:
        updates = manage_trailing_stops(db)
        if updates:
            logger.info("[JOB] checkpoint: ratcheted %d trailing stop(s)", len(updates))
        else:
            logger.debug("[JOB] checkpoint: no trailing stop changes")

        from .risk_governor import RiskGovernor
        gov = RiskGovernor(db)
        state = await gov.evaluate()
        logger.info(
            "[JOB] checkpoint: risk_state=%s drawdown=%.2f%%",
            state.get("state", "?"), state.get("drawdown_pct", 0),
        )
        _record_heartbeat(db)
    except Exception as exc:
        logger.error("[JOB] checkpoint failed: %s", exc)
    finally:
        db.close()


async def job_force_exit() -> None:
    """15:10 IST — Force-close all intraday paper positions opened today."""
    if is_nse_holiday():
        return
    db = SessionLocal()
    try:
        now_naive = ist_now().replace(tzinfo=None)  # naive IST for is_time_exit
        if not is_time_exit(now_naive, cutoff="15:10"):
            logger.warning("[JOB] force_exit fired but time guard says no — skipping")
            return

        today_utc = datetime.utcnow().date()
        open_positions = (
            db.query(PositionV2)
            .filter(
                PositionV2.closed_at.is_(None),
                PositionV2.is_paper == True,  # noqa: E712
            )
            .all()
        )
        # Close only positions opened today (intraday proxy: opened_at stored UTC)
        intraday = [
            p for p in open_positions
            if p.opened_at and p.opened_at.date() >= today_utc
        ]

        closed = 0
        for pos in intraday:
            exit_price = float(pos.current_price or pos.average_entry_price)
            entry = float(pos.average_entry_price)
            qty = pos.quantity
            direction = (pos.direction or "LONG").upper()
            pnl = (exit_price - entry) * qty if direction in ("LONG", "BUY") else (entry - exit_price) * qty
            pos.closed_at = datetime.utcnow()
            pos.realized_pnl = round(pnl, 2)
            closed += 1

        if closed:
            db.commit()
            logger.info("[JOB] force_exit: closed %d intraday paper position(s) at 15:10 IST", closed)
            from .notifier import Notifier
            await Notifier.get().send("force_exit", {"closed": closed})
        else:
            logger.debug("[JOB] force_exit: no intraday paper positions to close")

        _upsert(db, _MARKET_WINDOW_KEY, False)
    except Exception as exc:
        logger.error("[JOB] force_exit failed: %s", exc)
    finally:
        db.close()


async def job_eod_report() -> None:
    """15:30 IST — Generate EOD P&L report and store summary to Setting."""
    if is_nse_holiday():
        return
    db = SessionLocal()
    try:
        from .reporting_v2 import ReportingServiceV2
        reporter = ReportingServiceV2(db)
        report = await reporter.generate_eod_report(date=datetime.utcnow())
        summary = {
            "generated_at": ist_now().isoformat(),
            "account": report.get("account_name"),
            "closed_trades": report.get("closed_positions_count"),
            "realized_pnl": report.get("total_realized_pnl"),
        }
        _upsert(db, "last_eod_report", summary)
        logger.info("[JOB] eod_report: %s", summary)
        from .notifier import Notifier
        await Notifier.get().send("eod_report", summary)
    except Exception as exc:
        logger.error("[JOB] eod_report failed: %s", exc)
    finally:
        db.close()


async def job_eod_reflection() -> None:
    """16:30 IST — Claude EOD reflection: summarise today's paper trades via LLM."""
    if is_nse_holiday():
        return
    db = SessionLocal()
    try:
        from ..config import get_settings
        settings = get_settings()
        if not settings.anthropic_api_key and not settings.openai_api_key:
            logger.info("[JOB] eod_reflection: no LLM key configured — skipping")
            return

        today_utc = datetime.utcnow().date()
        closed = [
            p for p in db.query(PositionV2).filter(
                PositionV2.is_paper == True,  # noqa: E712
                PositionV2.closed_at.isnot(None),
            ).all()
            if p.closed_at and p.closed_at.date() >= today_utc
        ]
        total_pnl = sum(float(p.realized_pnl or 0) for p in closed)
        summary = {
            "date": ist_now().date().isoformat(),
            "closed_positions": len(closed),
            "total_pnl_inr": round(total_pnl, 2),
            "winners": sum(1 for p in closed if (p.realized_pnl or 0) > 0),
            "losers": sum(1 for p in closed if (p.realized_pnl or 0) < 0),
        }

        from .llm import get_llm_provider
        llm = get_llm_provider()
        reflection = await llm.complete_json(
            system=(
                "You are a trading journal assistant. Given today's paper trading summary, "
                "provide a brief EOD reflection. "
                "Return JSON with keys: observations (list of strings), risk_notes (string), "
                "tomorrow_focus (string)."
            ),
            user=f"Today's paper trading summary: {json.dumps(summary)}",
            max_tokens=512,
        )
        result = {
            "summary": summary,
            "reflection": reflection,
            "generated_at": ist_now().isoformat(),
        }
        _upsert(db, "eod_reflection", result)
        logger.info("[JOB] eod_reflection stored (%d trades, PnL=%.0f INR)", len(closed), total_pnl)
    except Exception as exc:
        logger.error("[JOB] eod_reflection failed: %s", exc)
    finally:
        db.close()


async def job_heartbeat() -> None:
    """Every 5 min — Dead-man's switch: record heartbeat and check for staleness."""
    if is_nse_holiday() or not is_market_hours():
        return
    db = SessionLocal()
    try:
        _record_heartbeat(db)
        _check_heartbeat_staleness(db)
    except Exception as exc:
        logger.error("[JOB] heartbeat failed: %s", exc)
    finally:
        db.close()
