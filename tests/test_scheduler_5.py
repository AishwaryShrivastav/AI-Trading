"""Tests for Step 5: NSE calendar, market job functions, dead-man's switch, scheduler."""
import pytest
from datetime import date, datetime
import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


# ======================================================================= NSE calendar
from backend.app.services.nse_calendar import is_nse_holiday, is_market_hours, ist_now


def test_saturday_is_holiday():
    assert is_nse_holiday(date(2026, 6, 13))  # Saturday


def test_sunday_is_holiday():
    assert is_nse_holiday(date(2026, 6, 14))  # Sunday


def test_republic_day_is_holiday():
    assert is_nse_holiday(date(2026, 1, 26))


def test_normal_monday_not_holiday():
    assert not is_nse_holiday(date(2026, 6, 15))  # Monday, not a holiday


def test_market_hours_mid_session():
    dt = datetime(2026, 6, 16, 10, 30, tzinfo=IST)
    assert is_market_hours(dt) is True


def test_market_hours_at_open():
    dt = datetime(2026, 6, 16, 9, 15, tzinfo=IST)
    assert is_market_hours(dt) is True


def test_market_hours_before_open():
    dt = datetime(2026, 6, 16, 9, 0, tzinfo=IST)
    assert is_market_hours(dt) is False


def test_market_hours_after_close():
    dt = datetime(2026, 6, 16, 16, 0, tzinfo=IST)
    assert is_market_hours(dt) is False


def test_market_hours_on_holiday():
    dt = datetime(2026, 1, 26, 10, 0, tzinfo=IST)  # Republic Day
    assert is_market_hours(dt) is False


def test_market_hours_on_weekend():
    dt = datetime(2026, 6, 13, 10, 0, tzinfo=IST)  # Saturday
    assert is_market_hours(dt) is False


def test_ist_now_is_aware():
    now = ist_now()
    assert now.tzinfo is not None


# ======================================================================= DB fixtures
from backend.app.database import SessionLocal, Setting, PositionV2


@pytest.fixture(autouse=False)
def clean_scheduler_settings():
    keys = [
        "market_window_open", "morning_briefing", "pre_market_run_at",
        "scheduler_heartbeat", "last_eod_report", "system_state", "equity_peak",
    ]
    db = SessionLocal()
    db.query(Setting).filter(Setting.key.in_(keys)).delete(synchronize_session=False)
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(Setting).filter(Setting.key.in_(keys)).delete(synchronize_session=False)
    db.commit()
    db.close()


# ======================================================================= job_market_open
@pytest.mark.asyncio
async def test_job_market_open_sets_flag(clean_scheduler_settings):
    from backend.app.services.market_jobs import job_market_open
    await job_market_open()
    db = SessionLocal()
    row = db.query(Setting).filter(Setting.key == "market_window_open").first()
    db.close()
    assert row is not None
    assert row.value is True


# ======================================================================= job_morning_briefing
@pytest.mark.asyncio
async def test_job_morning_briefing_stores_briefing(clean_scheduler_settings):
    from backend.app.services.market_jobs import job_morning_briefing
    await job_morning_briefing()
    db = SessionLocal()
    row = db.query(Setting).filter(Setting.key == "morning_briefing").first()
    db.close()
    assert row is not None
    assert isinstance(row.value, dict)
    assert "date" in row.value


