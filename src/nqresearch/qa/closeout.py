"""Milestone 0 closeout: calendar-aware MBO block freeze + partition proposal.

Reads the existing decoded MBO deep-audit artifact (no re-decode) and the
versioned effective calendar assembled from the reproducible baseline plus
official-CME overrides. Reclassifies shortened sessions (a session
whose decoded RTH span matches the calendar's shortened expectation is
COMPLETE), freezes contiguous block IDs using trading-day contiguity (weekends
AND holidays never break a block), and proposes DEV/SELECTION/HOLDOUT
boundaries at complete CME trading days. The partition proposal is
PROPOSED_NOT_ACTIVE: it is never frozen/activated without explicit human
approval (canonical §5.3/§60).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from nqresearch.calendar import load_calendar
from nqresearch.qa import status as st

RTH_FULL_SPAN_S = 6.5 * 3600
SPAN_TOLERANCE = 0.05

# Tentative boundaries (canonical §5.3: ~4-5 month holdout, candidate
# ~2026-04-01; based ONLY on coverage/calendar/MBO placement/period lengths).
# Revised per independent review so no MBO block spans a partition boundary:
# DEV absorbs the 2025-10-30..11-07 block; SELECTION starts Monday 11-10.
PROPOSED_DEV_START = date(2024, 8, 19)
PROPOSED_DEV_END = date(2025, 11, 7)           # Friday
PROPOSED_SELECTION_START = date(2025, 11, 10)  # Monday
PROPOSED_SELECTION_END = date(2026, 3, 31)     # Tuesday
PROPOSED_HOLDOUT_START = date(2026, 4, 1)      # Wednesday; tentative per spec
PROPOSED_HOLDOUT_END = date(2026, 8, 14)       # last complete session


def freeze_mbo_blocks(mbo_deep_artifact: Path) -> dict:
    """Final MBO session classification + frozen block IDs (calendar-aware)."""
    cal = load_calendar()
    deep = json.loads(mbo_deep_artifact.read_text(encoding="utf-8"))

    full = set(deep["full_rth_sessions"])
    reclassified = []
    for p in deep["partial_rth_sessions"]:
        s = p["session_id"]
        exp = cal.expected_rth_span_seconds(date.fromisoformat(s))
        obs = p["rth_span_coverage"] * RTH_FULL_SPAN_S
        if exp is not None and exp > 0 and abs(obs - exp) / exp <= SPAN_TOLERANCE:
            full.add(s)
            reclassified.append(
                {"session_id": s, "classification": "COMPLETE_SHORTENED_SESSION",
                 "observed_span_s": round(obs), "expected_span_s": exp}
            )
        else:
            reclassified.append(
                {"session_id": s, "classification": "PARTIAL_UNEXPLAINED",
                 "observed_span_s": round(obs), "expected_span_s": exp}
            )

    dates = sorted(date.fromisoformat(s) for s in full)
    blocks: list[list[date]] = []
    cur: list[date] = []
    for d in dates:
        if cur and cal.trading_days_strictly_between(cur[-1], d) > 0:
            blocks.append(cur)
            cur = []
        cur.append(d)
    if cur:
        blocks.append(cur)
    from nqresearch.calendar import calendar_identity

    frozen = [
        {"mbo_lab_block_id": f"MBO-BLK-{i + 1:03d}",
         "start": b[0].isoformat(), "end": b[-1].isoformat(),
         "n_sessions": len(b), "sessions": [x.isoformat() for x in b]}
        for i, b in enumerate(blocks)
    ]
    cal_id = calendar_identity()
    unexplained = [r for r in reclassified
                   if r["classification"] == "PARTIAL_UNEXPLAINED"]
    checks = [
        st.check("holiday_calendar_applied", st.PASS,
                 "block contiguity uses the versioned effective calendar "
                 "(baseline + official overrides)"),
        st.check("no_unexplained_partial_sessions",
                 st.PASS if not unexplained else st.WARN,
                 f"{len(unexplained)} partial sessions remain unexplained"),
    ]
    return {
        "artifact": "mbo_blocks_frozen",
        "based_on": {
            "mbo_deep_audit_source": str(mbo_deep_artifact),
            # Versioned EFFECTIVE calendar assembled from the reproducible
            # baseline plus official-CME overrides — bound by all three
            # identities so a change to either input invalidates this artifact.
            **cal_id,
        },
        "state": "PROVISIONAL_DOCUMENT_VERIFICATION_PENDING",
        "activation_ready": False,
        "activation_ready_conditions": [
            "official CME document verification of the baseline calendar is "
            "complete (overrides meta.baseline_verification all "
            "DOCUMENT_VERIFIED)",
            "all structural partition checks PASS",
            "explicit human partition approval has been recorded",
        ],
        "provisional_note": (
            "Block IDs are PROVISIONAL_DOCUMENT_VERIFICATION_PENDING: "
            "document-level verification of the baseline calendar's "
            "exceptional sessions against official CME schedules is pending "
            "(see cme_calendar_overrides.yaml meta.baseline_verification); "
            "until complete, blocks and partition dates must not be described "
            "as fully authoritative. The status field expresses computational "
            "validity only, never activation readiness."
        ),
        "n_sessions_final": len(dates),
        "reclassifications": reclassified,
        "blocks": frozen,
        "n_blocks": len(frozen),
        "acquisition_reason": "UNKNOWN_NOT_RECORDED_PENDING_USER_INPUT",
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }


def propose_partitions(blocks_frozen: dict) -> dict:
    """DEV/SELECTION/HOLDOUT proposal with per-partition MBO counts."""
    cal = load_calendar()

    def part_of(d: date) -> str:
        if d < PROPOSED_SELECTION_START:
            return "DEV"
        if d < PROPOSED_HOLDOUT_START:
            return "SELECTION"
        return "HOLDOUT"

    def trading_days(a: date, b: date) -> int:
        from datetime import timedelta

        n, d = 0, a
        while d <= b:
            if cal.is_trading_day(d):
                n += 1
            d += timedelta(days=1)
        return n

    mbo_sessions = {"DEV": 0, "SELECTION": 0, "HOLDOUT": 0}
    mbo_blocks = {"DEV": [], "SELECTION": [], "HOLDOUT": [], "SPANNING": []}
    for b in blocks_frozen["blocks"]:
        parts = {part_of(date.fromisoformat(s)) for s in b["sessions"]}
        for s in b["sessions"]:
            mbo_sessions[part_of(date.fromisoformat(s))] += 1
        if len(parts) == 1:
            mbo_blocks[parts.pop()].append(b["mbo_lab_block_id"])
        else:
            mbo_blocks["SPANNING"].append(
                {"block": b["mbo_lab_block_id"], "parts": sorted(parts)}
            )

    boundaries_ok = all(
        cal.is_trading_day(d) for d in
        (PROPOSED_DEV_START, PROPOSED_DEV_END, PROPOSED_SELECTION_START,
         PROPOSED_SELECTION_END, PROPOSED_HOLDOUT_START, PROPOSED_HOLDOUT_END)
    )
    forward_start = date(2026, 8, 17)
    contiguous = (
        cal.next_trading_day(PROPOSED_DEV_END) == PROPOSED_SELECTION_START
        and cal.next_trading_day(PROPOSED_SELECTION_END) == PROPOSED_HOLDOUT_START
        and cal.next_trading_day(PROPOSED_HOLDOUT_END) == forward_start
    )
    checks = [
        st.check("boundaries_on_trading_days",
                 st.PASS if boundaries_ok else st.FAIL,
                 "every proposed start/end boundary is a CME trading day"),
        st.check("partition_ranges_contiguous",
                 st.PASS if contiguous else st.FAIL,
                 "DEV→SELECTION→HOLDOUT→FORWARD cover consecutive trading "
                 "days with no gap or overlap"),
        st.check("no_partition_spanning_mbo_blocks",
                 st.PASS if not mbo_blocks["SPANNING"] else st.FAIL,
                 f"{len(mbo_blocks['SPANNING'])} MBO blocks span a partition "
                 "boundary; activation MUST be refused while non-empty"),
    ]
    return {
        "artifact": "partition_proposal",
        "state": "PROPOSED_NOT_ACTIVE",
        "calendar_verification_state": "PROVISIONAL_DOCUMENT_VERIFICATION_PENDING",
        "activation_ready": False,
        "activation_ready_conditions": [
            "official CME document verification of the baseline calendar is "
            "complete (overrides meta.baseline_verification all "
            "DOCUMENT_VERIFIED)",
            "all structural partition checks PASS",
            "explicit human partition approval has been recorded",
        ],
        "note": (
            "Boundaries derived only from coverage, calendar validity, MBO "
            "placement, and desired period lengths — never model outcomes. "
            "The ~2026-04-01 holdout boundary remains TENTATIVE per canonical "
            "§5.3 until explicitly approved. Activation/freezing requires "
            "explicit human approval and a follow-up protocol step."
        ),
        "proposal": {
            "DEV": {"start": PROPOSED_DEV_START.isoformat(),
                    "end": PROPOSED_DEV_END.isoformat(),
                    "trading_days": trading_days(PROPOSED_DEV_START,
                                                 PROPOSED_DEV_END)},
            "SELECTION": {"start": PROPOSED_SELECTION_START.isoformat(),
                          "end": PROPOSED_SELECTION_END.isoformat(),
                          "trading_days": trading_days(PROPOSED_SELECTION_START,
                                                       PROPOSED_SELECTION_END)},
            "HOLDOUT": {"start": PROPOSED_HOLDOUT_START.isoformat(),
                        "end": PROPOSED_HOLDOUT_END.isoformat(),
                        "tentative": True,
                        "trading_days": trading_days(PROPOSED_HOLDOUT_START,
                                                     PROPOSED_HOLDOUT_END)},
            "FORWARD": {"start": "2026-08-17",
                        "note": "all data collected after project start; the "
                                "2026-08-17 query-boundary partial edge "
                                "session is explicitly INELIGIBLE"},
        },
        "boundaries_on_trading_days": boundaries_ok,
        "mbo_sessions_per_partition": mbo_sessions,
        "mbo_blocks_per_partition": {k: v for k, v in mbo_blocks.items()},
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }
