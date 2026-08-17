from datetime import date

from nqresearch.qa.reconcile import (
    _compare,
    _merge_maps,
    _new_agg,
    _status_from,
    _update_agg,
)
from nqresearch.qa.status import FAIL, PASS, WARN
from nqresearch.sessions import session_utc_dates


def _agg(count=1, volume=2, px_min=10, px_max=20, ts_first=100, ts_last=200,
         side_A=1, side_B=0, side_N=0):
    a = _new_agg()
    _update_agg(a, count, volume, side_A, side_B, side_N, px_min, px_max,
                ts_first, ts_last)
    return a


class TestMerge:
    def test_merge_across_files_sums_and_extends(self):
        # Same (session, instrument) split across two UTC files.
        m = _merge_maps([
            {"2026-08-06|42": _agg(count=3, volume=5, ts_first=100, ts_last=200,
                                   px_min=15, px_max=18)},
            {"2026-08-06|42": _agg(count=2, volume=4, ts_first=250, ts_last=300,
                                   px_min=10, px_max=30)},
        ])
        a = m["2026-08-06|42"]
        assert a["count"] == 5 and a["volume"] == 9
        assert a["ts_first"] == 100 and a["ts_last"] == 300
        assert a["px_min"] == 10 and a["px_max"] == 30


class TestCompare:
    def test_exact_match(self):
        a = {"k": _agg()}
        b = {"k": _agg()}
        exact, mismatches = _compare(a, b, "x", "y")
        assert exact == 1 and mismatches == []

    def test_field_mismatch_reported(self):
        exact, mismatches = _compare(
            {"k": _agg(volume=2)}, {"k": _agg(volume=3)}, "x", "y"
        )
        assert exact == 0
        assert mismatches[0]["issue"] == "field_mismatch"
        assert "volume" in mismatches[0]["diffs"]

    def test_missing_key_reported(self):
        exact, mismatches = _compare({"k": _agg()}, {}, "x", "y")
        assert mismatches[0]["issue"] == "missing_in_y"


class TestStatus:
    def test_no_mismatch_passes(self):
        assert _status_from(100, 100, []) == PASS

    def test_small_relative_diff_warns(self):
        assert _status_from(100000, 100001, [{"m": 1}]) == WARN

    def test_large_relative_diff_fails(self):
        assert _status_from(100, 200, [{"m": 1}]) == FAIL


class TestCompleteSessionLogic:
    def test_session_complete_only_with_both_utc_files(self):
        overlap = {date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5),
                   date(2026, 8, 6), date(2026, 8, 7)}
        # Tue-Fri sessions are complete; Monday 08-03 needs Sunday 08-02.
        assert not all(d in overlap for d in session_utc_dates(date(2026, 8, 3)))
        for s in [date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6),
                  date(2026, 8, 7)]:
            assert all(d in overlap for d in session_utc_dates(s))
