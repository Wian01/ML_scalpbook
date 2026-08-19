"""ORDINARY RESEARCH data loading — fenced, provenance-checked, and (in the
Milestone 1 foundation) REFUSING ENTIRELY.

Why no paths are returned (independent-audit remediation): the partitions
are defined in CME trading-session dates, but vendor DBN files are UTC-day
splits, and one UTC file can contain events of TWO sessions. Concrete
boundary proof: session 2026-03-31 (last SELECTION session in the proposal)
spans UTC dates {2026-03-30, 2026-03-31}, while session 2026-04-01 (first
HOLDOUT session) spans {2026-03-31, 2026-04-01} — UTC file 2026-03-31
contains BOTH. Returning raw UTC-day paths could therefore expose HOLDOUT
events and omit the halo file needed for a requested session.

MILESTONE 2 REQUIREMENT (recorded here as the implementation contract): the
research reader must (a) pass the active-partition fence and
require_provenance(); (b) load the necessary UTC-day halo internally;
(c) assign CME session_id to every record BEFORE releasing anything;
(d) discard every event outside the approved requested sessions; (e) never
expose the underlying mixed-boundary raw file paths to research consumers;
and (f) apply the PA-0002 research-eligibility mask — emit nothing for a
quarantined session, never let a feature/label/sample/evaluation window
cross one, and reset rolling state at the next eligible session.

Until that session-filtered reader exists, every research access:
1. invokes the mechanical holdout fence (fail-closed while no active
   partition configuration exists);
2. invokes require_provenance() (fail-closed without a valid bound
   acquisition gate);
3. then still refuses with ResearchLoaderNotImplementedError.
"""

from __future__ import annotations

from datetime import date


class ResearchLoaderNotImplementedError(RuntimeError):
    """Fail-closed: no session-filtered research reader exists yet."""


def _gate(start: date, end: date) -> None:
    from nqresearch.eligibility import load_policy_for_research
    from nqresearch.holdout import assert_research_range_allowed
    from nqresearch.sources import require_provenance

    assert_research_range_allowed(start, end)  # fence FIRST; fail closed
    require_provenance()                        # provenance evidence required
    # PA-0002 mask must fully validate (schema + evidence binding + date-set
    # consistency) AND be the activation-approved policy. No caller-supplied
    # allowed-state set exists.
    load_policy_for_research()


def research_eligible_sessions(start: date, end: date) -> list[str]:
    """Gated enumeration of research-ELIGIBLE session IDs in a range.

    Quarantined sessions (PA-0002) are filtered out, so a broad request such
    as the whole of DEV still works; a range containing no eligible session,
    or a single quarantined session, is refused. Session identifiers only —
    raw file paths are never returned.
    """
    from nqresearch.eligibility import eligible_sessions_in_range

    _gate(start, end)
    return eligible_sessions_in_range(start, end)


def research_session_records(start: date, end: date):
    """THE research data entry point (explicit session-date range mandatory).

    Milestone 1: gates run, then this refuses — raw UTC-day paths are never
    returned to research consumers (see module docstring for the boundary
    proof and the Milestone 2 session-filtered reader contract).
    """
    _gate(start, end)
    raise ResearchLoaderNotImplementedError(
        "the session-filtered research reader is not implemented until "
        "Milestone 2; raw UTC-day file paths are never returned as research "
        "data (a UTC file can mix SELECTION and HOLDOUT sessions)"
    )


def research_input_entries(start: date, end: date):
    """Retained name from the fenced API: gates, then refuses (no raw paths)."""
    return research_session_records(start, end)


def research_input_files(start: date, end: date):
    """Retained name from the fenced API: gates, then refuses (no raw paths)."""
    return research_session_records(start, end)
