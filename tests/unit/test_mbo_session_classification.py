"""Session-classification thresholds: initialization-record 'ghost sessions'
(stale file-start timestamps spanning an earlier date's RTH window) must not
be classified as covered sessions."""

from nqresearch.qa.mbo_audit import (
    MIN_FULL_RTH_ROWS,
    MIN_RTH_COVERAGE_FRACTION,
    MIN_TRACE_RTH_ROWS,
)


def classify(rth_rows: int, span: float) -> str:
    # Mirrors audit_directory's partition of session_cov.
    if rth_rows < MIN_TRACE_RTH_ROWS:
        return "trace"
    if span >= MIN_RTH_COVERAGE_FRACTION and rth_rows >= MIN_FULL_RTH_ROWS:
        return "full"
    return "partial"


class TestSessionClassification:
    def test_ordinary_session_is_full(self):
        assert classify(9_000_000, 0.999) == "full"

    def test_ghost_with_wide_span_is_trace_not_full(self):
        # 37 stale init rows spanning nearly all of RTH must not count.
        assert classify(37, 0.97) == "trace"

    def test_mid_day_start_is_partial(self):
        # e.g. 2025-10-09: millions of rows but vendor coverage starts mid-day.
        assert classify(7_784_649, 0.4513) == "partial"

    def test_shortened_session_is_partial_pending_holiday_calendar(self):
        # e.g. 2026-07-03 half-day: real rows, ~54% of a normal RTH span.
        assert classify(1_015_860, 0.5385) == "partial"

    def test_thresholds_are_ordered(self):
        assert MIN_TRACE_RTH_ROWS < MIN_FULL_RTH_ROWS
        assert 0 < MIN_RTH_COVERAGE_FRACTION <= 1
