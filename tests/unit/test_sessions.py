"""Session assignment and RTH tests, including DST transitions and the 17:00 CT
session boundary (canonical spec sections 9/10, edge cases section 74)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from nqresearch.config import SessionWindowConfig
from nqresearch.sessions import (
    is_rth,
    session_exprs,
    session_utc_dates,
    trading_session,
)

CHICAGO = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def ct(y, m, d, hh, mm, ss=0) -> int:
    return ns(datetime(y, m, d, hh, mm, ss, tzinfo=CHICAGO))


class TestTradingSession:
    def test_midday_belongs_to_same_day(self):
        assert trading_session(ct(2026, 8, 12, 12, 0)) == date(2026, 8, 12)

    def test_before_boundary_belongs_to_same_day(self):
        assert trading_session(ct(2026, 8, 12, 16, 59, 59)) == date(2026, 8, 12)

    def test_at_boundary_belongs_to_next_day(self):
        assert trading_session(ct(2026, 8, 12, 17, 0, 0)) == date(2026, 8, 13)

    def test_sunday_evening_belongs_to_monday(self):
        # 2026-08-09 is a Sunday; the 17:00 CT open belongs to Monday's session.
        assert trading_session(ct(2026, 8, 9, 18, 0)) == date(2026, 8, 10)

    def test_midnight_utc_crossing(self):
        # 23:30 UTC on 2026-08-12 is 18:30 CT -> session 2026-08-13.
        t = ns(datetime(2026, 8, 12, 23, 30, tzinfo=UTC))
        assert trading_session(t) == date(2026, 8, 13)

    def test_dst_spring_forward_boundary_is_chicago_local(self):
        # US DST begins 2026-03-08. Before: CST (UTC-6); after: CDT (UTC-5).
        # 17:00 CT boundary on Fri 2026-03-06 == 23:00 UTC.
        assert trading_session(ns(datetime(2026, 3, 6, 22, 59, tzinfo=UTC))) == date(2026, 3, 6)
        assert trading_session(ns(datetime(2026, 3, 6, 23, 0, tzinfo=UTC))) == date(2026, 3, 7)
        # After transition, boundary on Mon 2026-03-09 == 22:00 UTC.
        assert trading_session(ns(datetime(2026, 3, 9, 21, 59, tzinfo=UTC))) == date(2026, 3, 9)
        assert trading_session(ns(datetime(2026, 3, 9, 22, 0, tzinfo=UTC))) == date(2026, 3, 10)

    def test_dst_fall_back(self):
        # US DST ends 2025-11-02. Boundary Mon 2025-11-03 == 23:00 UTC again.
        assert trading_session(ns(datetime(2025, 11, 3, 22, 59, tzinfo=UTC))) == date(2025, 11, 3)
        assert trading_session(ns(datetime(2025, 11, 3, 23, 0, tzinfo=UTC))) == date(2025, 11, 4)


class TestRTH:
    def test_open_boundary_inclusive(self):
        assert is_rth(ct(2026, 8, 12, 8, 30, 0))
        assert not is_rth(ct(2026, 8, 12, 8, 29, 59))

    def test_close_boundary_exclusive(self):
        assert not is_rth(ct(2026, 8, 12, 15, 0, 0))
        assert is_rth(ct(2026, 8, 12, 14, 59, 59))

    def test_rth_is_chicago_local_across_dst(self):
        # 08:30 CT == 14:30 UTC in CST (January), 13:30 UTC in CDT (June).
        assert is_rth(ns(datetime(2026, 1, 15, 14, 30, tzinfo=UTC)))
        assert not is_rth(ns(datetime(2026, 1, 15, 14, 29, tzinfo=UTC)))
        assert is_rth(ns(datetime(2026, 6, 15, 13, 30, tzinfo=UTC)))
        assert not is_rth(ns(datetime(2026, 6, 15, 12, 59, tzinfo=UTC)))


class TestConfigDriven:
    def test_boundary_and_rth_come_from_config(self):
        # Custom config: boundary 16:00, RTH 09:00-14:00.
        cfg = SessionWindowConfig(
            session_boundary="16:00", rth_start="09:00", rth_end="14:00"
        )
        t = ct(2026, 8, 12, 16, 30)
        assert trading_session(t) == date(2026, 8, 12)  # default 17:00 boundary
        assert trading_session(t, cfg) == date(2026, 8, 13)  # custom 16:00 boundary
        t2 = ct(2026, 8, 12, 8, 45)
        assert is_rth(t2)  # default RTH opens 08:30
        assert not is_rth(t2, cfg)  # custom RTH opens 09:00

    def test_default_config_matches_spec(self):
        cfg = SessionWindowConfig()
        assert cfg.timezone == "America/Chicago"
        assert cfg.session_boundary == "17:00"
        assert cfg.rth_start == "08:30"
        assert cfg.rth_end == "15:00"

    def test_polars_exprs_honor_custom_config(self):
        cfg = SessionWindowConfig(session_boundary="16:00")
        t = ct(2026, 8, 12, 16, 30)
        df = pl.DataFrame({"ts_event": [t]}).with_columns(session_exprs("ts_event", cfg))
        assert df["session_id"][0] == date(2026, 8, 13)


class TestSessionUtcDates:
    def test_session_spans_prior_utc_date_and_own(self):
        s = date(2026, 8, 6)
        assert session_utc_dates(s) == [date(2026, 8, 5), date(2026, 8, 6)]

    def test_monday_session_needs_sunday_file(self):
        s = date(2026, 8, 10)  # Monday; evening open lives in Sunday's UTC file
        assert session_utc_dates(s)[0] == date(2026, 8, 9)

    def test_window_boundaries_map_into_listed_dates(self):
        # First and last event of session 2026-08-06 fall on the listed UTC dates.
        start = ct(2026, 8, 5, 17, 0)
        end = ct(2026, 8, 6, 16, 59)
        listed = set(session_utc_dates(date(2026, 8, 6)))
        for t in (start, end):
            utc_day = datetime.fromtimestamp(t / 1e9, tz=UTC).date()
            assert utc_day in listed
            assert trading_session(t) == date(2026, 8, 6)


class TestPolarsMatchesScalar:
    @pytest.mark.parametrize(
        "ts",
        [
            ct(2026, 8, 12, 12, 0),
            ct(2026, 8, 12, 16, 59, 59),
            ct(2026, 8, 12, 17, 0),
            ct(2026, 8, 9, 18, 0),
            ct(2026, 3, 8, 12, 0),  # DST transition day
            ct(2025, 11, 2, 12, 0),  # fall-back day
            ct(2026, 8, 12, 8, 30),
            ct(2026, 8, 12, 15, 0),
            ns(datetime(2026, 8, 12, 23, 59, 59, tzinfo=UTC)),
            ns(datetime(2026, 8, 13, 0, 0, 0, tzinfo=UTC)),
        ],
    )
    def test_vectorized_equals_reference(self, ts):
        df = pl.DataFrame({"ts_event": [ts]}).with_columns(session_exprs("ts_event"))
        assert df["session_id"][0] == trading_session(ts)
        assert df["rth_flag"][0] == is_rth(ts)
