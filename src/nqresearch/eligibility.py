"""Research-eligibility mask (protocol amendment PA-0002) — FAIL-CLOSED.

SENSITIVE CODE — status PENDING_INDEPENDENT_AUDIT.

This module is a RESEARCH-POLICY layer, deliberately separate from calendar
evidence. It never reads, writes, or reinterprets evidence states: the
quarantined sessions remain PENDING_EVIDENCE in the evidence matrix and the
effective calendar remains provisional. Quarantine means "never research
input"; it never means "verified".

Guarantees enforced here:
- ONE canonical session-ID parser guards every public entry point: only an
  exact ``datetime.date`` (never a ``datetime``) or a canonical
  ``YYYY-MM-DD`` string is accepted; malformed, padded, timestamped,
  numeric, boolean and null identifiers are refused instead of silently
  being treated as eligible;
- the committed policy is PA-0002-SPECIFIC and schema-strict: exact policy
  id, version, amendment path, lifecycle state, semantics and reason code,
  strict booleans, no extra fields;
- a policy has an explicit LIFECYCLE and only APPROVED_FOR_ACTIVATION may
  ever satisfy activation;
- quarantined sessions can never be returned as research sessions, and a
  direct request for one is refused;
- a broad range (e.g. all of DEV) still works: eligible sessions are
  selected and quarantined ones filtered out, so quarantine never makes a
  partition unusable;
- no feature/label/sample/evaluation window may span a quarantined session,
  and rolling state must reset at the next eligible session — including
  when the quarantined date has NO observed session (holiday / no data);
- the causal front-contract series NEVER consumes this mask (rolls stay a
  data-level construct; see nqresearch.rolls).

This module exposes session identifiers only. It never returns raw file
paths and performs no normalization.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

POLICY_FILENAME = "research_eligibility.yaml"

# ---------------------------------------------------------------------------
# PA-0002 identity constants. The committed policy must match these EXACTLY;
# a generic "some canonical §50 exclusion" policy is not a PA-0002 policy.
# ---------------------------------------------------------------------------
PA0002_POLICY_ID = "PA-0002-research-quarantine-v1"
PA0002_POLICY_VERSION = 1
PA0002_AMENDMENT_PATH = (
    "docs/protocol-amendments/PA-0002-research-eligibility-quarantine.md"
)
PA0002_REASON_CODE = "PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE"
PA0002_EVIDENCE_STATE = "PENDING_EVIDENCE"
QA_NORMALIZATION_SEMANTIC = "ALLOWED_FOR_QA_AND_SESSION_RECONSTRUCTION"
FORBIDDEN = "FORBIDDEN"

# Explicit policy lifecycle. Only the approved state may ever activate.
POLICY_STATE_PROPOSED = "PROPOSED_PENDING_INDEPENDENT_REVIEW"
POLICY_STATE_IMPLEMENTED = "IMPLEMENTED_PENDING_ACTIVATION_APPROVAL"
POLICY_STATE_APPROVED = "APPROVED_FOR_ACTIVATION"
POLICY_LIFECYCLE_STATES = (
    POLICY_STATE_PROPOSED, POLICY_STATE_IMPLEMENTED, POLICY_STATE_APPROVED,
)
NON_ACTIVATION_POLICY_STATES = frozenset({
    POLICY_STATE_PROPOSED, POLICY_STATE_IMPLEMENTED,
})

# Canonical §50 allowed exclusions (kept for documentation and cross-checks);
# PA-0002 entries must use PA0002_REASON_CODE specifically.
CANONICAL_ALLOWED_REASON_CODES = frozenset({
    "VENDOR_CORRUPT_SESSION",
    "UNRECOVERABLE_DATA_GAP",
    "INVALID_BOOK_RECONSTRUCTION",
    "SESSION_MISSING_REQUIRED_COVERAGE",
    "FEATURE_WINDOW_CROSSING_CONTRACT_BOUNDARY",
    "TARGET_HORIZON_CROSSING_CONTRACT_BOUNDARY",
    PA0002_REASON_CODE,
})

# Frozen real-corpus invariants the quarantine must not disturb. These are
# ASSERTED, never merely reported back from whatever an artifact contains.
EXPECTED_COVERAGE_SESSIONS = 516
EXPECTED_PARTITION_TRADING_DAYS = {"DEV": 318, "SELECTION": 100, "HOLDOUT": 98}
EXPECTED_OBSERVED_DEV_SESSIONS = 317
EXPECTED_ELIGIBLE_DEV_SESSIONS = 309
EXPECTED_QUARANTINED_DATES = 10
EXPECTED_EXCLUDED_OBSERVED_DEV_SESSIONS = 8
EXPECTED_MBO_SESSIONS = 77
EXPECTED_MBO_BLOCKS = 30
EXPECTED_SPANNING_BLOCKS = 0
EXPECTED_ROLL_SWITCHES = 8

_SHA256_HEX = set("0123456789abcdef")
_CANONICAL_SESSION_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


class EligibilityPolicyError(RuntimeError):
    """Fail-closed refusal: the policy is missing, malformed, or unbound."""


class InvalidSessionIdError(ValueError):
    """A session identifier was not a canonical YYYY-MM-DD date."""


class IneligibleSessionError(RuntimeError):
    """A quarantined session was requested as research input, or a window
    would cross one."""


def parse_session_id(value) -> str:
    """THE canonical session-ID parser used by every public entry point.

    Accepts only an exact ``datetime.date`` (a ``datetime`` is refused, even
    though it subclasses ``date``) or a canonical ``YYYY-MM-DD`` string.
    Everything else — malformed or whitespace-padded strings, timestamps,
    non-canonical date spellings, ints, bools, None, arbitrary objects —
    raises instead of being silently treated as an ordinary eligible
    session.
    """
    if isinstance(value, bool):
        raise InvalidSessionIdError(
            f"session identifier {value!r} is a bool, not a date"
        )
    if isinstance(value, datetime):
        raise InvalidSessionIdError(
            f"session identifier {value!r} is a datetime; a session is a "
            "calendar date (YYYY-MM-DD), never an instant"
        )
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        if not _CANONICAL_SESSION_RE.match(value):
            raise InvalidSessionIdError(
                f"session identifier {value!r} is not canonical YYYY-MM-DD"
            )
        try:
            parsed = date.fromisoformat(value)
        except ValueError as e:
            raise InvalidSessionIdError(
                f"session identifier {value!r} is not a real date: {e}"
            ) from e
        if parsed.isoformat() != value:
            raise InvalidSessionIdError(
                f"session identifier {value!r} is not canonical"
            )
        return value
    raise InvalidSessionIdError(
        f"session identifier {value!r} ({type(value).__name__}) is not a date"
    )


def _is_sha256_hex(v) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(
        c in _SHA256_HEX for c in v.lower()
    )


def _strict_bool(v, name: str) -> bool:
    if not isinstance(v, bool):
        raise ValueError(f"{name} must be a strict boolean, got {v!r}")
    return v


def _non_blank(v: str, name: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{name} must be a non-blank string")
    return v


class PolicyMeta(BaseModel):
    policy_id: Literal[PA0002_POLICY_ID]
    policy_version: StrictInt
    amendment: Literal[PA0002_AMENDMENT_PATH]
    status: Literal[POLICY_STATE_PROPOSED, POLICY_STATE_IMPLEMENTED,
                    POLICY_STATE_APPROVED]
    canonical_basis: str
    evidence_matrix_sha256: str
    rationale: str

    model_config = {"extra": "forbid"}

    @field_validator("policy_version", mode="before")
    @classmethod
    def _exact_version(cls, v):
        if isinstance(v, bool) or type(v) is not int:
            raise ValueError("policy_version must be a plain int")
        if v != PA0002_POLICY_VERSION:
            raise ValueError(
                f"policy_version must be exactly {PA0002_POLICY_VERSION}"
            )
        return v

    @field_validator("canonical_basis", "rationale")
    @classmethod
    def _not_blank(cls, v, info):
        return _non_blank(v, info.field_name)

    @field_validator("evidence_matrix_sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not _is_sha256_hex(v):
            raise ValueError("evidence_matrix_sha256 must be 64 hex chars")
        return v.lower()


class PolicySemantics(BaseModel):
    qa_and_normalization_use: Literal[QA_NORMALIZATION_SEMANTIC]
    research_use: Literal[FORBIDDEN]
    feature_window_crossing: Literal[FORBIDDEN]
    label_horizon_crossing: Literal[FORBIDDEN]
    evaluation_window_crossing: Literal[FORBIDDEN]
    # StrictBool/StrictInt refuse coercive representations (1, 0, "true",
    # "false", "0", None, []) BEFORE any after-validator could see an
    # already-coerced value.
    rolling_state_reset_required_at_next_eligible_session: StrictBool
    prior_session_state_features_require_policy_review: StrictBool
    calendar_membership_unchanged: StrictBool
    partition_contiguity_unchanged: StrictBool
    coverage_counts_unchanged: StrictBool
    causal_roll_series_consumes_eligibility: StrictBool
    raw_data_unchanged: StrictBool
    n_mbo_blocks_quarantined: StrictInt
    holdout_sealed: StrictBool

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _mandated_values(self):
        must_be_true = (
            "rolling_state_reset_required_at_next_eligible_session",
            "prior_session_state_features_require_policy_review",
            "calendar_membership_unchanged", "partition_contiguity_unchanged",
            "coverage_counts_unchanged", "raw_data_unchanged",
            "holdout_sealed",
        )
        for name in must_be_true:
            if getattr(self, name) is not True:
                raise ValueError(f"{name} must be true under PA-0002")
        if self.causal_roll_series_consumes_eligibility is not False:
            raise ValueError(
                "the causal roll series must NEVER consume the eligibility "
                "mask (it is a data-level construct)"
            )
        if self.n_mbo_blocks_quarantined != 0:
            raise ValueError("PA-0002 quarantines no MBO block")
        return self


class QuarantinedSession(BaseModel):
    date: date
    research_eligible: StrictBool
    reason_code: Literal[PA0002_REASON_CODE]
    evidence_state_at_policy_time: Literal[PA0002_EVIDENCE_STATE]
    note: str

    model_config = {"extra": "forbid"}

    @field_validator("date", mode="before")
    @classmethod
    def _canonical_date(cls, v):
        return date.fromisoformat(parse_session_id(v))

    @field_validator("research_eligible", mode="before")
    @classmethod
    def _strict_false(cls, v):
        if v is not False:
            raise ValueError(
                "a quarantined session must declare research_eligible=false "
                f"as a strict boolean (got {v!r})"
            )
        return v

    @field_validator("note")
    @classmethod
    def _note_not_blank(cls, v):
        return _non_blank(v, "note")


class EligibilityPolicy(BaseModel):
    meta: PolicyMeta
    semantics: PolicySemantics
    quarantined_sessions: list[QuarantinedSession]

    model_config = {"extra": "forbid"}

    @field_validator("quarantined_sessions")
    @classmethod
    def _unique_ascending(cls, v):
        # An EMPTY list is legal and means "nothing is quarantined"; it is
        # only valid when no calendar date is pending (enforced by
        # resolve_activation_disposition).
        dates = [s.date for s in v]
        if len(dates) != len(set(dates)):
            raise ValueError("duplicate quarantined dates")
        if dates != sorted(dates):
            raise ValueError(
                "quarantined dates must be in deterministic ascending order"
            )
        return v

    @property
    def dates(self) -> frozenset[str]:
        return frozenset(s.date.isoformat() for s in self.quarantined_sessions)

    def digest(self) -> str:
        """Deterministic digest of the quarantined-date set."""
        return hashlib.sha256(
            "\n".join(sorted(self.dates)).encode("utf-8")
        ).hexdigest()


def policy_path(repo_root: Path | None = None) -> Path:
    from nqresearch.config import _repo_root

    return (repo_root or _repo_root()) / "config" / "data" / POLICY_FILENAME


def policy_sha256(repo_root: Path | None = None) -> str:
    p = policy_path(repo_root)
    if not p.is_file():
        raise EligibilityPolicyError(
            f"research-eligibility policy missing: {p}; failing closed"
        )
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_policy(repo_root: Path | None = None) -> EligibilityPolicy:
    """Schema-only load of the committed fixed-path policy. Production code
    must use load_validated_policy() instead — this performs no evidence
    binding, date-set, or lifecycle verification."""
    p = policy_path(repo_root)
    if not p.is_file():
        raise EligibilityPolicyError(
            f"research-eligibility policy missing: {p}; failing closed"
        )
    if p.name != POLICY_FILENAME or p.parent.name != "data":
        raise EligibilityPolicyError(
            f"policy must be the committed fixed-path file, got {p}; "
            "failing closed"
        )
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return EligibilityPolicy(**doc)
    except EligibilityPolicyError:
        raise
    except Exception as e:
        raise EligibilityPolicyError(
            f"research-eligibility policy malformed; failing closed: {e}"
        ) from e


def verify_policy_bound_to_evidence(repo_root: Path | None = None) -> None:
    """The policy must bind the exact committed evidence matrix it was
    reviewed against — a changed matrix invalidates the disposition."""
    from nqresearch.calendar_evidence import matrix_file_sha256
    from nqresearch.config import _repo_root

    root = repo_root or _repo_root()
    policy = load_policy(root)
    actual = matrix_file_sha256(root)
    if policy.meta.evidence_matrix_sha256 != actual:
        raise EligibilityPolicyError(
            "research-eligibility policy binds evidence matrix "
            f"{policy.meta.evidence_matrix_sha256[:12]}…, but the committed "
            f"matrix is {actual[:12]}…; failing closed"
        )


def _load_validated_policy(repo_root: Path | None = None,
                           data_root: Path | None = None,
                           allowed_states=POLICY_LIFECYCLE_STATES):
    """PRIVATE, TEST-INJECTABLE validation core. Production callers must use
    one of the intent-specific entry points below — no public API accepts a
    caller-supplied allowed-state set, so nobody can relax the lifecycle
    requirement from the outside.

    Verifies: strict PA-0002 schema at the committed fixed path; the exact
    evidence-matrix SHA binding; matrix/policy date-set consistency (which
    also guarantees no conflict is dispositioned); and that the policy's
    lifecycle state is permitted for this intent.
    """
    from nqresearch import calendar_evidence as ce
    from nqresearch import paths
    from nqresearch.config import _repo_root

    root = repo_root or _repo_root()
    droot = data_root or paths.data_root()
    policy = load_policy(root)
    verify_policy_bound_to_evidence(root)
    if policy.meta.status not in allowed_states:
        raise EligibilityPolicyError(
            f"research-eligibility policy lifecycle state "
            f"{policy.meta.status!r} is not permitted here (allowed: "
            f"{sorted(allowed_states)}); failing closed"
        )
    try:
        matrix = ce.load_validated_matrix(root, droot)
        disposition = ce.resolve_activation_disposition(matrix, policy.dates)
    except ce.CalendarEvidenceError as e:
        raise EligibilityPolicyError(str(e)) from e
    return policy, disposition


def load_policy_for_reporting(repo_root: Path | None = None,
                              data_root: Path | None = None):
    """Validation for artifact-state stamping, proposal generation and
    eligibility masking. Any well-formed lifecycle state is acceptable, but
    a malformed policy or a stale evidence-matrix binding fails closed."""
    return _load_validated_policy(repo_root, data_root,
                                  POLICY_LIFECYCLE_STATES)


def load_policy_for_activation(repo_root: Path | None = None,
                               data_root: Path | None = None):
    """Validation for PARTITION ACTIVATION: requires exactly
    APPROVED_FOR_ACTIVATION."""
    return _load_validated_policy(repo_root, data_root,
                                  (POLICY_STATE_APPROVED,))


def load_policy_for_research(repo_root: Path | None = None,
                             data_root: Path | None = None):
    """Validation for RESEARCH USE: requires the activation-approved
    policy."""
    return _load_validated_policy(repo_root, data_root,
                                  (POLICY_STATE_APPROVED,))


def _schema_policy_dates(repo_root: Path | None = None) -> frozenset[str]:
    """PRIVATE schema-only date set. Exists solely so the disposition
    resolver can obtain dates without recursing through validation; never a
    production eligibility decision."""
    return load_policy(repo_root).dates


def quarantined_sessions(repo_root: Path | None = None,
                         data_root: Path | None = None) -> frozenset[str]:
    """Validated quarantine date set (stale binding fails closed)."""
    policy, _ = load_policy_for_reporting(repo_root, data_root)
    return policy.dates


def is_research_eligible(session, repo_root: Path | None = None,
                         data_root: Path | None = None) -> bool:
    return parse_session_id(session) not in quarantined_sessions(repo_root,
                                                                 data_root)


def assert_session_eligible(session, repo_root: Path | None = None,
                            data_root: Path | None = None) -> None:
    """Refuse a directly requested quarantined session. There is deliberately
    NO override/allow-quarantined parameter."""
    iso = parse_session_id(session)
    if iso in quarantined_sessions(repo_root, data_root):
        raise IneligibleSessionError(
            f"session {iso} is research-INELIGIBLE under PA-0002 "
            "(quarantined holiday/partial session with pending calendar "
            "evidence): it may be normalized for QA but is never research "
            "input"
        )


def _observed_sessions(data_root: Path | None = None) -> list[str]:
    """Session IDs present in the committed coverage artifact, validated as
    canonical, unique and ascending. Session identifiers only — never raw
    file paths."""
    import json

    from nqresearch import paths

    root = data_root or paths.data_root()
    cov = root / "qa" / "m0_closeout" / "mbp1_full_history_coverage.json"
    if not cov.is_file():
        raise EligibilityPolicyError(
            f"coverage artifact missing: {cov}; session universe unknown; "
            "failing closed"
        )
    doc = json.loads(cov.read_text(encoding="utf-8"))
    try:
        ids = [parse_session_id(s["session_id"])
               for s in doc.get("sessions", [])]
    except (InvalidSessionIdError, KeyError, TypeError) as e:
        raise EligibilityPolicyError(
            f"coverage artifact has a non-canonical session id: {e}; "
            "failing closed"
        ) from e
    if len(ids) != len(set(ids)):
        raise EligibilityPolicyError(
            "coverage artifact contains duplicate session ids; failing closed"
        )
    if ids != sorted(ids):
        raise EligibilityPolicyError(
            "coverage artifact session ids are not ascending; failing closed"
        )
    return ids


def eligible_sessions_in_range(start, end, repo_root: Path | None = None,
                               data_root: Path | None = None) -> list[str]:
    """Eligible observed session IDs within an approved range.

    A broad request (e.g. all of DEV) succeeds and simply excludes the
    quarantined sessions — quarantine never makes a partition unusable. A
    range containing no eligible session is refused. Uses the fully
    validated policy.
    """
    a, b = parse_session_id(start), parse_session_id(end)
    if a > b:
        raise IneligibleSessionError(f"malformed range: {a} > {b}")
    # Validation loads the matrix, which verifies the coverage artifact's
    # identity — so the session universe below is only trusted after that
    # binding has been checked.
    policy, _ = load_policy_for_reporting(repo_root, data_root)
    q = policy.dates
    out = [s for s in _observed_sessions(data_root) if a <= s <= b
           and s not in q]
    if not out:
        raise IneligibleSessionError(
            f"no research-eligible session exists in {a}..{b}; refused"
        )
    return out


def assert_window_session_local(sessions_touched,
                                repo_root: Path | None = None,
                                data_root: Path | None = None) -> None:
    """A feature window, label horizon, sample window or evaluation window
    may touch exactly ONE session, which must be a KNOWN observed session and
    must be eligible.

    V1 horizons (≤15 min plus δ) are intraday, so every legitimate window is
    session-local; anything spanning a session boundary — and therefore
    possibly a quarantined session — is refused, as is any malformed or
    unknown session identifier.
    """
    touched = [parse_session_id(s) for s in sessions_touched]
    if not touched:
        raise IneligibleSessionError("window touches no session; refused")
    distinct = sorted(set(touched))
    if len(distinct) > 1:
        raise IneligibleSessionError(
            f"window spans multiple sessions {distinct}: no feature, label, "
            "sample or evaluation window may cross a session boundary "
            "(and therefore may never cross a quarantined session)"
        )
    only = distinct[0]
    assert_session_eligible(only, repo_root, data_root)
    if only not in _observed_sessions(data_root):
        raise IneligibleSessionError(
            f"window references unknown session {only} (not an observed "
            "session in the coverage artifact); refused"
        )


def next_eligible_session(after, repo_root: Path | None = None,
                          data_root: Path | None = None) -> str | None:
    """First eligible observed session strictly after `after` — the session
    at which rolling state must be reset."""
    iso = parse_session_id(after)
    q = quarantined_sessions(repo_root, data_root)
    for s in _observed_sessions(data_root):
        if s > iso and s not in q:
            return s
    return None


def requires_state_reset(session, repo_root: Path | None = None,
                         data_root: Path | None = None) -> bool:
    """True when rolling/EWMA/feature state must be reset before computing
    this session.

    Reset is required when the immediately preceding OBSERVED session was
    quarantined **or** when any quarantined CALENDAR date falls between the
    preceding observed session and this one — the latter covers quarantined
    dates that have no observed session at all (2025-01-01 New Year's Day,
    2025-04-18 Good Friday), after which state must not carry across.
    """
    iso = parse_session_id(session)
    obs = _observed_sessions(data_root)
    if iso not in obs:
        raise EligibilityPolicyError(
            f"{iso} is not an observed session; failing closed"
        )
    i = obs.index(iso)
    if i == 0:
        return True  # no prior state exists; start clean
    prev = obs[i - 1]
    q = quarantined_sessions(repo_root, data_root)
    if prev in q:
        return True
    return any(prev < d < iso for d in q)


def verify_structural_quarantine_invariants(
    repo_root: Path | None = None, data_root: Path | None = None
) -> dict:
    """Mechanically prove the quarantine cannot disturb activation-relevant
    structure, and ASSERT the frozen corpus invariants (never merely report
    whatever an artifact happens to contain). Fail-closed.

    Every quarantined date must lie in DEV, must not be in SELECTION or
    HOLDOUT, must not be a partition boundary, must not be an MBO session,
    must not fall inside any MBO block span, and must not be a causal-roll
    decision source.
    """
    import json

    from nqresearch import paths
    from nqresearch.config import _repo_root

    root = repo_root or _repo_root()
    droot = data_root or paths.data_root()
    close = droot / "qa" / "m0_closeout"

    def _load(name):
        p = close / name
        if not p.is_file():
            raise EligibilityPolicyError(
                f"closeout artifact missing: {p}; structural quarantine "
                "invariants unverifiable; failing closed"
            )
        return json.loads(p.read_text(encoding="utf-8"))

    prop = _load("partition_proposal.json")
    blocks = _load("mbo_blocks_frozen.json")
    rolls = _load("mbp1_front_contract_series.json")
    cov = _load("mbp1_full_history_coverage.json")
    q = sorted(_schema_policy_dates(root))

    p = prop["proposal"]
    dev = (p["DEV"]["start"], p["DEV"]["end"])
    sel = (p["SELECTION"]["start"], p["SELECTION"]["end"])
    hold = (p["HOLDOUT"]["start"], p["HOLDOUT"]["end"])
    boundaries = {dev[0], dev[1], sel[0], sel[1], hold[0], hold[1]}

    mbo_sessions = set()
    spans = []
    for b in blocks["blocks"]:
        mbo_sessions |= set(b["sessions"])
        spans.append((b["mbo_lab_block_id"], b["start"], b["end"]))
    decision_sources = {s["decided_from_session"] for s in rolls["switches"]}

    for d in q:
        if not (dev[0] <= d <= dev[1]):
            raise EligibilityPolicyError(
                f"quarantined date {d} is not inside DEV; failing closed"
            )
        if sel[0] <= d <= sel[1] or hold[0] <= d <= hold[1]:
            raise EligibilityPolicyError(
                f"quarantined date {d} lies in SELECTION or HOLDOUT; "
                "failing closed"
            )
        if d in boundaries:
            raise EligibilityPolicyError(
                f"quarantined date {d} is a partition boundary; failing closed"
            )
        if d in mbo_sessions:
            raise EligibilityPolicyError(
                f"quarantined date {d} is an MBO session; failing closed"
            )
        for bid, s, e in spans:
            if s <= d <= e:
                raise EligibilityPolicyError(
                    f"quarantined date {d} lies inside MBO block {bid} "
                    f"({s}..{e}); failing closed"
                )
        if d in decision_sources:
            raise EligibilityPolicyError(
                f"quarantined date {d} is a causal-roll decision source; "
                "failing closed"
            )

    observed = [s["session_id"] for s in cov.get("sessions", [])]
    dev_obs = [s for s in observed if dev[0] <= s <= dev[1]]
    dev_eligible = [s for s in dev_obs if s not in set(q)]
    spanning = prop.get("mbo_blocks_per_partition", {}).get("SPANNING", [])

    def _require(actual, expected, what):
        if actual != expected:
            raise EligibilityPolicyError(
                f"frozen corpus invariant violated: {what} is {actual!r}, "
                f"expected {expected!r}; failing closed"
            )

    _require(len(q), EXPECTED_QUARANTINED_DATES, "quarantined date count")
    _require(cov.get("n_expected_complete_sessions"),
             EXPECTED_COVERAGE_SESSIONS, "coverage expected sessions")
    for name, exp in EXPECTED_PARTITION_TRADING_DAYS.items():
        _require(p[name].get("trading_days"), exp, f"{name} trading days")
    _require(len(dev_obs), EXPECTED_OBSERVED_DEV_SESSIONS,
             "observed DEV sessions")
    _require(len(dev_eligible), EXPECTED_ELIGIBLE_DEV_SESSIONS,
             "eligible observed DEV sessions")
    _require(len(dev_obs) - len(dev_eligible),
             EXPECTED_EXCLUDED_OBSERVED_DEV_SESSIONS,
             "excluded observed DEV sessions")
    _require(len(mbo_sessions), EXPECTED_MBO_SESSIONS, "MBO sessions")
    _require(blocks.get("n_blocks"), EXPECTED_MBO_BLOCKS, "MBO blocks")
    _require(len(spanning), EXPECTED_SPANNING_BLOCKS, "spanning MBO blocks")
    _require(rolls.get("n_switches"), EXPECTED_ROLL_SWITCHES,
             "causal roll switches")

    return {
        "n_quarantined": len(q),
        "all_in_dev": True,
        "none_in_selection_or_holdout": True,
        "none_is_partition_boundary": True,
        "none_is_mbo_session": True,
        "none_inside_mbo_block_span": True,
        "none_is_roll_decision_source": True,
        "n_coverage_expected_sessions": cov["n_expected_complete_sessions"],
        "n_observed_dev_sessions": len(dev_obs),
        "n_eligible_dev_sessions": len(dev_eligible),
        "n_excluded_observed_dev_sessions": len(dev_obs) - len(dev_eligible),
        "n_mbo_sessions": len(mbo_sessions),
        "n_mbo_blocks": blocks["n_blocks"],
        "n_spanning_mbo_blocks": len(spanning),
        "n_roll_switches": rolls["n_switches"],
    }
