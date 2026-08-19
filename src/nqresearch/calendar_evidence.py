"""Date-level CME calendar evidence model (protocol amendment PA-0001).

SENSITIVE CODE — feeds partition-activation safety. Status
PENDING_INDEPENDENT_AUDIT.

CME GCC officially confirmed (2026-08-19) that no archive of previous years'
holiday calendars exists. This module therefore replaces the impossible
blanket "official document per holiday group" requirement with an explicit,
per-date evidence model over a fixed hierarchy:

  1. Official CME published schedule/export for the applicable date.
  2. Official CME GCC correspondence establishing archive (un)availability.
  3. Observed canonical Databento MBP-1 session behaviour.
  4. Strong/partial secondary sources (NinjaTrader, AMP GCC material, dated
     broker/news schedules) for the exact date and claim.
  5. Lower-tier secondary (CrossTrade) — corroboration only.
  6. Tertiary date-only cross-checks (Kibot) — never session times.

Evidence states per date (never per recurring group alone):

  DOCUMENT_VERIFIED                          an official CME artifact proves
                                             the applicable date and schedule
  TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE  archive unavailability (verified
                                             GCC email) + observed canonical
                                             data + at least one qualifying
                                             independent secondary source,
                                             with no material conflict
  PENDING_EVIDENCE                           insufficient evidence
  CONFLICT_REQUIRES_REVIEW                   sources materially disagree

Fail-closed guarantees enforced here:
- The matrix must cover EXACTLY the frozen exceptional-date set.
- A source can only support dates it explicitly declares (a 2026 document can
  never promote a 2024/2025 date).
- Every evidence file hash is verified against the immutable copy under
  <data_root>/reference/cme_calendar/ — fabricated hashes fail.
- The GCC email is authenticity-pinned (sender domain + hash) and is
  mechanically barred from proving session times (tier gating).
- Lower-tier/date-only sources can never produce a triangulated state.
- Missing observed data blocks triangulation.
- Group roll-ups are conservative: a group is only as strong as its weakest
  member date.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

EVIDENCE_MATRIX_FILENAME = "cme_calendar_evidence.yaml"

STATE_DOCUMENT_VERIFIED = "DOCUMENT_VERIFIED"
STATE_TRIANGULATED = "TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE"
STATE_PENDING = "PENDING_EVIDENCE"
STATE_CONFLICT = "CONFLICT_REQUIRES_REVIEW"
EVIDENCE_STATES = frozenset({
    STATE_DOCUMENT_VERIFIED, STATE_TRIANGULATED, STATE_PENDING, STATE_CONFLICT,
})
# Conservative strength order for group roll-ups: a group rolls up to its
# WEAKEST member. A material conflict is weaker than merely-missing evidence.
_STATE_STRENGTH = {
    STATE_CONFLICT: 0, STATE_PENDING: 1,
    STATE_TRIANGULATED: 2, STATE_DOCUMENT_VERIFIED: 3,
}

TIER_OFFICIAL_CME = "OFFICIAL_CME"
TIER_OFFICIAL_CME_CORRESPONDENCE = "OFFICIAL_CME_CORRESPONDENCE"
TIER_SECONDARY_STRONG = "SECONDARY_STRONG"
TIER_SECONDARY_PARTIAL = "SECONDARY_PARTIAL"
TIER_SECONDARY_LOWER = "SECONDARY_LOWER"
TIER_TERTIARY_DATE_ONLY = "TERTIARY_DATE_ONLY"
SOURCE_TIERS = frozenset({
    TIER_OFFICIAL_CME, TIER_OFFICIAL_CME_CORRESPONDENCE, TIER_SECONDARY_STRONG,
    TIER_SECONDARY_PARTIAL, TIER_SECONDARY_LOWER, TIER_TERTIARY_DATE_ONLY,
})
# Only these tiers can supply the independent secondary corroboration that a
# triangulated state requires — CrossTrade-class and date-only sources never
# suffice, and the GCC correspondence never proves session times.
TRIANGULATION_CORROBORATION_TIERS = frozenset({
    TIER_SECONDARY_STRONG, TIER_SECONDARY_PARTIAL,
})

CLAIM_DIRECT = "DIRECT"
CLAIM_DOCUMENTED_INFERENCE = "DOCUMENTED_INFERENCE"
CLAIM_DATE_ONLY = "DATE_ONLY"
CLAIM_KINDS = frozenset({CLAIM_DIRECT, CLAIM_DOCUMENTED_INFERENCE, CLAIM_DATE_ONLY})
# Claim kinds that can carry schedule content (a DATE_ONLY claim never can).
_SCHEDULE_CLAIM_KINDS = frozenset({CLAIM_DIRECT, CLAIM_DOCUMENTED_INFERENCE})

AGREEMENT_AGREES = "AGREES"
AGREEMENT_DISCREPANCY = "DISCREPANCY"
AGREEMENT_NOT_ASSESSABLE = "NOT_ASSESSABLE"
AGREEMENTS = frozenset({
    AGREEMENT_AGREES, AGREEMENT_DISCREPANCY, AGREEMENT_NOT_ASSESSABLE,
})

MOURNING_GROUP = "National Day of Mourning (2025-01-09)"

# The COMPLETE frozen exceptional-session set of the effective calendar inside
# the corpus (21 early closes + 4 full holidays + the 2025-01-09 mourning
# day), each bound to its frozen holiday group. The matrix must cover exactly
# these dates — no more, no fewer, no renames.
EXPECTED_EXCEPTIONAL_DATES: dict[str, str] = {
    "2024-09-02": "Labor Day (2024-09-02, 2025-09-01)",
    "2024-11-28": "Thanksgiving + day after (2024-11-28/29, 2025-11-27/28)",
    "2024-11-29": "Thanksgiving + day after (2024-11-28/29, 2025-11-27/28)",
    "2024-12-24": "Christmas / New Year (2024-12-24/25, 2025-01-01, 2025-12-24/25, 2026-01-01)",
    "2024-12-25": "Christmas / New Year (2024-12-24/25, 2025-01-01, 2025-12-24/25, 2026-01-01)",
    "2025-01-01": "Christmas / New Year (2024-12-24/25, 2025-01-01, 2025-12-24/25, 2026-01-01)",
    "2025-01-09": MOURNING_GROUP,
    "2025-01-20": "MLK Day (2025-01-20, 2026-01-19)",
    "2025-02-17": "Presidents Day (2025-02-17, 2026-02-16)",
    "2025-04-18": "Good Friday (2025-04-18, 2026-04-03)",
    "2025-05-26": "Memorial Day (2025-05-26, 2026-05-25)",
    "2025-06-19": "Juneteenth (2025-06-19, 2026-06-19)",
    "2025-07-03": "Independence Day (2025-07-04, 2026-07-03)",
    "2025-07-04": "Independence Day (2025-07-04, 2026-07-03)",
    "2025-09-01": "Labor Day (2024-09-02, 2025-09-01)",
    "2025-11-27": "Thanksgiving + day after (2024-11-28/29, 2025-11-27/28)",
    "2025-11-28": "Thanksgiving + day after (2024-11-28/29, 2025-11-27/28)",
    "2025-12-24": "Christmas / New Year (2024-12-24/25, 2025-01-01, 2025-12-24/25, 2026-01-01)",
    "2025-12-25": "Christmas / New Year (2024-12-24/25, 2025-01-01, 2025-12-24/25, 2026-01-01)",
    "2026-01-01": "Christmas / New Year (2024-12-24/25, 2025-01-01, 2025-12-24/25, 2026-01-01)",
    "2026-01-19": "MLK Day (2025-01-20, 2026-01-19)",
    "2026-02-16": "Presidents Day (2025-02-17, 2026-02-16)",
    "2026-04-03": "Good Friday (2025-04-18, 2026-04-03)",
    "2026-05-25": "Memorial Day (2025-05-26, 2026-05-25)",
    "2026-06-19": "Juneteenth (2025-06-19, 2026-06-19)",
    "2026-07-03": "Independence Day (2025-07-04, 2026-07-03)",
}

# Artifact-level verification state stamped on regenerated proposal/blocks
# artifacts once (and only once) every date is resolved without conflicts.
CALENDAR_EVIDENCE_COMPLETE_STATE = "CALENDAR_EVIDENCE_COMPLETE_DATE_LEVEL"
CALENDAR_EVIDENCE_PENDING_STATE = "PROVISIONAL_DOCUMENT_VERIFICATION_PENDING"
# PA-0002: pending dates may be DISPOSITIONED (not resolved) by a reviewed
# research-eligibility quarantine. The calendar stays explicitly PROVISIONAL
# and no evidence state is ever upgraded or relabelled by this mechanism.
CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED = (
    "PROVISIONAL_PENDING_DATES_QUARANTINED"
)

DISPOSITION_EVIDENCE_COMPLETE = "EVIDENCE_COMPLETE"
DISPOSITION_PENDING_DATES_QUARANTINED = "PENDING_DATES_QUARANTINED"

_SHA256_HEX = set("0123456789abcdef")


class CalendarEvidenceError(RuntimeError):
    """Fail-closed refusal: the evidence matrix is missing, malformed,
    unverifiable against the immutable evidence files, or internally
    inconsistent."""


def _is_sha256_hex(v) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(
        c in _SHA256_HEX for c in v.lower()
    )


class EvidenceFile(BaseModel):
    file: str
    sha256: str

    model_config = {"extra": "forbid"}

    @field_validator("sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not _is_sha256_hex(v):
            raise ValueError("sha256 must be 64 hex chars")
        return v.lower()


class SourceClaim(BaseModel):
    """One attributable claim a source makes, with a STABLE id: date-level
    evidence references bind to (source, claim_id), never to free text, so a
    renamed/removed/invented claim fails validation."""

    id: str
    text: str

    model_config = {"extra": "forbid"}

    @field_validator("id", "text")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("claim id/text must be non-empty")
        return v


class EvidenceSource(BaseModel):
    id: str
    tier: str
    title: str
    url: str
    retrieval_method: str
    retrieved_utc: datetime
    files: list[EvidenceFile]
    applicable_dates: list[date]
    claims: list[SourceClaim]
    limitations: list[str] = []

    model_config = {"extra": "forbid"}

    @field_validator("tier")
    @classmethod
    def _tier(cls, v: str) -> str:
        if v not in SOURCE_TIERS:
            raise ValueError(f"unknown source tier {v!r}")
        return v

    @field_validator("files")
    @classmethod
    def _at_least_one_file(cls, v):
        if not v:
            raise ValueError("a source must carry at least one evidence file")
        return v

    @field_validator("applicable_dates")
    @classmethod
    def _dates(cls, v):
        if not v:
            raise ValueError("a source must declare its applicable dates")
        if len(v) != len(set(v)):
            raise ValueError("duplicate applicable dates")
        return v

    @field_validator("claims")
    @classmethod
    def _claims(cls, v):
        if not v:
            raise ValueError("a source must declare at least one claim")
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate claim ids within a source")
        return v


class EvidenceRef(BaseModel):
    source: str
    claim_id: str
    kind: str

    model_config = {"extra": "forbid"}

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in CLAIM_KINDS:
            raise ValueError(f"unknown claim kind {v!r}")
        return v

    @field_validator("claim_id")
    @classmethod
    def _claim(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("claim_id must be non-empty")
        return v


class ObservedBehaviour(BaseModel):
    session_present: bool
    rth_span_seconds: float | None
    expected_rth_span_seconds: float | None
    data_available: bool
    note: str

    model_config = {"extra": "forbid"}


class DateEvidence(BaseModel):
    date: date
    holiday_group: str
    instrument_scope: str
    expected_ct: str
    observed: ObservedBehaviour
    evidence: list[EvidenceRef]
    agreement: str
    state: str
    limitations: list[str] = []

    model_config = {"extra": "forbid"}

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in EVIDENCE_STATES:
            raise ValueError(f"unknown evidence state {v!r}")
        return v

    @field_validator("agreement")
    @classmethod
    def _agreement(cls, v: str) -> str:
        if v not in AGREEMENTS:
            raise ValueError(f"unknown agreement value {v!r}")
        return v


class ArchiveUnavailability(BaseModel):
    statement: str
    email_source: str
    sender: str
    sender_mailbox: str  # exact From mailbox, e.g. gcc@cmegroup.com
    sender_domain: str
    subject: str
    message_date_utc: datetime
    message_id: str
    authentication: str
    body_statement: str  # exact archive-unavailability sentence in the body
    referral_url: str

    model_config = {"extra": "forbid"}


class EvidenceMatrix(BaseModel):
    meta: dict
    archive_unavailability: ArchiveUnavailability
    sources: list[EvidenceSource]
    dates: list[DateEvidence]

    model_config = {"extra": "forbid"}


def matrix_path(repo_root: Path) -> Path:
    return repo_root / "config" / "data" / EVIDENCE_MATRIX_FILENAME


def matrix_file_sha256(repo_root: Path) -> str:
    p = matrix_path(repo_root)
    if not p.is_file():
        raise CalendarEvidenceError(
            f"calendar evidence matrix missing: {p}; failing closed"
        )
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_matrix(repo_root: Path) -> EvidenceMatrix:
    """Parse + schema-validate only. Full evidence verification requires
    validate_matrix() against the immutable evidence directory."""
    p = matrix_path(repo_root)
    if not p.is_file():
        raise CalendarEvidenceError(
            f"calendar evidence matrix missing: {p}; failing closed"
        )
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return EvidenceMatrix(**doc)
    except CalendarEvidenceError:
        raise
    except Exception as e:
        raise CalendarEvidenceError(
            f"calendar evidence matrix malformed; failing closed: {e}"
        ) from e


def _contained(root: Path, relpath: str, what: str) -> Path:
    """Strict Windows-safe containment (shared resolver in nqresearch.
    rawguard): traversal, absolute/drive/root-relative/UNC forms, and
    symlink/junction or prefix-collision escapes all fail closed — a
    matching SHA-256 can never make an out-of-root file acceptable. The
    RESOLVED path is returned and must be used for the actual read."""
    from nqresearch.rawguard import PathContainmentError, resolve_strictly_contained

    try:
        return resolve_strictly_contained(root, relpath)
    except PathContainmentError as e:
        raise CalendarEvidenceError(
            f"{what} path containment violation; failing closed: {e}"
        ) from e


def _verify_file_hashes(matrix: EvidenceMatrix, evidence_dir: Path) -> None:
    for s in matrix.sources:
        for f in s.files:
            p = _contained(evidence_dir, f.file,
                           f"evidence file of source {s.id!r}")
            if not p.is_file():
                raise CalendarEvidenceError(
                    f"evidence file missing for source {s.id!r}: {p}; "
                    "failing closed"
                )
            actual = hashlib.sha256(p.read_bytes()).hexdigest()
            if actual != f.sha256:
                raise CalendarEvidenceError(
                    f"evidence file hash mismatch for source {s.id!r} "
                    f"({f.file}): declared {f.sha256[:12]}…, actual "
                    f"{actual[:12]}…; evidence changed or fabricated; "
                    "failing closed"
                )


def _norm_ws(s: str) -> str:
    import re

    return re.sub(r"\s+", " ", s or "").strip()


def _verify_archive_unavailability(matrix: EvidenceMatrix,
                                   sources: dict[str, EvidenceSource],
                                   evidence_dir: Path) -> None:
    """Substantive, fail-closed verification of the GCC correspondence: the
    actual `.eml` BYTES are parsed and every identity field the matrix
    declares must match the parsed message — a matrix that misdescribes the
    email fails even when the file hash matches.

    Authentication scope (honest statement): this verifies the immutable
    RECEIVED message and the receiving mail system's stored
    Authentication-Results (DKIM/DMARC/SPF pass verdicts recorded at
    delivery time, plus the presence of CME's DKIM-Signature header). It is
    NOT a fresh cryptographic DKIM verification against live DNS keys.
    """
    import email as email_mod
    import email.policy
    import email.utils
    import re

    au = matrix.archive_unavailability
    src = sources.get(au.email_source)
    if src is None:
        raise CalendarEvidenceError(
            "archive_unavailability email_source is not a defined source; "
            "failing closed"
        )
    if src.tier != TIER_OFFICIAL_CME_CORRESPONDENCE:
        raise CalendarEvidenceError(
            "archive-unavailability email must be tier "
            f"{TIER_OFFICIAL_CME_CORRESPONDENCE}, got {src.tier!r}; "
            "failing closed"
        )
    if au.sender_domain != "cmegroup.com":
        raise CalendarEvidenceError(
            "archive-unavailability correspondence is not from cmegroup.com "
            f"(sender_domain {au.sender_domain!r}); failing closed"
        )
    eml_files = [f for f in src.files if f.file.lower().endswith(".eml")]
    if len(src.files) != 1 or len(eml_files) != 1:
        raise CalendarEvidenceError(
            "the correspondence source must carry exactly one evidence file "
            "with an .eml suffix; failing closed"
        )
    eml_path = _contained(evidence_dir, eml_files[0].file,
                          "archive-unavailability .eml")
    if not eml_path.is_file():
        raise CalendarEvidenceError(
            f"correspondence .eml missing: {eml_path}; failing closed"
        )
    try:
        msg = email_mod.message_from_bytes(eml_path.read_bytes(),
                                           policy=email.policy.default)
    except Exception as e:
        raise CalendarEvidenceError(
            f"correspondence .eml unparseable; failing closed: {e}"
        ) from e

    _, mailbox = email.utils.parseaddr(str(msg.get("From", "")))
    if mailbox.lower() != au.sender_mailbox.lower():
        raise CalendarEvidenceError(
            f"parsed From mailbox {mailbox!r} does not match the declared "
            f"sender {au.sender_mailbox!r}; failing closed"
        )
    if mailbox.lower().rpartition("@")[2] != au.sender_domain.lower():
        raise CalendarEvidenceError(
            f"parsed From domain of {mailbox!r} is not "
            f"{au.sender_domain!r}; failing closed"
        )
    if _norm_ws(str(msg.get("Subject", ""))) != _norm_ws(au.subject):
        raise CalendarEvidenceError(
            "parsed email subject does not match the declared subject; "
            "failing closed"
        )
    try:
        parsed_date = email.utils.parsedate_to_datetime(str(msg.get("Date")))
    except Exception as e:
        raise CalendarEvidenceError(
            f"correspondence Date header unparseable; failing closed: {e}"
        ) from e
    if (parsed_date is None or parsed_date.utcoffset() is None
            or parsed_date != au.message_date_utc):
        raise CalendarEvidenceError(
            f"parsed email Date {parsed_date} does not match the declared "
            f"message_date_utc {au.message_date_utc}; failing closed"
        )
    if _norm_ws(str(msg.get("Message-ID", ""))) != _norm_ws(au.message_id):
        raise CalendarEvidenceError(
            "parsed Message-ID does not match the declared message_id; "
            "failing closed"
        )
    dkim_sigs = " ".join(str(v) for v in
                         (msg.get_all("DKIM-Signature") or []))
    if not re.search(r"\bd=cmegroup\.com\b", dkim_sigs):
        raise CalendarEvidenceError(
            "no DKIM-Signature header identifying d=cmegroup.com; "
            "failing closed"
        )
    auth = _norm_ws(" ".join(str(v) for v in
                             (msg.get_all("Authentication-Results") or [])))

    def _pass_clause(method: str) -> str | None:
        # The ';'-delimited clause carrying `<method>=pass`, if any.
        for part in auth.split(";"):
            if re.search(rf"\b{method}=pass\b", part):
                return part
        return None

    # Exact authentication-domain TOKENS, boundary-anchored: suffix/prefix
    # look-alikes (evilcmegroup.com, cmegroup.com.evil.example) never match.
    dkim_clause = _pass_clause("dkim")
    if not (dkim_clause and re.search(
            r"(?:^|[\s(])header\.i=@cmegroup\.com(?=[)\s]|$)", dkim_clause)):
        raise CalendarEvidenceError(
            "recipient-recorded Authentication-Results do not show DKIM pass "
            "bound exactly to header.i=@cmegroup.com; failing closed"
        )
    dmarc_clause = _pass_clause("dmarc")
    if not (dmarc_clause and re.search(
            r"(?:^|[\s(])header\.from=cmegroup\.com(?=[)\s]|$)",
            dmarc_clause)):
        raise CalendarEvidenceError(
            "recipient-recorded Authentication-Results do not show DMARC "
            "pass bound exactly to header.from=cmegroup.com; failing closed"
        )
    if _pass_clause("spf") is None:
        raise CalendarEvidenceError(
            "recipient-recorded Authentication-Results do not show SPF pass; "
            "failing closed"
        )
    body = None
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body = part.get_content()
            break
    if body is None:
        raise CalendarEvidenceError(
            "correspondence has no plain-text body part; failing closed"
        )
    if _norm_ws(au.body_statement) not in _norm_ws(body):
        raise CalendarEvidenceError(
            "the declared archive-unavailability statement is not present "
            "in the parsed email body; failing closed"
        )
    all_parts_text = []
    for part in msg.walk():
        if part.get_content_type() in ("text/plain", "text/html"):
            try:
                all_parts_text.append(part.get_content())
            except Exception:
                pass
    if not any(au.referral_url in t for t in all_parts_text):
        raise CalendarEvidenceError(
            "the declared CME trading-hours referral URL is not present in "
            "the email; failing closed"
        )


def validate_matrix(matrix: EvidenceMatrix, evidence_dir: Path) -> None:
    """Structural + evidentiary validation, fail-closed.

    Verifies: exact frozen date/group coverage; source citation scoping
    (never outside applicable_dates); per-state evidentiary requirements
    (tier gating, observed-data requirement, agreement coherence); and every
    evidence file hash against the immutable evidence directory.
    """
    sources = {}
    for s in matrix.sources:
        if s.id in sources:
            raise CalendarEvidenceError(
                f"duplicate source id {s.id!r}; failing closed"
            )
        sources[s.id] = s

    _verify_file_hashes(matrix, evidence_dir)
    _verify_archive_unavailability(matrix, sources, evidence_dir)

    seen = {}
    for d in matrix.dates:
        iso = d.date.isoformat()
        if iso in seen:
            raise CalendarEvidenceError(
                f"duplicate evidence entry for {iso}; failing closed"
            )
        seen[iso] = d
    expected = set(EXPECTED_EXCEPTIONAL_DATES)
    if set(seen) != expected:
        missing = sorted(expected - set(seen))
        extra = sorted(set(seen) - expected)
        raise CalendarEvidenceError(
            "evidence matrix does not cover exactly the frozen "
            f"exceptional-date set (missing: {missing}; unexpected: {extra}); "
            "failing closed"
        )
    email_id = matrix.archive_unavailability.email_source

    for iso, d in seen.items():
        if d.holiday_group != EXPECTED_EXCEPTIONAL_DATES[iso]:
            raise CalendarEvidenceError(
                f"{iso} is bound to group {d.holiday_group!r}, expected "
                f"{EXPECTED_EXCEPTIONAL_DATES[iso]!r}; failing closed"
            )
        for ref in d.evidence:
            src = sources.get(ref.source)
            if src is None:
                raise CalendarEvidenceError(
                    f"{iso} cites undefined source {ref.source!r}; "
                    "failing closed"
                )
            if ref.claim_id not in {c.id for c in src.claims}:
                raise CalendarEvidenceError(
                    f"{iso} cites claim {ref.claim_id!r} which source "
                    f"{ref.source!r} does not declare — date-level evidence "
                    "must bind to a real, stable source claim; failing closed"
                )
            if d.date not in src.applicable_dates:
                raise CalendarEvidenceError(
                    f"{iso} cites source {ref.source!r} outside its declared "
                    "applicable dates — evidence for one year can never "
                    "support another date; failing closed"
                )
            if (src.tier == TIER_TERTIARY_DATE_ONLY
                    and ref.kind != CLAIM_DATE_ONLY):
                raise CalendarEvidenceError(
                    f"{iso}: tertiary date-only source {ref.source!r} may "
                    "never carry a schedule claim; failing closed"
                )

        # Agreement/state coherence.
        if d.agreement == AGREEMENT_DISCREPANCY and d.state != STATE_CONFLICT:
            raise CalendarEvidenceError(
                f"{iso} records a source discrepancy but state is {d.state!r} "
                f"(must be {STATE_CONFLICT}); failing closed"
            )
        if d.state == STATE_CONFLICT and d.agreement != AGREEMENT_DISCREPANCY:
            raise CalendarEvidenceError(
                f"{iso} is {STATE_CONFLICT} without a recorded discrepancy; "
                "failing closed"
            )
        if (d.agreement == AGREEMENT_NOT_ASSESSABLE
                and d.state != STATE_PENDING):
            raise CalendarEvidenceError(
                f"{iso} agreement is not assessable but state is {d.state!r} "
                f"(must be {STATE_PENDING}); failing closed"
            )

        if d.state == STATE_DOCUMENT_VERIFIED:
            official = [r for r in d.evidence
                        if sources[r.source].tier == TIER_OFFICIAL_CME
                        and r.kind == CLAIM_DIRECT]
            if not official:
                raise CalendarEvidenceError(
                    f"{iso} is {STATE_DOCUMENT_VERIFIED} without a DIRECT "
                    "claim from an official CME artifact; failing closed"
                )
        elif d.state == STATE_TRIANGULATED:
            cited = {r.source for r in d.evidence}
            if email_id not in cited:
                raise CalendarEvidenceError(
                    f"{iso} claims triangulation without citing the verified "
                    "GCC archive-unavailability correspondence; failing closed"
                )
            if not d.observed.data_available:
                raise CalendarEvidenceError(
                    f"{iso} claims triangulation without observed canonical "
                    "Databento evidence; failing closed"
                )
            qualifying = [
                r for r in d.evidence
                if sources[r.source].tier in TRIANGULATION_CORROBORATION_TIERS
                and r.kind in _SCHEDULE_CLAIM_KINDS
            ]
            if not qualifying:
                raise CalendarEvidenceError(
                    f"{iso} claims triangulation without a qualifying "
                    "independent secondary source (strong/partial tier with "
                    "a direct or documented-inference claim) — the GCC "
                    "email, lower-tier and date-only sources never suffice; "
                    "failing closed"
                )


def group_states(matrix: EvidenceMatrix) -> dict[str, str]:
    """Conservative per-group roll-up: each group takes its WEAKEST member
    state. One document-verified year never promotes a multi-year group."""
    rollup: dict[str, str] = {}
    for d in matrix.dates:
        g = d.holiday_group
        if g not in rollup or (_STATE_STRENGTH[d.state]
                               < _STATE_STRENGTH[rollup[g]]):
            rollup[g] = d.state
    return rollup


def evidence_complete(matrix: EvidenceMatrix) -> bool:
    """True only when EVERY exceptional date is DOCUMENT_VERIFIED or
    TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE (no pending, no conflicts)."""
    return all(
        d.state in (STATE_DOCUMENT_VERIFIED, STATE_TRIANGULATED)
        for d in matrix.dates
    )


def unresolved_dates(matrix: EvidenceMatrix) -> dict[str, str]:
    return {
        d.date.isoformat(): d.state for d in matrix.dates
        if d.state not in (STATE_DOCUMENT_VERIFIED, STATE_TRIANGULATED)
    }


def conflict_dates(matrix: EvidenceMatrix) -> dict[str, str]:
    return {d.date.isoformat(): d.state for d in matrix.dates
            if d.state == STATE_CONFLICT}


def pending_dates(matrix: EvidenceMatrix) -> dict[str, str]:
    return {d.date.isoformat(): d.state for d in matrix.dates
            if d.state == STATE_PENDING}


def resolve_activation_disposition(matrix: EvidenceMatrix,
                                   quarantined: frozenset[str] | set[str]
                                   ) -> str:
    """Activation-resolution check (PA-0002) — SEPARATE from evidence.

    This never reads, writes, or upgrades an evidence state. It answers one
    question: given the true evidence states plus a reviewed quarantine
    policy, may activation proceed, and under which named disposition?

    Semantics (fail-closed):
    - DOCUMENT_VERIFIED and TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE are
      evidence-complete;
    - CONFLICT_REQUIRES_REVIEW ALWAYS blocks and can never be dispositioned
      by quarantine;
    - a PENDING_EVIDENCE date may be dispositioned only if it appears
      exactly in the bound quarantine policy, and EVERY pending date must be
      so covered; an extra, missing, or substituted quarantine date fails
      closed (in particular a verified/triangulated date can never be
      silently quarantined);
    - with no pending dates the disposition is EVIDENCE_COMPLETE; otherwise
      PENDING_DATES_QUARANTINED, under which the calendar remains explicitly
      provisional and is never relabelled DOCUMENT_VERIFIED.
    """
    conflicts = conflict_dates(matrix)
    if conflicts:
        raise CalendarEvidenceError(
            f"calendar evidence has unresolved conflicts {sorted(conflicts)}: "
            "a conflict can NEVER be resolved by quarantine; failing closed"
        )
    pending = set(pending_dates(matrix))
    unresolved = set(unresolved_dates(matrix))
    if unresolved != pending:  # defensive: any non-pending unresolved state
        raise CalendarEvidenceError(
            f"unresolved dates {sorted(unresolved - pending)} are neither "
            "pending nor conflicting; failing closed"
        )
    q = set(quarantined)
    if not pending:
        if q:
            raise CalendarEvidenceError(
                "quarantine policy declares dates "
                f"{sorted(q)} but no calendar date is pending: verified or "
                "triangulated dates are never silently quarantined; "
                "failing closed"
            )
        return DISPOSITION_EVIDENCE_COMPLETE
    if q != pending:
        raise CalendarEvidenceError(
            "quarantine policy does not exactly cover the pending dates "
            f"(missing: {sorted(pending - q)}; unexpected: {sorted(q - pending)}"
            "); failing closed"
        )
    return DISPOSITION_PENDING_DATES_QUARANTINED


def verify_observed_against_coverage(matrix: EvidenceMatrix,
                                     coverage_path: Path) -> None:
    """Cross-check every transcribed observed block against the live
    coverage artifact. The artifact's IDENTITY is enforced first: the matrix
    must declare the artifact's SHA-256 and the actual bytes must match it —
    only then are per-date observed fields compared. Fabricated observed
    claims and swapped/edited artifacts both fail here."""
    import json

    if not coverage_path.is_file():
        raise CalendarEvidenceError(
            f"coverage artifact missing: {coverage_path}; observed evidence "
            "unverifiable; failing closed"
        )
    declared = (matrix.meta or {}).get("observed_reference", {}).get(
        "artifact_sha256"
    )
    if not _is_sha256_hex(declared):
        raise CalendarEvidenceError(
            "matrix meta.observed_reference.artifact_sha256 missing or not "
            "a valid SHA-256; observed evidence unbindable; failing closed"
        )
    actual = hashlib.sha256(coverage_path.read_bytes()).hexdigest()
    if actual != declared.lower():
        raise CalendarEvidenceError(
            "coverage artifact identity mismatch (declared "
            f"{declared[:12]}…, actual {actual[:12]}…): the observed "
            "evidence was transcribed from a different artifact version; "
            "failing closed"
        )
    doc = json.loads(coverage_path.read_text(encoding="utf-8"))
    by_session = {s.get("session_id"): s for s in doc.get("sessions", [])}
    for d in matrix.dates:
        iso = d.date.isoformat()
        s = by_session.get(iso)
        if d.observed.session_present:
            if s is None:
                raise CalendarEvidenceError(
                    f"{iso}: matrix claims an observed session but the "
                    "coverage artifact has none; failing closed"
                )
            if s.get("rth_span_seconds") != d.observed.rth_span_seconds:
                raise CalendarEvidenceError(
                    f"{iso}: observed RTH span mismatch (matrix "
                    f"{d.observed.rth_span_seconds}, artifact "
                    f"{s.get('rth_span_seconds')}); failing closed"
                )
        elif s is not None:
            raise CalendarEvidenceError(
                f"{iso}: matrix claims no observed session but the coverage "
                "artifact contains one; failing closed"
            )


def load_validated_matrix(repo_root: Path, data_root: Path) -> EvidenceMatrix:
    """Load + fully verify the matrix against the immutable evidence files
    and the live coverage artifact. Fail-closed on any inconsistency."""
    from nqresearch.rawguard import is_contained

    matrix = load_matrix(repo_root)
    evidence_root = (matrix.meta or {}).get("evidence_root")
    if not isinstance(evidence_root, str) or not evidence_root:
        raise CalendarEvidenceError(
            "matrix meta.evidence_root missing; failing closed"
        )
    evidence_dir = _contained(data_root, evidence_root, "meta.evidence_root")
    if not evidence_dir.is_dir():
        raise CalendarEvidenceError(
            f"meta.evidence_root does not resolve to an existing directory "
            f"inside the data root ({evidence_dir}); failing closed"
        )
    validate_matrix(matrix, evidence_dir)
    observed_ref = (matrix.meta or {}).get("observed_reference", {})
    artifact_rel = observed_ref.get("artifact")
    if not isinstance(artifact_rel, str) or not artifact_rel:
        raise CalendarEvidenceError(
            "matrix meta.observed_reference.artifact missing; failing closed"
        )
    coverage_path = _contained(data_root, artifact_rel,
                               "meta.observed_reference.artifact")
    if not is_contained(coverage_path, Path(data_root) / "qa"):
        raise CalendarEvidenceError(
            "meta.observed_reference.artifact must live under "
            "<data_root>/qa/; failing closed"
        )
    verify_observed_against_coverage(matrix, coverage_path)
    return matrix


def current_calendar_verification_state(repo_root: Path,
                                        data_root: Path) -> str:
    """Artifact-level state for regenerated closeout artifacts. NEVER claims
    completeness on any validation failure (fail-safe direction: pending).

    Under PA-0002 a fully-quarantined pending set yields the explicitly
    PROVISIONAL state PROVISIONAL_PENDING_DATES_QUARANTINED — never
    DOCUMENT_VERIFIED and never the complete state.
    """
    try:
        matrix = load_validated_matrix(repo_root, data_root)
    except Exception:
        return CALENDAR_EVIDENCE_PENDING_STATE
    if evidence_complete(matrix):
        return CALENDAR_EVIDENCE_COMPLETE_STATE
    # The quarantine disposition may ONLY be emitted through the fully
    # validated policy path: a stale evidence-matrix binding, a malformed or
    # non-PA-0002 policy, or an inconsistent date set all fall back to the
    # ordinary provisional/pending state.
    # Imported OUTSIDE the try: a wrong/renamed symbol must raise loudly
    # rather than be swallowed into the fail-safe pending path.
    from nqresearch.eligibility import load_policy_for_reporting

    try:
        _policy, disposition = load_policy_for_reporting(repo_root, data_root)
    except Exception:
        return CALENDAR_EVIDENCE_PENDING_STATE
    if disposition == DISPOSITION_PENDING_DATES_QUARANTINED:
        return CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED
    return CALENDAR_EVIDENCE_PENDING_STATE
