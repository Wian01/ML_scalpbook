from datetime import date

import pytest

from nqresearch.filenames import file_date_key, file_utc_date


class TestFileUtcDate:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("glbx-mdp3-20260803.mbp-1.dbn.zst", date(2026, 8, 3)),
            ("glbx-mdp3-20240809.trades.dbn.zst", date(2024, 8, 9)),
            ("glbx-mdp3-20251031.mbo.dbn.zst", date(2025, 10, 31)),
        ],
    )
    def test_ignores_mdp3_digit(self, name, expected):
        assert file_utc_date(name) == expected

    def test_no_date_raises(self):
        with pytest.raises(ValueError):
            file_utc_date("metadata.json")

    def test_key(self):
        assert file_date_key("glbx-mdp3-20260803.mbp-1.dbn.zst") == "20260803"
