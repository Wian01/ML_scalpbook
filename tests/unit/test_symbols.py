import pytest

from nqresearch.symbols import (
    CALENDAR_SPREAD,
    NQ_CALENDAR_SPREAD,
    NQ_OUTRIGHT,
    OTHER,
    OTHER_PRODUCT,
    OUTRIGHT,
    classify_for_nq_research,
    classify_symbol,
    instrument_map_from_mappings,
    product_root,
)


class TestClassify:
    @pytest.mark.parametrize("sym", ["NQZ5", "NQU6", "NQM9", "NQZ26", "NQH31"])
    def test_outrights(self, sym):
        assert classify_symbol(sym) == OUTRIGHT

    @pytest.mark.parametrize("sym", ["NQM7-NQU7", "NQZ6-NQH7", "NQU6-NQM7"])
    def test_calendar_spreads(self, sym):
        assert classify_symbol(sym) == CALENDAR_SPREAD

    @pytest.mark.parametrize("sym", ["NQ.FUT", "ESZ5", "NQ", "NQA5", "NQZ5-ESZ5", ""])
    def test_other(self, sym):
        assert classify_symbol(sym) == OTHER


class TestProductRoot:
    @pytest.mark.parametrize(
        "sym,root",
        [
            ("NQZ5", "NQ"),
            ("ESU6", "ES"),
            ("NQM7-NQU7", "NQ"),
            ("ESU6-ESZ6", "ES"),
            ("6EZ5", "6E"),
        ],
    )
    def test_roots(self, sym, root):
        assert product_root(sym) == root

    @pytest.mark.parametrize("sym", ["NQZ5-ESZ5", "NQ.FUT", "garbage", ""])
    def test_unparseable_or_mixed(self, sym):
        assert product_root(sym) is None


class TestClassifyForNqResearch:
    def test_nq_outright_in_scope(self):
        assert classify_for_nq_research("NQZ5") == NQ_OUTRIGHT

    def test_nq_calendar_spread_excluded(self):
        assert classify_for_nq_research("NQM7-NQU7") == NQ_CALENDAR_SPREAD

    @pytest.mark.parametrize("sym", ["ESU6", "ESU6-ESZ6", "NQZ5-ESZ5", "junk"])
    def test_other_products_excluded(self, sym):
        assert classify_for_nq_research(sym) == OTHER_PRODUCT


class TestInstrumentMap:
    def test_basic_mapping(self):
        mappings = {
            "NQZ6": [{"start_date": None, "end_date": None, "symbol": "261401"}],
            "NQM7-NQU7": [{"start_date": None, "end_date": None, "symbol": "42047398"}],
        }
        m = instrument_map_from_mappings(mappings)
        assert m == {261401: "NQZ6", 42047398: "NQM7-NQU7"}

    def test_conflicting_mapping_raises(self):
        mappings = {
            "NQZ6": [{"symbol": "1"}],
            "NQH7": [{"symbol": "1"}],
        }
        with pytest.raises(ValueError):
            instrument_map_from_mappings(mappings)

    def test_empty_symbol_skipped(self):
        assert instrument_map_from_mappings({"NQZ6": [{"symbol": ""}]}) == {}
