"""NSE trading calendar: holidays, market hours, IST helpers (Step 5).

Pure functions — no DB, no network. Update _NSE_HOLIDAYS_2026 annually from
https://www.nseindia.com/trade/exchange-market-timings-holidays.htm
"""
from datetime import date, datetime, time
from typing import Optional, Set
import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)

# NSE equity-segment holidays for 2026 (confirm each year from NSE official list)
_NSE_HOLIDAYS_2026: Set[date] = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 23),   # Holi
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day / Labour Day
    date(2026, 7, 6),    # Bakri Eid (approximate — verify against Islamic calendar)
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti / Dussehra
    date(2026, 10, 23),  # Diwali Laxmi Puja (approximate — verify annually)
    date(2026, 11, 14),  # Gurunanak Jayanti (approximate — verify annually)
    date(2026, 12, 25),  # Christmas
}


def is_nse_holiday(d: Optional[date] = None) -> bool:
    """True if the given date (default: today IST) is an NSE holiday or weekend."""
    d = d or datetime.now(IST).date()
    return d.weekday() >= 5 or d in _NSE_HOLIDAYS_2026


def is_market_hours(dt: Optional[datetime] = None) -> bool:
    """True if dt is within NSE trading hours on a trading day.

    dt is converted to IST if it carries tzinfo; naive dt is assumed IST.
    Defaults to now (IST) if omitted.
    """
    if dt is None:
        dt = datetime.now(IST)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    return not is_nse_holiday(dt.date()) and _MARKET_OPEN <= dt.time() <= _MARKET_CLOSE


def ist_now() -> datetime:
    """Current datetime in IST (timezone-aware)."""
    return datetime.now(IST)
