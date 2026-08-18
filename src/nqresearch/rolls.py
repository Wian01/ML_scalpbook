"""Front-contract determination for parent-symbology NQ data (proposed rule).

PROPOSED RULE (protocol clarification restoring canonical §8 intent; pending
review approval):

1. Calendar spreads are excluded before any volume calculation; only NQ
   outrights compete. Raw symbol and instrument_id are always preserved.
2. STRICTLY CAUSAL: the front effective for session S is decided from the
   PREVIOUS completed eligible session's outright volumes (matching
   Databento's documented volume-based continuous-contract ranking by the
   previous day's trading volume). Session S's own completed volume is never
   used to select session S's contract.
3. Switches take effect only at complete session boundaries; there is no
   intra-session switch. The first corpus session has no prior session and
   is explicitly UNRESOLVED/ineligible (front=None) — no look-ahead seed.
4. Monotone-expiry constraint: the front may only move to a LATER expiry.
   A later back-volume spike can never switch backward (prevents roll-week
   flip-flop deterministically, without tunable hysteresis).
5. Tie (equal volume): the incumbent front is retained; if there is no
   incumbent yet, the earliest expiry wins.
6. Missing/insufficient data: a session with no outright volume (e.g. the
   Good Friday quote-only session) retains the incumbent front and is
   flagged INSUFFICIENT_VOLUME; the first sessions before any volume exists
   have front=None.
7. Prices are never back-adjusted; features/labels/latency windows crossing
   a switch are dropped at dataset-construction time (§8) — the switch
   records emitted here are the authoritative boundaries for that rule.
8. Roll-week flag: sessions within ±3 trading sessions of a switch.
"""

from __future__ import annotations

from nqresearch.symbols import MONTH_CODES, _GENERIC_OUTRIGHT_RE


def expiry_sort_key(symbol: str) -> tuple[int, int]:
    """(year, month_index) for an outright symbol like NQU6 / NQZ26.

    Two-digit years are absolute (e.g. 26 -> 2026); single-digit years are
    resolved to the 2020s decade window used by CME Globex display symbols
    within this project's 2024-2026 corpus (e.g. 5 -> 2025).
    """
    m = _GENERIC_OUTRIGHT_RE.match(symbol)
    if not m:
        raise ValueError(f"not an outright symbol: {symbol!r}")
    _, month_code, year_digits = m.groups()
    year = int(year_digits)
    year = 2000 + year if year >= 10 else 2020 + year
    return (year, MONTH_CODES.index(month_code))


def compute_front_series(
    session_volumes: dict[str, dict[str, int]],
) -> dict:
    """front-per-session + switch records from {session: {symbol: volume}}.

    session_volumes must contain OUTRIGHT symbols only, in chronological
    session order (keys are ISO dates; processed sorted).
    """
    front: str | None = None
    prev_session: str | None = None
    prev_vols: dict[str, int] | None = None
    per_session: list[dict] = []
    switches: list[dict] = []
    for sess in sorted(session_volumes):
        flags: list[str] = []
        # Decide front for THIS session from the PREVIOUS session's volumes.
        if prev_vols is None:
            flags.append("UNRESOLVED_NO_PRIOR_SESSION")
        elif not prev_vols or max(prev_vols.values()) <= 0:
            flags.append("INSUFFICIENT_VOLUME")  # incumbent persists
        else:
            max_vol = max(prev_vols.values())
            leaders = sorted(
                (s for s, v in prev_vols.items() if v == max_vol),
                key=expiry_sort_key,
            )
            if front is not None and front in leaders:
                candidate = front  # tie retains incumbent
            else:
                candidate = leaders[0]
            if front is None:
                front = candidate
            elif candidate != front:
                if expiry_sort_key(candidate) > expiry_sort_key(front):
                    switches.append(
                        {"session_id": sess, "from": front, "to": candidate,
                         "decided_from_session": prev_session}
                    )
                    front = candidate
                else:
                    # Backward-expiry volume spike: never switch back.
                    flags.append("BACKWARD_VOLUME_LEADER_IGNORED")
        per_session.append({"session_id": sess, "front": front, "flags": flags})
        prev_session, prev_vols = sess, session_volumes[sess]

    switch_sessions = {s["session_id"] for s in switches}
    ordered = [r["session_id"] for r in per_session]
    roll_week: set[str] = set()
    for i, sess in enumerate(ordered):
        for j in range(max(0, i - 3), min(len(ordered), i + 4)):
            if ordered[j] in switch_sessions:
                roll_week.add(sess)
                break
    for r in per_session:
        r["roll_week"] = r["session_id"] in roll_week
    return {"per_session": per_session, "switches": switches}
