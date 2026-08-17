"""Machine-readable QA status model (canonical spec section 12)."""

from __future__ import annotations

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

_ORDER = {PASS: 0, WARN: 1, FAIL: 2}


def worst(statuses) -> str:
    """Aggregate statuses to the worst one; empty input is PASS."""
    result = PASS
    for s in statuses:
        if _ORDER[s] > _ORDER[result]:
            result = s
    return result


def check(name: str, status: str, detail: str = "", **data) -> dict:
    return {"check": name, "status": status, "detail": detail, **data}
