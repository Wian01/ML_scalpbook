from datetime import date

from nqresearch.qa.mbo_inventory import assign_blocks, weekdays_between


class TestWeekdaysBetween:
    def test_adjacent_days(self):
        assert weekdays_between(date(2025, 10, 9), date(2025, 10, 10)) == 0

    def test_over_weekend(self):
        # Fri -> Mon: Sat/Sun between, no weekdays.
        assert weekdays_between(date(2025, 10, 10), date(2025, 10, 13)) == 0

    def test_missing_weekday(self):
        # Thu -> Mon skips Friday.
        assert weekdays_between(date(2025, 10, 9), date(2025, 10, 13)) == 1


class TestAssignBlocks:
    def test_weekend_does_not_break_block(self):
        blocks = assign_blocks(
            [date(2025, 10, 9), date(2025, 10, 10), date(2025, 10, 13)]
        )
        assert len(blocks) == 1
        assert blocks[0]["n_sessions"] == 3
        assert blocks[0]["mbo_lab_block_id"] == "MBO-BLK-001"

    def test_missing_weekday_breaks_block(self):
        blocks = assign_blocks([date(2025, 10, 9), date(2025, 10, 14)])
        assert len(blocks) == 2
        assert [b["mbo_lab_block_id"] for b in blocks] == ["MBO-BLK-001", "MBO-BLK-002"]

    def test_duplicates_and_order_are_normalized(self):
        blocks = assign_blocks([date(2025, 10, 10), date(2025, 10, 9), date(2025, 10, 9)])
        assert len(blocks) == 1
        assert blocks[0]["sessions"] == ["2025-10-09", "2025-10-10"]

    def test_isolated_sessions(self):
        blocks = assign_blocks([date(2025, 9, 8), date(2025, 9, 19)])
        assert len(blocks) == 2
        assert all(b["n_sessions"] == 1 for b in blocks)
