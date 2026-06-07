# underlying_calendar

A lean Python library for trading calendars — market hours, holidays, early closes, and date arithmetic.

## Requirements

Python 3.9+ (uses `zoneinfo`, stdlib since 3.9).

## Installation

```bash
pip install underlying_calendar
```

Or directly from source:

```bash
git clone https://github.com/your-username/underlying_calendar.git
cd underlying_calendar
pip install -e .
```

## Quick start

```python
from underlying_calendar import SPX_CALENDAR

# Check if a date is a trading day
SPX_CALENDAR.is_trading_day("2026-07-04")   # False — Independence Day
SPX_CALENDAR.is_trading_day("2026-07-06")   # True

# Market hours (returned as UTC ISO 8601)
SPX_CALENDAR.market_open("2026-07-06")      # "2026-07-06T13:30:00+00:00"
SPX_CALENDAR.market_close("2026-07-06")     # "2026-07-06T20:00:00+00:00"
SPX_CALENDAR.market_close("2026-07-03")     # "2026-07-03T17:00:00+00:00"  (early close)

# Date navigation
SPX_CALENDAR.next_trading_day("2026-07-04")          # "2026-07-06"
SPX_CALENDAR.previous_trading_day("2026-07-06")      # "2026-07-02"
SPX_CALENDAR.add_trading_days("2026-07-06", 3)       # "2026-07-09"
SPX_CALENDAR.trading_days_between("2026-07-06", "2026-07-10")  # 4

# Rolling conventions
SPX_CALENDAR.roll("2026-07-04")                          # "2026-07-06" (modified_following)
SPX_CALENDAR.roll("2026-07-04", convention="previous")   # "2026-07-02"

# Build a list of trading days
SPX_CALENDAR.schedule("2026-01-01", "2026-01-31")
# ["2026-01-02", "2026-01-05", ..., "2026-01-30"]
```

## Built-in presets

| Name | Description |
|---|---|
| `SPX_CALENDAR` | NYSE/SPX calendar with holidays and early closes (2000–2030) |
| `WEEKDAYS_CALENDAR` | Mon–Fri, no holidays |
| `ALL_DAYS_CALENDAR` | Every calendar day, including weekends |

```python
from underlying_calendar import SPX_CALENDAR, WEEKDAYS_CALENDAR, ALL_DAYS_CALENDAR
```

## Custom calendars

```python
from underlying_calendar import TradingCalendar

cal = TradingCalendar(
    weekends=(5, 6),
    holidays=("2026-01-01", "2026-12-25"),
    timezone="Europe/London",
    open_time="08:00",
    close_time="16:30",
    early_close_days=("2026-12-24",),
    early_close_time="12:30",
)
```

### Rolling conventions

| Convention | Behaviour |
|---|---|
| `following` | Next trading day |
| `previous` | Previous trading day |
| `modified_following` | Following, unless it crosses into the next month — then previous (ISDA default) |
| `modified_previous` | Previous, unless it crosses into the prior month — then following |

## License

MIT
