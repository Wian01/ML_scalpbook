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

    An eventual activation must bind to the exact approved proposal,
    effective calendar, calendar-evidence matrix and CME archive-
    unavailability correspondence identities plus recorded approval evidence
    (PA-0001).
    """

    activated: bool
    approval: ApprovalRecord
    partition_proposal_sha256: str  # SHA-256 of the approved proposal artifact
    effective_calendar_sha256: str  # merged-calendar identity at approval time
    evidence_matrix_sha256: str     # committed cme_calendar_evidence.yaml file
    cme_correspondence_sha256: str  # immutable GCC archive-unavailability .eml
    research_eligibility_sha256: str  # committed PA-0002 quarantine policy
    # Activation-relevant STRUCTURAL artifacts, bound by exact identity so a
    # modified artifact cannot make an unsafe quarantine look safe.
    coverage_artifact_sha256: str
    mbo_blocks_sha256: str
    front_contract_series_sha256: str
    dev: PartitionRange
    selection: PartitionRange
    holdout: PartitionRange

    model_config = {"extra": "forbid"}

    @field_validator("partition_proposal_sha256", "effective_calendar_sha256",
                     "evidence_matrix_sha256", "cme_correspondence_sha256",
                     "research_eligibility_sha256", "coverage_artifact_sha256",
                     "mbo_blocks_sha256", "front_contract_series_sha256")
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


_STRUCTURAL_ARTIFACTS = {
    # attr -> (relative path, artifact name, required keys, allowed statuses)
    # Per-artifact acceptance: no generic PASS-or-WARN rule. Coverage may be
    # a substantively coherent PASS or the ONE understood 2025-04-18 Good
    # Friday WARN — coherence between status, checks and the machine-readable
    # missing-session field is enforced by _coverage_substance_problems(),
    # which the generation-time input validator uses as well. The frozen MBO
    # blocks and the causal front series must be PASS.
    "coverage_artifact_sha256": (
        "mbp1_full_history_coverage.json", "mbp1_full_history_coverage",
        ("sessions", "n_expected_complete_sessions"),
        ("PASS", "WARN"),
    ),
    "mbo_blocks_sha256": (
        "mbo_blocks_frozen.json", "mbo_blocks_frozen",
        ("blocks", "n_blocks"), ("PASS",),
    ),
    "front_contract_series_sha256": (
        "mbp1_front_contract_series.json", "mbp1_front_contract_series",
        ("switches", "n_switches"), ("PASS",),
    ),
}


def _verify_artifact_envelope(fname: str, doc: dict) -> None:
    """Activation-bound artifacts must carry a trustworthy provenance
    envelope under the AL-0043/44/45 policy: generated from a clean
    committed tree at a real ancestral commit of the ACTUAL project
    repository, under the CURRENT effective config and package code.
    Historical artifacts predating that policy are therefore
    activation-INELIGIBLE until a reviewed clean-tree regeneration."""
    from nqresearch import paths
    from nqresearch.config import effective_config_hash
    from nqresearch.qa.cache import package_source_hash
    from nqresearch.sources import ProvenanceError, _verify_committed_ancestor

    clean = doc.get("generation_git_clean")
    if clean is not True or not isinstance(clean, bool):
        raise PartitionsNotActiveError(
            f"activation-bound artifact {fname} has generation_git_clean="
            f"{clean!r} (must be exactly boolean true): it was not generated "
            "from a clean committed tree; failing closed"
        )
    sha = doc.get("git_sha")
    import re as _re
    if not (isinstance(sha, str) and _re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise PartitionsNotActiveError(
            f"activation-bound artifact {fname} has no valid committed "
            f"git_sha ({sha!r}); failing closed"
        )
    try:
        _verify_committed_ancestor(sha, paths.ROOT)
    except ProvenanceError as e:
        raise PartitionsNotActiveError(
            f"activation-bound artifact {fname}: {e}"
        ) from e
    if doc.get("config_hash") != effective_config_hash():
        raise PartitionsNotActiveError(
            f"activation-bound artifact {fname} was generated under a "
            "different effective configuration; failing closed"
        )
    if doc.get("audit_code_hash") != package_source_hash():
        raise PartitionsNotActiveError(
            f"activation-bound artifact {fname} was generated by different "
            "package code; failing closed"
        )


def _verify_structural_artifacts(parts: "ActivePartitions", matrix,
                                 data_root: Path, repo_root: Path,
                                 proposal_doc: dict) -> None:
    """Bind the activation-relevant structural artifacts by exact identity
    BEFORE trusting their content, so a modified/substituted artifact cannot
    make an unsafe quarantine appear safe. Also requires a single truth for
    the coverage artifact: the identity the evidence matrix already verified
    must equal the one the active configuration binds."""
    import hashlib
    import json

    close = data_root / "qa" / "m0_closeout"
    for attr, (fname, artifact_name, keys, allowed_status) in \
            _STRUCTURAL_ARTIFACTS.items():
        declared = getattr(parts, attr)
        p = close / fname
        if not p.is_file():
            raise PartitionsNotActiveError(
                f"activation-bound structural artifact missing: {p}; "
                "failing closed"
            )
        raw = p.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != declared:
            raise PartitionsNotActiveError(
                f"structural artifact {fname} identity mismatch (declared "
                f"{declared[:12]}…, actual {actual[:12]}…): stale, "
                "substituted or tampered evidence; failing closed"
            )
        try:
            doc = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise PartitionsNotActiveError(
                f"structural artifact {fname} is malformed: {e}; "
                "failing closed"
            ) from e
        if doc.get("artifact") != artifact_name:
            raise PartitionsNotActiveError(
                f"structural artifact {fname} declares artifact "
                f"{doc.get('artifact')!r}, expected {artifact_name!r}; "
                "failing closed"
            )
        if doc.get("status") not in allowed_status:
            raise PartitionsNotActiveError(
                f"structural artifact {fname} status {doc.get('status')!r} "
                f"is not one of the permitted statuses {allowed_status}; "
                "failing closed"
            )
        for k in keys:
            if k not in doc:
                raise PartitionsNotActiveError(
                    f"structural artifact {fname} is missing required key "
                    f"{k!r}; failing closed"
                )
        if artifact_name == "mbp1_full_history_coverage":
            # A WARN top-level status is NOT generically acceptable: only the
            # specifically understood 2025-04-18 pre-RTH Good Friday WARN is,
            # and the substantive invariants must hold.
            from nqresearch.qa.closeout import _coverage_substance_problems

            problems = _coverage_substance_problems(doc, fname)
            if problems:
                raise PartitionsNotActiveError(
                    f"coverage artifact is not in the understood state: "
                    f"{problems}; failing closed pending review"
                )
        _verify_artifact_envelope(fname, doc)
    # The approved PROPOSAL must itself have embedded the same structural
    # identities the active configuration binds — one truth, not two.
    embedded = (proposal_doc.get("research_eligibility_binding", {})
                .get("structural_artifact_sha256"))
    if not isinstance(embedded, dict):
        raise PartitionsNotActiveError(
            "the approved proposal embeds no structural_artifact_sha256 "
            "binding (regenerate under PA-0002); failing closed"
        )
    for attr in _STRUCTURAL_ARTIFACTS:
        if embedded.get(attr) != getattr(parts, attr):
            raise PartitionsNotActiveError(
                f"active configuration {attr} does not equal the identity "
                "embedded in the approved partition proposal; failing closed"
            )
    # ONE truth for coverage: the matrix-verified identity must equal the
    # identity bound by the active configuration.
    matrix_cov = (matrix.meta or {}).get("observed_reference", {}).get(
        "artifact_sha256"
    )
    if matrix_cov is None or str(matrix_cov).lower() != \
            parts.coverage_artifact_sha256:
        raise PartitionsNotActiveError(
            "the coverage identity bound by the active configuration does "
            "not equal the identity verified through the evidence matrix; "
            "failing closed"
        )


def _verify_calendar_evidence(
    parts: "ActivePartitions", repo_root: Path, data_root: Path,
    proposal_cal_state: str | None = None,
    proposal_doc: dict | None = None,
) -> None:
    """Date-level calendar evidence gate (PA-0001, supersedes the group-level
    DOCUMENT_VERIFIED-only gate after CME GCC confirmed the historical
    archive does not exist).

    Activation requires ALL of:
    - the committed evidence matrix validates against the immutable evidence
      files AND the live coverage artifact (hash + observed cross-checks);
    - EVERY exceptional date is DOCUMENT_VERIFIED or
      TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE — no pending dates, no
      conflicts;
    - the active configuration binds the exact matrix file hash and the
      exact GCC archive-unavailability email hash;
    - the overrides file's group summaries agree exactly with the matrix
      (conservative weakest-member roll-ups over the frozen nine groups) and
      declare the completed policy state;
    - the Jan-9 mourning reference carries the real PDF hash.
    """
    from nqresearch import calendar_evidence as ce

    from nqresearch import eligibility as el

    try:
        matrix = ce.load_validated_matrix(repo_root, data_root)
    except ce.CalendarEvidenceError as e:
        raise PartitionsNotActiveError(str(e)) from e

    # PA-0002: pending dates are DISPOSITIONED by the reviewed quarantine
    # policy, never resolved by editing evidence. Conflicts always block, and
    # ONLY an APPROVED_FOR_ACTIVATION policy may ever activate — a proposed
    # or merely implemented policy always fails here.
    try:
        policy, disposition = el.load_policy_for_activation(
            repo_root, data_root)
    except (ce.CalendarEvidenceError, el.EligibilityPolicyError) as e:
        raise PartitionsNotActiveError(str(e)) from e

    # The policy hash is bound in BOTH dispositions, never only under
    # quarantine.
    actual_policy_sha = el.policy_sha256(repo_root)
    if parts.research_eligibility_sha256 != actual_policy_sha:
        raise PartitionsNotActiveError(
            "activation does not bind the actual research-eligibility "
            f"policy (declared {parts.research_eligibility_sha256[:12]}…, "
            f"actual {actual_policy_sha[:12]}…); failing closed"
        )
    # Structural artifact identities are verified in BOTH dispositions,
    # BEFORE any of their content is trusted.
    _verify_structural_artifacts(parts, matrix, data_root, repo_root,
                                 proposal_doc or {})
    if disposition == ce.DISPOSITION_PENDING_DATES_QUARANTINED:
        # Quarantined dates must be structurally incapable of disturbing
        # partitions, MBO blocks, or the causal roll series, and the frozen
        # corpus invariants must hold exactly.
        try:
            el.verify_structural_quarantine_invariants(repo_root, data_root)
        except el.EligibilityPolicyError as e:
            raise PartitionsNotActiveError(str(e)) from e
    # The proposal artifact must declare exactly the state implied by the
    # disposition, in BOTH branches — a quarantine disposition may never
    # present itself as DOCUMENT_VERIFIED or as evidence-complete, and an
    # evidence-complete disposition may never hide behind a provisional
    # label.
    expected_cal_state = (
        ce.CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED
        if disposition == ce.DISPOSITION_PENDING_DATES_QUARANTINED
        else ce.CALENDAR_EVIDENCE_COMPLETE_STATE
    )
    if proposal_cal_state is not None and \
            proposal_cal_state != expected_cal_state:
        raise PartitionsNotActiveError(
            f"proposal calendar_verification_state {proposal_cal_state!r} "
            f"does not match the actual disposition {disposition} (expected "
            f"{expected_cal_state}); failing closed"
        )
    actual_matrix_sha = ce.matrix_file_sha256(repo_root)
    if parts.evidence_matrix_sha256 != actual_matrix_sha:
        raise PartitionsNotActiveError(
            "activation does not bind the actual calendar evidence matrix "
            f"(declared {parts.evidence_matrix_sha256[:12]}…, actual "
            f"{actual_matrix_sha[:12]}…); failing closed"
        )
    sources = {s.id: s for s in matrix.sources}
    email = sources[matrix.archive_unavailability.email_source]
    email_sha = email.files[0].sha256
    if parts.cme_correspondence_sha256 != email_sha:
        raise PartitionsNotActiveError(
            "activation does not bind the verified CME archive-"
            "unavailability correspondence hash; failing closed"
        )

    ov_path = repo_root / "config" / "data" / "cme_calendar_overrides.yaml"
    if not ov_path.is_file():
        raise PartitionsNotActiveError(
            "calendar overrides file missing; calendar evidence state "
            "unknown; failing closed"
        )
    meta = (yaml.safe_load(ov_path.read_text(encoding="utf-8")) or {}).get(
        "meta", {}
    )
    bv = meta.get("baseline_verification", {})
    # Under a quarantine disposition the overrides summary must remain the
    # TRUTHFUL provisional state: document verification really is still
    # pending, and quarantine never relabels the calendar as verified.
    expected_status = (
        ce.CALENDAR_EVIDENCE_COMPLETE_STATE
        if disposition == ce.DISPOSITION_EVIDENCE_COMPLETE
        else ce.CALENDAR_EVIDENCE_PENDING_STATE
    )
    if bv.get("status") != expected_status:
        raise PartitionsNotActiveError(
            "overrides calendar-evidence status is "
            f"{bv.get('status')!r}, not {expected_status} (required under "
            f"disposition {disposition}); failing closed"
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
    rollups = ce.group_states(matrix)
    date_states = {d.date.isoformat(): d.state for d in matrix.dates}
    for g in groups:
        name = g.get("holiday_group")
        if g.get("status") != rollups.get(name):
            raise PartitionsNotActiveError(
                f"overrides group {name!r} declares status "
                f"{g.get('status')!r} but the evidence matrix rolls up to "
                f"{rollups.get(name)!r} (weakest member); failing closed"
            )
        for iso, st in (g.get("dates") or {}).items():
            if date_states.get(str(iso)) != st:
                raise PartitionsNotActiveError(
                    f"overrides group {name!r} declares {iso} as {st!r} but "
                    f"the evidence matrix records "
                    f"{date_states.get(str(iso))!r}; failing closed"
                )
    # The Jan-9 mourning reference must carry the REAL official PDF hash.
    mourning = sources.get("cme-mourning-2025-pdf")
    for ref in meta.get("references", []):
        if "document_sha256" in ref:
            declared = ref.get("document_sha256")
            if not _is_sha256_hex(declared):
                raise PartitionsNotActiveError(
                    f"override reference {ref.get('id')!r} has a pending/"
                    "invalid document identity; failing closed"
                )
            if (ref.get("id") == "cme-2025-01-09-mourning"
                    and (mourning is None
                         or declared.lower() != mourning.files[0].sha256)):
                raise PartitionsNotActiveError(
                    "override Jan-9 mourning reference hash does not match "
                    "the verified official PDF evidence; failing closed"
                )


def _verify_approval_bound_to_audit_record(
    parts: "ActivePartitions", repo_root: Path
) -> None:
    """The claimed immutable human approval must be REAL: the committed
    approval_reference must name an entry in the append-only implementation
    audit log, and that entry must cite the exact approved proposal SHA, the
    exact calendar-evidence matrix SHA, and the exact CME archive-
    unavailability correspondence SHA (PA-0001)."""
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
    required = {
        "proposal SHA-256": parts.partition_proposal_sha256,
        "evidence matrix SHA-256": parts.evidence_matrix_sha256,
        "CME correspondence SHA-256": parts.cme_correspondence_sha256,
        "research-eligibility policy SHA-256":
            parts.research_eligibility_sha256,
        "coverage artifact SHA-256": parts.coverage_artifact_sha256,
        "MBO blocks SHA-256": parts.mbo_blocks_sha256,
        "front-contract series SHA-256": parts.front_contract_series_sha256,
    }
    for what, sha in required.items():
        if sha not in entry:
            raise PartitionsNotActiveError(
                f"audit-log entry {m.group(0)} does not cite the {what}; "
                "approval is not bound to this activation's exact evidence; "
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
    # The proposal itself must carry a trustworthy CURRENT envelope BEFORE
    # any of its status, checks, state, readiness, ranges or embedded
    # identities are trusted.
    _verify_artifact_envelope("partition_proposal.json", doc)
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
    from nqresearch.calendar_evidence import (
        CALENDAR_EVIDENCE_COMPLETE_STATE,
        CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
    )
    if cal_state not in ("DOCUMENT_VERIFIED", CALENDAR_EVIDENCE_COMPLETE_STATE,
                         CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED):
        raise PartitionsNotActiveError(
            "proposal calendar_verification_state is "
            f"{cal_state!r}, not DOCUMENT_VERIFIED, "
            f"{CALENDAR_EVIDENCE_COMPLETE_STATE} or "
            f"{CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED} (contradicts the "
            "approved state); failing closed"
        )
    _verify_calendar_evidence(parts, repo_root, data_root, cal_state, doc)
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
