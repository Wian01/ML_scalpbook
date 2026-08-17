import numpy as np

from nqresearch.flags import UNDEF_PRICE, flag_counts


class TestFlagCounts:
    def test_single_bits(self):
        flags = np.array([128, 128, 32, 4, 0], dtype=np.uint8)
        c = flag_counts(flags)
        assert c["F_LAST"] == 2
        assert c["F_SNAPSHOT"] == 1
        assert c["F_MAYBE_BAD_BOOK"] == 1
        assert c["UNKNOWN_BITS"] == 0

    def test_combined_bits(self):
        flags = np.array([128 + 32, 128 + 16], dtype=np.uint8)
        c = flag_counts(flags)
        assert c["F_LAST"] == 2
        assert c["F_SNAPSHOT"] == 1
        assert c["F_MBP"] == 1

    def test_unknown_bits_detected(self):
        flags = np.array([1, 2, 128], dtype=np.uint8)
        assert flag_counts(flags)["UNKNOWN_BITS"] == 2

    def test_undef_price_sentinel(self):
        assert UNDEF_PRICE == np.iinfo(np.int64).max
