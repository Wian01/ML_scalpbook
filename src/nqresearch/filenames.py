"""Vendor filename parsing.

Databento daily-split files are named like `glbx-mdp3-YYYYMMDD.<schema>.dbn.zst`.
The date must be extracted with an explicit pattern: naive digit concatenation
would pick up the `3` from `mdp3`.
"""

from __future__ import annotations

import re
from datetime import date

_DATE_RE = re.compile(r"(20\d{6})")


def file_utc_date(filename: str) -> date:
    """UTC date encoded in a Databento daily-split filename."""
    m = _DATE_RE.search(filename)
    if not m:
        raise ValueError(f"No YYYYMMDD date found in filename: {filename!r}")
    s = m.group(1)
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def file_date_key(filename: str) -> str:
    """YYYYMMDD string key for joining daily files across datasets."""
    return file_utc_date(filename).strftime("%Y%m%d")
