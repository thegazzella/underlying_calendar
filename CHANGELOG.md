# Changelog

All notable changes to this project will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-06-07

### Added
- `TradingCalendar` class with O(1) holiday and weekend membership tests
- Market hours (`market_open`, `market_close`) returned as UTC ISO 8601 strings with DST support
- Early close day support with a configurable early close time
- Date navigation: `next_trading_day`, `previous_trading_day`, `add_trading_days`, `trading_days_between`
- Rolling conventions: `following`, `previous`, `modified_following`, `modified_previous`
- `schedule()` to build a sorted list of trading days over a date range
- Built-in presets: `SPX_CALENDAR` (NYSE, 2000–2030), `WEEKDAYS_CALENDAR`, `ALL_DAYS_CALENDAR`
