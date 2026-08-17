"""Databento DBN record flag bits (MDP3).

F_LAST marks the final record of a packet/event; only F_LAST-complete book
states are valid observations for features/labels (canonical spec section 16).
"""

from __future__ import annotations

import numpy as np

FLAG_BITS = {
    "F_LAST": 128,
    "F_TOB": 64,
    "F_SNAPSHOT": 32,
    "F_MBP": 16,
    "F_BAD_TS_RECV": 8,
    "F_MAYBE_BAD_BOOK": 4,
}

UNDEF_PRICE = 9223372036854775807  # int64 max sentinel for undefined price


def flag_counts(flags: np.ndarray) -> dict[str, int]:
    """Count how many records carry each known flag bit; report unknown bits."""
    out = {name: int((flags & bit != 0).sum()) for name, bit in FLAG_BITS.items()}
    known_mask = 0
    for bit in FLAG_BITS.values():
        known_mask |= bit
    out["UNKNOWN_BITS"] = int((flags & ~np.uint8(known_mask) != 0).sum())
    return out
