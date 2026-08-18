"""Effective CME calendar semantics: the pandas_market_calendars snapshot is
a reproducible BASELINE (not authoritative by itself), merged with the
official-CME overrides file which wins on conflict; validated against
observed vendor data."""

from datetime import date, time

import pytest

from nqresearch.calendar import (
    STATUS_HOLIDAY,
    STATUS_NORMAL,
    STATUS_SHORTENED,
    STATUS_WEEKEND,
    load_calendar,
)
from nqresearch.config import effective_config_hash
from nqresearch.sessions import is_rth, trading_session

CAL = load_calendar()


class TestKnownDates:
    def test_ordinary_session(self):
        assert CAL.session_status(date(2026, 8, 12)) == STATUS_NORMAL
        assert CAL.close_time_ct(date(2026, 8, 12)) == time(16, 0)

    def test_good_friday_is_shortened_not_holiday(self):
        # Observed in vendor data: tiny 2025-04-18 MBP-1 file (quotes, no
        # trades file) and active 16 MB 2026-04-03 file (jobs-report morning).
        for d in (date(2025, 4, 18), date(2026, 4, 3)):
            assert CAL.session_status(d) == STATUS_SHORTENED
            assert CAL.close_time_ct(d) == time(8, 15)

    def test_independence_day_shortened_2026_07_03(self):
        assert CAL.session_status(date(2026, 7, 3)) == STATUS_SHORTENED
        assert CAL.close_time_ct(date(2026, 7, 3)) == time(12, 0)
        # Expected RTH span 08:30-12:00 = 3.5 h — matches the decoded MBO
        # rth_span_coverage of ~0.5385 (3.5/6.5).
        assert CAL.expected_rth_span_seconds(date(2026, 7, 3)) == 12600

    def test_day_after_thanksgiving_early_close(self):
        assert CAL.close_time_ct(date(2025, 11, 28)) == time(12, 15)

    def test_full_holidays(self):
        for d in (date(2024, 12, 25), date(2025, 1, 1), date(2025, 12, 25),
                  date(2026, 1, 1)):
            assert CAL.session_status(d) == STATUS_HOLIDAY
            assert not CAL.is_trading_day(d)

    def test_weekends(self):
        assert CAL.session_status(date(2026, 8, 8)) == STATUS_WEEKEND
        assert CAL.session_status(date(2026, 8, 9)) == STATUS_WEEKEND

    def test_official_override_2025_01_09_mourning_day(self):
        # Official CME override over the pandas_market_calendars baseline:
        # 08:30 CT close -> zero expected RTH, matching observed data.
        d = date(2025, 1, 9)
        assert CAL.session_status(d) == STATUS_SHORTENED
        assert CAL.close_time_ct(d) == time(8, 30)
        assert CAL.expected_rth_span_seconds(d) == 0
        assert CAL.is_override(d)
        assert not CAL.is_override(date(2026, 7, 3))  # baseline, not override

    def test_degraded_flag_dates_are_valid_sessions_or_weekends(self):
        # The two Saturday "degraded" vendor flags are weekend dates.
        assert CAL.session_status(date(2026, 1, 31)) == STATUS_WEEKEND
        assert CAL.session_status(date(2026, 3, 21)) == STATUS_WEEKEND
        assert CAL.is_trading_day(date(2024, 9, 18))


class TestSessionBoundaryInteraction:
    def test_dst_transition_days_are_ordinary_sessions(self):
        assert CAL.session_status(date(2026, 3, 9)) == STATUS_NORMAL  # after spring-fwd
        assert CAL.session_status(date(2025, 11, 3)) == STATUS_NORMAL  # after fall-back

    def test_boundary_17ct_belongs_to_next_trading_day(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        t = int(datetime(2026, 7, 2, 17, 30,
                         tzinfo=ZoneInfo("America/Chicago")).timestamp() * 1e9)
        s = trading_session(t)
        assert s == date(2026, 7, 3)
        assert CAL.session_status(s) == STATUS_SHORTENED

    def test_rth_flag_vs_early_close(self):
        # 13:00 CT on 2026-07-03 is inside generic RTH hours but after the
        # 12:00 shortened close — coverage logic must use the calendar's
        # expected span, not the raw RTH window.
        from datetime import datetime
        from zoneinfo import ZoneInfo

        t = int(datetime(2026, 7, 3, 13, 0,
                         tzinfo=ZoneInfo("America/Chicago")).timestamp() * 1e9)
        assert is_rth(t)  # generic window
        assert CAL.expected_rth_span_seconds(date(2026, 7, 3)) < 6 * 3600


class TestContiguity:
    def test_weekend_not_between(self):
        assert CAL.trading_days_strictly_between(date(2026, 8, 7), date(2026, 8, 10)) == 0

    def test_holiday_not_counted(self):
        # 2025-12-25 (Thu) is a full holiday: 12-24 -> 12-26 has none between.
        assert CAL.trading_days_strictly_between(date(2025, 12, 24), date(2025, 12, 26)) == 0

    def test_shortened_session_counts_as_trading_day(self):
        # 2026-07-02 -> 2026-07-06 skips shortened 07-03 (a real session).
        assert CAL.trading_days_strictly_between(date(2026, 7, 2), date(2026, 7, 6)) == 1


class TestOverridesConfigBinding:
    def test_overrides_change_alters_effective_config_hash(self, tmp_path):
        import shutil

        from nqresearch.config import _repo_root, clear_config_cache

        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='x'\n")
        src = _repo_root() / "config" / "data"
        shutil.copy(src / "cme_calendar.yaml", root / "config" / "data")
        ov = root / "config" / "data" / "cme_calendar_overrides.yaml"
        ov.write_text('early_close_overrides:\n  "2025-01-09": "08:30"\n')
        clear_config_cache()
        h1 = effective_config_hash(root)
        ov.write_text('early_close_overrides:\n  "2025-01-09": "09:30"\n')
        clear_config_cache()
        assert effective_config_hash(root) != h1


class TestConfigBinding:
    def test_calendar_snapshot_in_effective_config_hash(self, tmp_path):
        import shutil

        from nqresearch.config import clear_config_cache

        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='x'\n")
        h_without = effective_config_hash(root)
        shutil.copy(
            load_calendar.__wrapped__.__globals__["_repo_root"]()
            / "config" / "data" / "cme_calendar.yaml",
            root / "config" / "data" / "cme_calendar.yaml",
        )
        clear_config_cache()
        assert effective_config_hash(root) != h_without
