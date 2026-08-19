"""Mechanical holdout fence (canonical §7, §61) — FAIL-CLOSED foundation.

SENSITIVE CODE — status PENDING_INDEPENDENT_AUDIT.

Rules enforced here:
- Research data access requires an ACTIVE partition configuration file
  (config/data/partitions_active.yaml). While none exists — the current
  state, since the closeout proposal is PROPOSED_NOT_ACTIVE — every research
  range request FAILS CLOSED. The proposal artifact is never read to infer
  partitions.
- With an active configuration, any requested range that touches the HOLDOUT
  range (boundaries inclusive) is refused, and ranges must lie fully inside
  DEV ∪ SELECTION (FORWARD is likewise not ordinary research input).
- The PUBLIC fence API takes no repo_root/config parameter: callers cannot
  supply a fabricated configuration. Tests exercise the pure range logic and
  the loader through PRIVATE helpers only.
- There is NO override parameter anywhere in this module. A future holdout
  opening is a separate explicit workflow gated on a committed
  docs/holdout_plan_01.md and an immutable audit event; until that workflow
  exists, holdout_opening() always refuses.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator, model_validator

ACTIVE_PARTITIONS_FILENAME = "partitions_active.yaml"
_SHA256_HEX = set("0123456789abcdef")


class HoldoutFenceError(RuntimeError):
    """Fail-closed refusal of research data access."""


class PartitionsNotActiveError(HoldoutFenceError):
    pass


class HoldoutAccessError(HoldoutFenceError):
    pass


class PartitionRange(BaseModel):
    start: date
    end: date

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _ordered(self):
        if self.start > self.end:
            raise ValueError(f"malformed range: start {self.start} > end {self.end}")
        return self


class ApprovalRecord(BaseModel):
    """Durable approval identity — an arbitrary name string alone is not
    sufficient to activate partitions."""

    approved_by: str
    approval_reference: str  # e.g. audit-log entry ID / signed review document
    approved_at_utc: datetime

    model_config = {"extra": "forbid"}

    @field_validator("approved_by", "approval_reference")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("approval identity fields must be non-empty")
        return v

    @field_validator("approved_at_utc")
    @classmethod
    def _tz_aware_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("approved_at_utc must be timezone-aware")
        if v.utcoffset().total_seconds() != 0:
            raise ValueError("approved_at_utc must be expressed in UTC")
        return v


class ActivePartitions(BaseModel):
    """Schema of config/data/partitions_active.yaml (does not exist yet).

    An eventual activation must bind to the exact approved proposal and
    effective calendar identities plus recorded approval evidence.
    """

    activated: bool
    approval: ApprovalRecord
    partition_proposal_sha256: str  # SHA-256 of the approved proposal artifact
    effective_calendar_sha256: str  # merged-calendar identity at approval time
    dev: PartitionRange
    selection: PartitionRange
    holdout: PartitionRange

    model_config = {"extra": "forbid"}

    @field_validator("partition_proposal_sha256", "effective_calendar_sha256")
    @classmethod
    def _sha256(cls, v: str) -> str:
        if len(v) != 64 or any(c not in _SHA256_HEX for c in v.lower()):
            raise ValueError("must be a 64-hex-char SHA-256 identity")
        return v.lower()

    @model_validator(mode="after")
    def _chronological(self):
        if not (self.dev.end < self.selection.start <= self.selection.end
                < self.holdout.start):
            raise ValueError("partitions must be chronological: DEV < SELECTION < HOLDOUT")
        if not self.activated:
            raise ValueError("partitions file present but activated is not true")
        return self


def _load_active_partitions_from(root: Path) -> ActivePartitions:
    """PRIVATE loader (tests only inject through this). Fail-closed on absent
    or malformed configuration; never falls back to the proposal artifact."""
    path = root / "config" / "data" / ACTIVE_PARTITIONS_FILENAME
    if not path.is_file():
        raise PartitionsNotActiveError(
            "no active partition configuration exists "
            f"({path.name} absent): research data access is FAIL-CLOSED. The "
            "closeout partition proposal is PROPOSED_NOT_ACTIVE and is never "
            "inferred or silently activated."
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return ActivePartitions(**data)
    except Exception as e:  # malformed config must also fail closed
        raise PartitionsNotActiveError(
            f"active partition configuration is malformed; failing closed: {e}"
        ) from e


# The COMPLETE frozen baseline-verification plan for the current corpus
# range: exactly these nine holiday groups (byte-identical to the committed
# overrides meta). Missing, renamed, duplicated, or unexpected groups fail.
EXPECTED_BASELINE_GROUPS = frozenset({
    "Labor Day (2024-09-02, 2025-09-01)",
    "Thanksgiving + day after (2024-11-28/29, 2025-11-27/28)",
    "Christmas / New Year (2024-12-24/25, 2025-01-01, 2025-12-24/25, 2026-01-01)",
    "MLK Day (2025-01-20, 2026-01-19)",
    "Presidents Day (2025-02-17, 2026-02-16)",
    "Good Friday (2025-04-18, 2026-04-03)",
    "Memorial Day (2025-05-26, 2026-05-25)",
    "Juneteenth (2025-06-19, 2026-06-19)",
    "Independence Day (2025-07-04, 2026-07-03)",
})


def _is_sha256_hex(v) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(
        c in _SHA256_HEX for c in v.lower()
    )


def _verify_baseline_calendar_verified(repo_root: Path) -> None:
    """The official-calendar baseline verification must ACTUALLY be complete
    against the COMPLETE frozen plan: exactly the nine expected holiday
    groups, each DOCUMENT_VERIFIED and bound to attributable official-document
    evidence (source reference + document SHA-256). Any pending declared
    document identity (e.g. the Jan-9 mourning-day PDF) blocks activation."""
    ov_path = repo_root / "config" / "data" / "cme_calendar_overrides.yaml"
    if not ov_path.is_file():
        raise PartitionsNotActiveError(
            "calendar overrides file missing; baseline verification state "
            "unknown; failing closed"
        )
    meta = (yaml.safe_load(ov_path.read_text(encoding="utf-8")) or {}).get(
        "meta", {}
    )
    bv = meta.get("baseline_verification", {})
    if bv.get("status") != "DOCUMENT_VERIFIED":
        raise PartitionsNotActiveError(
            "official-calendar baseline verification is "
            f"{bv.get('status')!r}, not DOCUMENT_VERIFIED; failing closed"
        )
    groups = bv.get("groups", [])
    names = [g.get("holiday_group") for g in groups]
    if len(names) != len(set(names)):
        raise PartitionsNotActiveError(
            "duplicate baseline holiday groups; failing closed"
        )
    if set(names) != EXPECTED_BASELINE_GROUPS:
        missing = EXPECTED_BASELINE_GROUPS - set(names)
        extra = set(names) - EXPECTED_BASELINE_GROUPS
        raise PartitionsNotActiveError(
            "baseline verification group set does not exactly match the "
            f"frozen nine-group plan (missing: {sorted(missing)}; "
            f"unexpected: {sorted(extra)}); failing closed"
        )
    for g in groups:
        if g.get("status") != "DOCUMENT_VERIFIED":
            raise PartitionsNotActiveError(
                f"calendar holiday group {g.get('holiday_group')!r} is not "
                "DOCUMENT_VERIFIED; failing closed"
            )
        if not str(g.get("source_reference", "")).strip() or not _is_sha256_hex(
            g.get("document_sha256")
        ):
            raise PartitionsNotActiveError(
                f"calendar holiday group {g.get('holiday_group')!r} is marked "
                "verified without attributable official-document evidence "
                "(source_reference + document_sha256 required); failing closed"
            )
    # Every declared document identity in the overrides references must be a
    # real SHA-256 — the pending Jan-9 identity (null) blocks activation.
    for ref in meta.get("references", []):
        if "document_sha256" in ref and not _is_sha256_hex(ref.get("document_sha256")):
            raise PartitionsNotActiveError(
                f"override reference {ref.get('id')!r} has a pending/invalid "
                "document identity; failing closed"
            )


def _verify_approval_bound_to_audit_record(
    parts: "ActivePartitions", repo_root: Path
) -> None:
    """The claimed immutable human approval must be REAL: the committed
    approval_reference must name an entry in the append-only implementation
    audit log, and that entry must cite the exact approved proposal SHA."""
    import re

    m = re.search(r"AL-\d{3,4}", parts.approval.approval_reference)
    if not m:
        raise PartitionsNotActiveError(
            "approval_reference does not name an audit-log entry (AL-nnnn); "
            "failing closed"
        )
    log_path = repo_root / "docs" / "implementation-audit-log.md"
    if not log_path.is_file():
        raise PartitionsNotActiveError(
            "append-only audit log not found; approval evidence unverifiable; "
            "failing closed"
        )
    text = log_path.read_text(encoding="utf-8")
    heading = f"## {m.group(0)}"
    idx = text.find(heading)
    if idx < 0:
        raise PartitionsNotActiveError(
            f"approval reference {m.group(0)} has no entry in the append-only "
            "audit log; failing closed"
        )
    nxt = text.find("\n## ", idx + len(heading))
    entry = text[idx: nxt if nxt > 0 else len(text)]
    if parts.partition_proposal_sha256 not in entry:
        raise PartitionsNotActiveError(
            f"audit-log entry {m.group(0)} does not cite the approved "
            "proposal SHA-256; approval is not bound to this activation; "
            "failing closed"
        )


def _verify_activation_evidence(
    parts: ActivePartitions, repo_root: Path, data_root: Path
) -> None:
    """Verify the activation binds to ACTUAL evidence, not just well-formed
    hashes: the approved proposal artifact's real SHA-256, exact range
    equality with the proposal, the proposal's structural checks PASS, and
    the CURRENT effective calendar identity. Fabricated 64-hex values fail
    here."""
    import hashlib
    import json

    proposal_path = data_root / "qa" / "m0_closeout" / "partition_proposal.json"
    if not proposal_path.is_file():
        raise PartitionsNotActiveError(
            "activation evidence missing: approved partition_proposal.json "
            "not found; failing closed"
        )
    actual_sha = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    if actual_sha != parts.partition_proposal_sha256:
        raise PartitionsNotActiveError(
            "activation does not bind to the actual approved proposal "
            f"artifact (declared {parts.partition_proposal_sha256[:12]}…, "
            f"actual {actual_sha[:12]}…); failing closed"
        )
    doc = json.loads(proposal_path.read_text(encoding="utf-8"))
    if doc.get("artifact") != "partition_proposal":
        raise PartitionsNotActiveError(
            "bound artifact is not a partition proposal; failing closed"
        )
    if doc.get("status") != "PASS":
        raise PartitionsNotActiveError(
            f"proposal top-level status is {doc.get('status')!r}, not PASS; "
            "failing closed"
        )
    MANDATORY_CHECKS = {
        "boundaries_on_trading_days",
        "partition_ranges_contiguous",
        "no_partition_spanning_mbo_blocks",
    }
    checks = {c.get("check"): c.get("status") for c in doc.get("checks", [])}
    if set(checks) != MANDATORY_CHECKS:
        raise PartitionsNotActiveError(
            f"proposal structural-check set {sorted(checks)} does not exactly "
            f"match the mandatory set {sorted(MANDATORY_CHECKS)}; failing closed"
        )
    if any(status != "PASS" for status in checks.values()):
        raise PartitionsNotActiveError(
            f"approved proposal's structural checks are not all PASS "
            f"({checks}); failing closed"
        )
    # Internal coherence: state, activation_ready, and calendar verification
    # must AGREE on the single activation-approved combination; any
    # contradictory mixture fails closed.
    state = doc.get("state")
    ready = doc.get("activation_ready")
    cal_state = doc.get("calendar_verification_state")
    if state != "APPROVED_FOR_ACTIVATION":
        raise PartitionsNotActiveError(
            f"proposal state is {state!r}, not APPROVED_FOR_ACTIVATION "
            "(a PROPOSED_NOT_ACTIVE artifact can never activate, regardless "
            "of other flags); failing closed"
        )
    if ready is not True:
        raise PartitionsNotActiveError(
            "proposal activation_ready is not true (contradicts the approved "
            "state); failing closed"
        )
    if cal_state != "DOCUMENT_VERIFIED":
        raise PartitionsNotActiveError(
            "proposal calendar_verification_state is "
            f"{cal_state!r}, not DOCUMENT_VERIFIED (contradicts the approved "
            "state); failing closed"
        )
    _verify_baseline_calendar_verified(repo_root)
    _verify_approval_bound_to_audit_record(parts, repo_root)
    prop = doc.get("proposal", {})
    expected = {
        "dev": parts.dev, "selection": parts.selection, "holdout": parts.holdout,
    }
    for name, rng in expected.items():
        p = prop.get(name.upper(), {})
        if (p.get("start") != rng.start.isoformat()
                or p.get("end") != rng.end.isoformat()):
            raise PartitionsNotActiveError(
                f"active {name.upper()} range {rng.start}..{rng.end} does not "
                f"exactly equal the approved proposal "
                f"({p.get('start')}..{p.get('end')}); failing closed"
            )
    from nqresearch.calendar import calendar_identity

    cal_sha = calendar_identity(repo_root)["effective_calendar_sha256"]
    if cal_sha != parts.effective_calendar_sha256:
        raise PartitionsNotActiveError(
            "active configuration binds a different effective calendar than "
            "the current one; failing closed"
        )


def load_active_partitions() -> ActivePartitions:
    """PUBLIC loader: fixed to the real repository configuration and the real
    data root; no caller can point it at a fabricated tree. Verifies both the
    schema AND the actual activation evidence."""
    from nqresearch import paths
    from nqresearch.config import _repo_root

    root = _repo_root()
    parts = _load_active_partitions_from(root)
    _verify_activation_evidence(parts, root, paths.data_root())
    return parts


def _check_range(start: date, end: date, parts: ActivePartitions) -> None:
    """Pure range logic (private; unit-tested directly)."""
    if start > end:
        raise HoldoutFenceError(f"malformed request range: {start} > {end}")
    h = parts.holdout
    if start <= h.end and end >= h.start:
        raise HoldoutAccessError(
            f"requested range {start}..{end} overlaps HOLDOUT "
            f"{h.start}..{h.end}: refused (canonical §6.3/§7). Holdout access "
            "requires the separate explicit opening workflow."
        )
    allowed = (
        (parts.dev.start <= start and end <= parts.dev.end)
        or (parts.selection.start <= start and end <= parts.selection.end)
        or (parts.dev.start <= start and end <= parts.selection.end
            and start <= parts.dev.end)
    )
    if not allowed:
        raise HoldoutFenceError(
            f"requested range {start}..{end} is not fully inside "
            "DEV ∪ SELECTION; refused (FORWARD/holdout/out-of-partition data "
            "is not ordinary research input)"
        )


def assert_research_range_allowed(start: date, end: date) -> ActivePartitions:
    """Gate every ordinary research data request on the ACTIVE partitions.

    PUBLIC API: no configuration-injection parameter exists. Refuses
    (fail-closed): missing/malformed active config; malformed request ranges;
    any overlap with HOLDOUT (inclusive); any date outside DEV ∪ SELECTION.
    """
    parts = load_active_partitions()
    _check_range(start, end, parts)
    return parts


def holdout_opening(*_args, **_kwargs):
    """The ONLY intended future path to holdout data. Not implemented in the
    Milestone 1 foundation: always refuses (canonical §7 requires a committed
    docs/holdout_plan_01.md, a frozen evaluation plan, and an immutable audit
    event; at most two historical openings)."""
    raise HoldoutFenceError(
        "holdout opening workflow is not implemented in the V1 foundation; "
        "no code path may read HOLDOUT data"
    )
