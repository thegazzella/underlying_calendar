"""
underlying_calendar.trading_calendar
=====================================
A lean, efficient trading calendar.

Design
------
- TradingCalendar is a concrete class instantiated directly with weekends,
  holidays, market open/close times, early close days, and a single early
  close time that applies to all early close days.
- Weekends and holidays are stored as frozensets for O(1) membership tests.
- Early close days are stored as a frozenset; the shared early close time is
  stored as (hour, minute).
- All public date APIs accept and return plain "yyyy-mm-dd" strings.
  datetime and zoneinfo are used internally only.
- market_open() and market_close() return UTC ISO 8601 strings, handling
  DST automatically via the IANA timezone database.

Rolling conventions
-------------------
    "following"          Next trading day.
    "previous"           Previous trading day.
    "modified_following" Following, unless it crosses into the next month —
                         then previous. (ISDA standard)
    "modified_previous"  Previous, unless it crosses into the prior month —
                         then following.

Usage
-----
    import pandas_market_calendars as mcal
    import pandas as pd
    from underlying_calendar import TradingCalendar

    nyse  = mcal.get_calendar("NYSE")
    sched = nyse.schedule("2020-01-01", "2030-12-31")

    all_days = set(pd.date_range("2020-01-01", "2030-12-31").strftime("%Y-%m-%d"))
    trade    = set(sched.index.strftime("%Y-%m-%d"))
    weekends = {d for d in all_days if pd.Timestamp(d).weekday() >= 5}
    holidays = tuple(all_days - trade - weekends)

    early_close_days = tuple(
        row.name.strftime("%Y-%m-%d")
        for _, row in sched.iterrows()
        if row["market_close"].hour < 20   # before 20:00 UTC = before 16:00 ET
    )

    spx_cal = TradingCalendar(
        weekends=(5, 6),
        holidays=holidays,
        timezone="America/New_York",
        open_time="09:30",
        close_time="16:00",
        early_close_days=early_close_days,
        early_close_time="13:00",
    )

    spx_cal.market_open("2026-05-16")    # → "2026-05-16T13:30:00+00:00"
    spx_cal.market_close("2026-05-16")   # → "2026-05-16T20:00:00+00:00"
    spx_cal.market_close("2026-07-03")   # → "2026-07-03T17:00:00+00:00"  (early)
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MONDAY    = 0
TUESDAY   = 1
WEDNESDAY = 2
THURSDAY  = 3
FRIDAY    = 4
SATURDAY  = 5
SUNDAY    = 6

_ROLLING_CONVENTIONS = frozenset({
    "following",
    "previous",
    "modified_following",
    "modified_previous",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse(date: str) -> datetime.date:
    """Parse an ISO 8601 'yyyy-mm-dd' string to datetime.date."""
    try:
        return datetime.date.fromisoformat(date)
    except (ValueError, TypeError):
        raise ValueError(
            f"Cannot parse date {date!r}. Expected 'yyyy-mm-dd', e.g. '2026-05-16'."
        )


def _parse_time(time_str: str, name: str) -> tuple[int, int]:
    """Parse a 'HH:MM' string into (hour, minute). Raises on bad format."""
    try:
        h, m = time_str.split(":")
        hour, minute = int(h), int(m)
    except (ValueError, AttributeError):
        raise ValueError(
            f"{name} must be in 'HH:MM' format, e.g. '09:30'. Got {time_str!r}."
        )
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(
            f"{name}: hour must be 0–23 and minute 0–59, got '{time_str}'."
        )
    return hour, minute


def _fmt(date: datetime.date) -> str:
    return date.strftime("%Y-%m-%d")


def _to_utc(date: str, hour: int, minute: int, tz: ZoneInfo) -> str:
    """Convert a local date + time to a UTC ISO 8601 string."""
    d = _parse(date)
    local_dt = datetime.datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
    return local_dt.astimezone(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# TradingCalendar
# ---------------------------------------------------------------------------

class TradingCalendar:
    """
    A trading calendar with market hours, holidays, and early close support.

    All membership tests are O(1) via frozensets. market_open() and
    market_close() return UTC ISO 8601 strings, handling DST automatically.

    Parameters
    ----------
    weekends : iterable of int
        ISO weekday numbers of structural non-trading days (0=Mon … 6=Sun).
        Standard western markets: (5, 6).
    holidays : iterable of str
        Non-trading dates in "yyyy-mm-dd" format. Duplicates ignored.
    timezone : str
        IANA timezone name for the exchange, e.g. "America/New_York".
    open_time : str
        Regular market open in local time, "HH:MM", e.g. "09:30".
    close_time : str
        Regular market close in local time, "HH:MM", e.g. "16:00".
    early_close_days : iterable of str | None
        Dates when the market closes at early_close_time instead of close_time.
        "yyyy-mm-dd" format. Duplicates ignored.
    early_close_time : str | None
        The single close time applied to all early_close_days, "HH:MM".
        Must be strictly before close_time.
        Required when early_close_days is provided.

    Example
    -------
        cal = TradingCalendar(
            weekends=(5, 6),
            holidays=("2026-01-01", "2026-12-25"),
            timezone="America/New_York",
            open_time="09:30",
            close_time="16:00",
            early_close_days=("2026-07-03", "2026-11-27", "2026-12-24"),
            early_close_time="13:00",
        )
        cal.market_close("2026-07-06")   # "2026-07-06T20:00:00+00:00"  (regular)
        cal.market_close("2026-07-03")   # "2026-07-03T17:00:00+00:00"  (early)
    """

    __slots__ = (
        "_weekends",
        "_holidays",
        "_tz",
        "_open_h", "_open_m",
        "_close_h", "_close_m",
        "_early_close_days",
        "_early_close_h", "_early_close_m",
    )

    def __init__(
        self,
        weekends: tuple[int, ...],
        holidays: tuple[str, ...] = (),
        timezone: str = "America/New_York",
        open_time: str = "09:30",
        close_time: str = "16:00",
        early_close_days: tuple[str, ...] | None = None,
        early_close_time: str | None = None,
    ) -> None:
        # --- weekends ---
        invalid = set(weekends) - set(range(7))
        if invalid:
            raise ValueError(
                f"Invalid weekday numbers: {invalid}. Must be in 0–6 (Mon–Sun)."
            )

        # --- holidays ---
        for h in holidays:
            _parse(h)

        # --- open / close times ---
        open_h,  open_m  = _parse_time(open_time,  "open_time")
        close_h, close_m = _parse_time(close_time, "close_time")
        if (open_h, open_m) >= (close_h, close_m):
            raise ValueError(
                f"open_time ({open_time}) must be before close_time ({close_time})."
            )

        # --- early close ---
        if early_close_days and early_close_time is None:
            raise ValueError(
                "early_close_time must be provided when early_close_days is set."
            )
        if early_close_time and not early_close_days:
            raise ValueError(
                "early_close_days must be provided when early_close_time is set."
            )

        early_close_h, early_close_m = 0, 0
        if early_close_time:
            early_close_h, early_close_m = _parse_time(early_close_time, "early_close_time")
            if (early_close_h, early_close_m) >= (close_h, close_m):
                raise ValueError(
                    f"early_close_time ({early_close_time}) must be before "
                    f"close_time ({close_time})."
                )

        for d in (early_close_days or ()):
            _parse(d)   # validate format

        self._weekends:      frozenset[int] = frozenset(weekends)
        self._holidays:      frozenset[str] = frozenset(holidays)
        self._tz:            ZoneInfo       = ZoneInfo(timezone)
        self._open_h:        int            = open_h
        self._open_m:        int            = open_m
        self._close_h:       int            = close_h
        self._close_m:       int            = close_m
        self._early_close_days: frozenset[str] = frozenset(early_close_days or ())
        self._early_close_h: int            = early_close_h
        self._early_close_m: int            = early_close_m

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def weekends(self) -> frozenset[int]:
        return self._weekends

    @property
    def holidays(self) -> frozenset[str]:
        return self._holidays

    @property
    def early_close_days(self) -> frozenset[str]:
        return self._early_close_days

    @property
    def early_close_time(self) -> str | None:
        """Early close time as 'HH:MM' local string, or None if not set."""
        if not self._early_close_days:
            return None
        return f"{self._early_close_h:02d}:{self._early_close_m:02d}"

    # ------------------------------------------------------------------
    # Core predicates  (all O(1))
    # ------------------------------------------------------------------

    def is_weekend(self, date: str) -> bool:
        return _parse(date).weekday() in self._weekends

    def is_holiday(self, date: str) -> bool:
        return date in self._holidays

    def is_early_close(self, date: str) -> bool:
        """Return True if *date* is an early close day."""
        return date in self._early_close_days

    def is_trading_day(self, date: str) -> bool:
        d = _parse(date)
        return d.weekday() not in self._weekends and date not in self._holidays

    # ------------------------------------------------------------------
    # Market hours
    # ------------------------------------------------------------------

    def market_open(self, date: str) -> str:
        """
        Return the market open time for *date* as a UTC ISO 8601 string.

        Raises ValueError if *date* is not a trading day.
        """
        if not self.is_trading_day(date):
            raise ValueError(f"{date} is not a trading day.")
        return _to_utc(date, self._open_h, self._open_m, self._tz)

    def market_close(self, date: str) -> str:
        """
        Return the market close time for *date* as a UTC ISO 8601 string.

        Returns early_close_time when *date* is in early_close_days,
        otherwise returns the regular close time.
        Raises ValueError if *date* is not a trading day.
        """
        if not self.is_trading_day(date):
            raise ValueError(f"{date} is not a trading day.")
        if date in self._early_close_days:
            return _to_utc(date, self._early_close_h, self._early_close_m, self._tz)
        return _to_utc(date, self._close_h, self._close_m, self._tz)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def next_trading_day(self, date: str) -> str:
        """Return the first trading day strictly after *date*."""
        d = _parse(date) + datetime.timedelta(days=1)
        while d.weekday() in self._weekends or _fmt(d) in self._holidays:
            d += datetime.timedelta(days=1)
        return _fmt(d)

    def previous_trading_day(self, date: str) -> str:
        """Return the last trading day strictly before *date*."""
        d = _parse(date) - datetime.timedelta(days=1)
        while d.weekday() in self._weekends or _fmt(d) in self._holidays:
            d -= datetime.timedelta(days=1)
        return _fmt(d)

    def add_trading_days(self, date: str, n: int) -> str:
        """
        Advance *date* by *n* trading days (*n* may be negative).

        *date* itself is not counted; movement starts from the next/previous day.
        """
        if not isinstance(n, int):
            raise TypeError(f"n must be an int, got {type(n)}")
        d = _parse(date)
        step = 1 if n >= 0 else -1
        remaining = abs(n)
        while remaining:
            d += datetime.timedelta(days=step)
            if d.weekday() not in self._weekends and _fmt(d) not in self._holidays:
                remaining -= 1
        return _fmt(d)

    def trading_days_between(self, start: str, end: str) -> int:
        """
        Count trading days strictly between *start* (exclusive) and
        *end* (inclusive).
 
        This matches the natural interpretation of "days to expiry":
        if today is Monday and expiry is Wednesday, the answer is 2
        (Tuesday and Wednesday), not 3.
 
        Parameters
        ----------
        start : str
            Start date in "yyyy-mm-dd" format (not counted).
        end : str
            End date in "yyyy-mm-dd" format (counted if it is a trading day).
 
        Returns
        -------
        int
            Number of trading days in (start, end].
 
        Raises
        ------
        ValueError
            If *end* is before or equal to *start*.
 
        Examples
        --------
            # Monday to Wednesday → 2 (Tue, Wed)
            cal.trading_days_between("2022-01-03", "2022-01-05")
 
            # Friday to Monday → 1 (Mon only — weekend skipped)
            cal.trading_days_between("2022-01-07", "2022-01-10")
        """
        s, e = _parse(start), _parse(end)
        if e <= s:
            raise ValueError(
                f"end ({end}) must be strictly after start ({start})."
            )
        count = 0
        d = s + datetime.timedelta(days=1)
        while d <= e:
            if d.weekday() not in self._weekends and _fmt(d) not in self._holidays:
                count += 1
            d += datetime.timedelta(days=1)
        return count
 
    # ------------------------------------------------------------------
    # Rolling conventions
    # ------------------------------------------------------------------

    def roll(self, date: str, convention: str = "modified_following") -> str:
        """
        Roll *date* to a trading day using the specified convention.

        Returns *date* unchanged if it is already a trading day.

        Parameters
        ----------
        convention : str
            One of "following", "previous", "modified_following",
            "modified_previous".
        """
        convention = convention.lower().strip()
        if convention not in _ROLLING_CONVENTIONS:
            raise ValueError(
                f"Unknown convention {convention!r}. "
                f"Choose from: {sorted(_ROLLING_CONVENTIONS)}"
            )

        if self.is_trading_day(date):
            return date

        d = _parse(date)

        if convention == "following":
            return self._roll_following(d)

        if convention == "previous":
            return self._roll_previous(d)

        if convention == "modified_following":
            candidate = self._roll_following(d)
            if _parse(candidate).month == d.month:
                return candidate
            return self._roll_previous(d)

        # modified_previous
        candidate = self._roll_previous(d)
        if _parse(candidate).month == d.month:
            return candidate
        return self._roll_following(d)

    def _roll_following(self, d: datetime.date) -> str:
        d += datetime.timedelta(days=1)
        while d.weekday() in self._weekends or _fmt(d) in self._holidays:
            d += datetime.timedelta(days=1)
        return _fmt(d)

    def _roll_previous(self, d: datetime.date) -> str:
        d -= datetime.timedelta(days=1)
        while d.weekday() in self._weekends or _fmt(d) in self._holidays:
            d -= datetime.timedelta(days=1)
        return _fmt(d)

    # ------------------------------------------------------------------
    # Schedule builder
    # ------------------------------------------------------------------

    def schedule(self, start: str, end: str) -> list[str]:
        """
        Build a sorted list of every trading day in [start, end].

        Parameters
        ----------
        start, end : str
            Inclusive date range in "yyyy-mm-dd" format.

        Returns
        -------
        list[str]
            Sorted list of "yyyy-mm-dd" strings.
        """
        s, e = _parse(start), _parse(end)
        if s > e:
            raise ValueError(f"start ({start}) must be <= end ({end})")
        dates = []
        d = s
        while d <= e:
            if d.weekday() not in self._weekends and _fmt(d) not in self._holidays:
                dates.append(_fmt(d))
            d += datetime.timedelta(days=1)
        return dates

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        early = (
            f"early_close={self.early_close_time} "
            f"({len(self._early_close_days)} dates)"
            if self._early_close_days else "no early closes"
        )
        return (
            f"TradingCalendar("
            f"weekends={sorted(self._weekends)}, "
            f"holidays={len(self._holidays)} dates, "
            f"open={self._open_h:02d}:{self._open_m:02d}, "
            f"close={self._close_h:02d}:{self._close_m:02d}, "
            f"{early})"
        )