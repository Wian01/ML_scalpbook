"""NQ symbol classification and instrument-ID mapping helpers.

All purchased datasets use Databento parent symbology (NQ.FUT, stype_in=parent,
stype_out=instrument_id), so raw files contain every NQ child instrument:
outright futures AND calendar spreads. Research joins use instrument_id
(canonical spec section 8); raw symbols are retained for audit/reporting.
"""

from __future__ import annotations

import re
from typing import Any

MONTH_CODES = "FGHJKMNQUVXZ"

_OUTRIGHT_RE = re.compile(rf"^NQ[{MONTH_CODES}]\d{{1,2}}$")
_GENERIC_OUTRIGHT_RE = re.compile(rf"^([A-Z0-9]{{1,3}}?)([{MONTH_CODES}])(\d{{1,2}})$")

OUTRIGHT = "outright"
CALENDAR_SPREAD = "calendar_spread"
OTHER = "other"

# Classification for NQ research over mixed-product raw files (e.g. MBO jobs
# that also queried ES.FUT). Mixed files are expected and preserved unchanged;
# non-NQ products and NQ calendar spreads are excluded from NQ research
# coverage, with exclusions recorded in QA metadata.
NQ_OUTRIGHT = "nq_outright"
NQ_CALENDAR_SPREAD = "nq_calendar_spread"
OTHER_PRODUCT = "other_product"


def classify_symbol(symbol: str) -> str:
    """Classify a raw CME Globex NQ symbol as outright, calendar spread, or other."""
    if _OUTRIGHT_RE.match(symbol):
        return OUTRIGHT
    legs = symbol.split("-")
    if len(legs) == 2 and all(_OUTRIGHT_RE.match(leg) for leg in legs):
        return CALENDAR_SPREAD
    return OTHER


def product_root(symbol: str) -> str | None:
    """Product root of an outright or single-product spread (e.g. 'NQ', 'ES').

    Returns None when the symbol is not parseable or mixes product roots.
    """
    legs = symbol.split("-")
    roots = set()
    for leg in legs:
        m = _GENERIC_OUTRIGHT_RE.match(leg)
        if not m:
            return None
        roots.add(m.group(1))
    return roots.pop() if len(roots) == 1 else None


def classify_for_nq_research(symbol: str) -> str:
    """NQ-research classification: NQ outrights are in scope; NQ calendar
    spreads and all other products are excluded (recorded, never dropped
    silently from raw)."""
    root = product_root(symbol)
    if root != "NQ":
        return OTHER_PRODUCT
    return NQ_OUTRIGHT if "-" not in symbol else NQ_CALENDAR_SPREAD


def instrument_map_from_mappings(mappings: dict[str, list[dict[str, Any]]]) -> dict[int, str]:
    """Build instrument_id -> raw symbol from DBN metadata symbol mappings.

    DBN metadata mappings (stype_out=instrument_id) map each raw symbol to
    dated intervals whose 'symbol' entry is the instrument_id as a string.
    Raises on conflicting assignments of one instrument_id to different symbols
    within a single file's metadata.
    """
    out: dict[int, str] = {}
    for raw_symbol, intervals in mappings.items():
        for interval in intervals:
            iid_str = interval.get("symbol", "")
            if not iid_str:
                continue
            iid = int(iid_str)
            existing = out.get(iid)
            if existing is not None and existing != raw_symbol:
                raise ValueError(
                    f"instrument_id {iid} mapped to both {existing!r} and {raw_symbol!r}"
                )
            out[iid] = raw_symbol
    return out