# ======================================================================= job_force_exit
@pytest.fixture
def intraday_paper_position():
    db = SessionLocal()
    pos = PositionV2(
        account_id=999990, symbol="FEXIT_TST", exchange="NSE", direction="LONG",
        quantity=5, average_entry_price=100.0, current_price=106.0,
        stop_loss=90.0, is_paper=True, opened_at=datetime.utcnow(),
    )
    db.add(pos)
    db.commit()
    pid = pos.id
    db.close()
    yield pid
    db = SessionLocal()
    db.query(PositionV2).filter(PositionV2.id == pid).delete()
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_job_force_exit_closes_intraday_position(intraday_paper_position, clean_scheduler_settings):
    from unittest.mock import patch
    from backend.app.services.market_jobs import job_force_exit

    # Bypass the time check so the job runs regardless of when the test fires
    with patch("backend.app.services.market_jobs.is_time_exit", return_value=True):
        await job_force_exit()

    db = SessionLocal()
    pos = db.query(PositionV2).filter(PositionV2.id == intraday_paper_position).first()
    db.close()

    assert pos.closed_at is not None
    assert pos.realized_pnl == pytest.approx(30.0)  # (106 - 100) * 5


@pytest.mark.asyncio
async def test_job_force_exit_skips_when_not_time(intraday_paper_position, clean_scheduler_settings):
    from unittest.mock import patch
    from backend.app.services.market_jobs import job_force_exit

    with patch("backend.app.services.market_jobs.is_time_exit", return_value=False):
        await job_force_exit()

    db = SessionLocal()
    pos = db.query(PositionV2).filter(PositionV2.id == intraday_paper_position).first()
    db.close()
    assert pos.closed_at is None  # should NOT have been closed


# ======================================================================= job_checkpoint
@pytest.fixture
def paper_position_with_gain():
    db = SessionLocal()
    pos = PositionV2(
        account_id=999991, symbol="CHKPNT_TST", exchange="NSE", direction="LONG",
        quantity=10, average_entry_price=100.0, current_price=105.0,
        stop_loss=95.0, is_paper=True,
    )
    db.add(pos)
    db.commit()
    pid = pos.id
    db.close()
    yield pid
    db = SessionLocal()
    db.query(PositionV2).filter(PositionV2.id == pid).delete()
    db.commit()
    # also clean risk state
    db.query(Setting).filter(Setting.key.in_(["system_state", "equity_peak"])).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_job_checkpoint_ratchets_trailing_stop(paper_position_with_gain, clean_scheduler_settings):
    from backend.app.services.market_jobs import job_checkpoint
    await job_checkpoint()

    db = SessionLocal()
    pos = db.query(PositionV2).filter(PositionV2.id == paper_position_with_gain).first()
    db.close()
    # +5% gain from 100→105, activate=2%, lock=50% -> new SL = 100 + 5*0.5 = 102.5
    assert pos.stop_loss == pytest.approx(102.5)


# ======================================================================= dead-man's switch
def test_heartbeat_record_not_stale(clean_scheduler_settings):
    from backend.app.services.market_jobs import _record_heartbeat, _check_heartbeat_staleness
    db = SessionLocal()
    _record_heartbeat(db)
    stale = _check_heartbeat_staleness(db, max_age_minutes=30)
    db.close()
    assert stale is False


def test_heartbeat_missing_is_not_stale(clean_scheduler_settings):
    # No heartbeat recorded yet → not stale (system just started)
    from backend.app.services.market_jobs import _check_heartbeat_staleness
    db = SessionLocal()
    stale = _check_heartbeat_staleness(db, max_age_minutes=30)
    db.close()
    assert stale is False


# ======================================================================= scheduler lifecycle
@pytest.mark.asyncio
async def test_scheduler_starts_has_twelve_jobs_and_stops():
    from backend.app.services.scheduler import SchedulerService
    svc = SchedulerService()  # fresh instance (not the singleton)
    assert not svc.is_running
    svc.start()
    assert svc.is_running
    jobs = svc.job_status()
    assert len(jobs) == 12  # 11 cron + 1 heartbeat interval
    svc.shutdown()
    assert not svc.is_running


@pytest.mark.asyncio
async def test_scheduler_double_start_is_noop():
    from backend.app.services.scheduler import SchedulerService
    svc = SchedulerService()
    svc.start()
    svc.start()  # second call should be ignored, not raise
    assert svc.is_running
    svc.shutdown()
