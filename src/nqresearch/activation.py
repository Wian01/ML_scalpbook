"""Partition-activation tooling (PA-0002) — FAIL-CLOSED, review-only.

SENSITIVE CODE — status PENDING_INDEPENDENT_AUDIT.

Two deliberately separate commands, neither of which can activate anything
by itself:

1. ``finalize_activation_candidate()`` re-verifies every mechanical
   precondition and produces an immutable partition-activation CANDIDATE in
   state ``READY_FOR_ACTIVATION_APPROVAL`` with ``structural_ready=true`` and
   ``activation_ready=false``. It refuses unless the research-eligibility
   policy is exactly ``APPROVED_FOR_ACTIVATION``. Against the live
   repository today it therefore REFUSES, because the real policy is still
   ``IMPLEMENTED_PENDING_ACTIVATION_APPROVAL``.

2. ``generate_active_partitions()`` writes
   ``config/data/partitions_active.yaml`` — the only record that actually
   confers activation — and refuses unless a valid candidate AND a valid,
   already-committed human-approval audit entry both exist and agree on
   every identity.

SEPARATION OF POWERS: a generated artifact can never self-certify that a
human approved its exact bytes, because its own SHA-256 does not exist while
it is being written. Mechanical readiness (the candidate), human approval
(the append-only audit entry) and activation (the active configuration) are
three independent records.

The PUBLIC entry points take NO repository, data-root or artifact-path
parameter: a caller can never point them at a fabricated tree or substitute
a hand-written candidate. Tests exercise the private ``_..._from`` helpers
against synthetic temporary trees.

There is deliberately NO override, force, bypass, alternate policy path, or
caller-supplied relaxed state anywhere in this module. Nothing here opens,
reads, or enumerates HOLDOUT records.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from pydantic import ValidationError


class ActivationError(RuntimeError):
    """Fail-closed refusal of a finalization or activation step."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(cond, message: str) -> None:
    if not cond:
        raise ActivationError(f"{message}; failing closed")


@contextmanager
def _as_activation_error(context: str):
    """Translate the EXPECTED refusal exceptions raised by the evidence,
    envelope and policy validators into ``ActivationError``.

    The activation module's public contract (and the CLI that prints its
    refusals) is ``ActivationError``. The validators it reuses belong to other
    modules and raise their own fail-closed types, which would otherwise
    escape as uncaught tracebacks even though the refusal is entirely
    expected.

    ONLY the three named refusal types are translated — there is deliberately
    no ``except Exception`` here, so a programming error (TypeError,
    AttributeError, KeyError, ...) still propagates loudly instead of being
    disguised as an ordinary activation refusal. The original message is
    preserved and the original exception is chained via ``raise ... from``.
    """
    from nqresearch.calendar_evidence import CalendarEvidenceError
    from nqresearch.eligibility import EligibilityPolicyError
    from nqresearch.holdout import PartitionsNotActiveError

    try:
        yield
    except ActivationError:
        raise                       # already the right type; keep its message
    except (PartitionsNotActiveError, EligibilityPolicyError,
            CalendarEvidenceError) as e:
        raise ActivationError(f"{context}: {e}") from e


def _closeout(data_root: Path) -> Path:
    return data_root / "qa" / "m0_closeout"


def _roots(repo_root: Path | None, data_root: Path | None):
    from nqresearch import paths
    from nqresearch.config import _repo_root

    return (repo_root or _repo_root()), (data_root or paths.data_root())


def _verify_activation_preconditions_from(repo_root: Path,
                                          data_root: Path) -> dict:
    """PRIVATE: re-verify EVERY mechanical precondition for activation
    against the given roots and return the proven facts plus the exact
    identities. Fail-closed.

    Verifies: policy lifecycle exactly APPROVED_FOR_ACTIVATION; the policy's
    evidence-matrix binding; all ten pending dates exactly quarantined with
    their evidence states still truthful; the coverage substance digest AND
    the exact coverage file identity; the exact understood coverage WARN;
    the causal front series; MBO blocks and non-spanning placement; all
    partition structural checks; all quarantine structural invariants; the
    exact DEV/SELECTION/HOLDOUT ranges and counts; and current clean
    committed envelopes on every activation-bound artifact.
    """
    from nqresearch.calendar_evidence import (
        COVERAGE_SUBSTANCE_ALGORITHM,
        DISPOSITION_PENDING_DATES_QUARANTINED,
        STATE_PENDING,
        coverage_substance_sha256,
        load_validated_matrix,
        matrix_file_sha256,
        pending_dates,
    )
    from nqresearch.eligibility import (
        POLICY_STATE_APPROVED,
        load_policy_for_activation,
        policy_sha256,
        verify_structural_quarantine_invariants,
    )
    from nqresearch.holdout import (
        ACTIVE_PARTITIONS_FILENAME,
        CANDIDATE_STATE_NOT_ACTIVE,
        _verify_artifact_envelope,
        _verify_neutral_proposal,
    )
    from nqresearch.qa.closeout import (
        PROPOSED_DEV_END,
        PROPOSED_DEV_START,
        PROPOSED_HOLDOUT_END,
        PROPOSED_HOLDOUT_START,
        PROPOSED_SELECTION_END,
        PROPOSED_SELECTION_START,
        _coverage_substance_problems,
    )

    root, droot = repo_root, data_root
    close = _closeout(droot)

    # 1. Policy must be exactly APPROVED_FOR_ACTIVATION (no relaxation path).
    with _as_activation_error(
            "research-eligibility policy is not usable for activation"):
        policy, disposition = load_policy_for_activation(root, droot)
    _require(policy.meta.status == POLICY_STATE_APPROVED,
             f"policy lifecycle is {policy.meta.status!r}, not "
             f"{POLICY_STATE_APPROVED}")
    _require(disposition == DISPOSITION_PENDING_DATES_QUARANTINED,
             f"unexpected evidence disposition {disposition!r}")

    # 2. Evidence: matrix validates; the ten pending dates are exactly the
    #    quarantined set; every state is still truthfully PENDING_EVIDENCE.
    with _as_activation_error("calendar evidence matrix is not usable for "
                              "activation"):
        matrix = load_validated_matrix(root, droot)
    pending = pending_dates(matrix)
    _require(set(pending) == set(policy.dates),
             "the quarantine policy does not cover exactly the pending dates")
    _require(len(pending) == 10,
             f"expected exactly 10 pending dates, found {len(pending)}")
    _require(all(v == STATE_PENDING for v in pending.values()),
             "a pending date has been relabelled away from PENDING_EVIDENCE")

    # 3. Structural quarantine invariants + frozen corpus counts.
    with _as_activation_error("structural quarantine invariants do not hold"):
        facts = verify_structural_quarantine_invariants(root, droot)

    # 4. Every activation-bound artifact: identity, structure and CURRENT
    #    clean committed envelope.
    names = {
        "coverage": ("mbp1_full_history_coverage.json",
                     "mbp1_full_history_coverage"),
        "blocks": ("mbo_blocks_frozen.json", "mbo_blocks_frozen"),
        "front": ("mbp1_front_contract_series.json",
                  "mbp1_front_contract_series"),
        "proposal": ("partition_proposal.json", "partition_proposal"),
    }
    docs, ident = {}, {}
    for key, (fname, artifact) in names.items():
        p = close / fname
        _require(p.is_file(), f"activation-bound artifact missing: {p}")
        raw = p.read_bytes()
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ActivationError(
                f"{fname} is malformed: {e}; failing closed") from e
        _require(doc.get("artifact") == artifact,
                 f"{fname} declares artifact {doc.get('artifact')!r}")
        # Clean committed tree, current config and package code.
        with _as_activation_error(
                f"activation-bound artifact {fname} is not usable"):
            _verify_artifact_envelope(fname, doc)
        docs[key], ident[key] = doc, hashlib.sha256(raw).hexdigest()

    # 5. Coverage: substance digest bound by the matrix AND the exact
    #    understood WARN state (two independent identities/purposes).
    ref = (matrix.meta or {}).get("observed_reference", {})
    _require(ref.get("substance_digest_algorithm")
             == COVERAGE_SUBSTANCE_ALGORITHM,
             "matrix declares an unexpected coverage substance algorithm")
    recomputed = coverage_substance_sha256(docs["coverage"])
    _require(recomputed == str(ref.get("substance_sha256", "")).lower(),
             "live coverage substance digest does not match the matrix")
    problems = _coverage_substance_problems(docs["coverage"],
                                            "mbp1_full_history_coverage.json")
    _require(not problems, f"coverage is not in the understood state: {problems}")

    # 6. Front series: causal, eight switches, no partial edge session.
    front = docs["front"]
    _require(front.get("status") == "PASS", "front series is not PASS")
    _require(front.get("n_switches") == 8,
             f"front series has {front.get('n_switches')} switches, expected 8")
    _require("CAUSAL" in str(front.get("rule", "")).upper(),
             "front series does not declare the strictly causal rule")
    _require("2026-08-17" not in [e.get("session_id")
                                  for e in front.get("per_session", [])],
             "front series includes the 2026-08-17 partial edge session")

    # 7. MBO blocks.
    blocks = docs["blocks"]
    _require(blocks.get("status") == "PASS", "MBO block artifact is not PASS")
    _require(blocks.get("n_sessions_final") == facts["n_mbo_sessions"] == 77,
             "MBO session count is not 77")
    _require(blocks.get("n_blocks") == facts["n_mbo_blocks"] == 30,
             "MBO block count is not 30")

    # 8. Partition proposal: the SOURCE must still be the neutral
    #    PROPOSED_NOT_ACTIVE artifact with all structural checks PASS. The
    #    exact same neutrality rule the fence applies at activation time is
    #    reused here, so the two layers cannot drift apart.
    prop = docs["proposal"]
    with _as_activation_error("partition proposal is unusable"):
        _verify_neutral_proposal(prop)
    _require(prop.get("state") == CANDIDATE_STATE_NOT_ACTIVE,
             f"source proposal state is {prop.get('state')!r}, expected "
             f"{CANDIDATE_STATE_NOT_ACTIVE}")
    _require(prop["mbo_blocks_per_partition"].get("SPANNING") == [],
             "an MBO block spans a partition boundary")

    # 9. Exact ranges and counts.
    expected_ranges = {
        "DEV": (PROPOSED_DEV_START, PROPOSED_DEV_END, 318),
        "SELECTION": (PROPOSED_SELECTION_START, PROPOSED_SELECTION_END, 100),
        "HOLDOUT": (PROPOSED_HOLDOUT_START, PROPOSED_HOLDOUT_END, 98),
    }
    for name, (start, end, days) in expected_ranges.items():
        p = prop["proposal"][name]
        _require(p["start"] == start.isoformat() and p["end"] == end.isoformat(),
                 f"{name} range {p['start']}..{p['end']} != expected "
                 f"{start}..{end}")
        _require(p.get("trading_days") == days,
                 f"{name} trading days {p.get('trading_days')} != {days}")
    _require(prop["mbo_sessions_per_partition"]
             == {"DEV": 23, "SELECTION": 23, "HOLDOUT": 31},
             "MBO session distribution changed")

    # 10. HOLDOUT must remain sealed: nothing here reads holdout records, and
    #     no active configuration may already exist.
    _require(not (root / "config" / "data"
                  / ACTIVE_PARTITIONS_FILENAME).is_file(),
             "an active partition configuration already exists")

    from nqresearch.calendar import calendar_identity
    with _as_activation_error("activation identities are not computable"):
        identities = {
            "partition_proposal_sha256": ident["proposal"],
            "effective_calendar_sha256":
                calendar_identity(root)["effective_calendar_sha256"],
            "evidence_matrix_sha256": matrix_file_sha256(root),
            "cme_correspondence_sha256":
                {s.id: s for s in matrix.sources}[
                    matrix.archive_unavailability.email_source].files[0].sha256,
            "research_eligibility_sha256": policy_sha256(root),
            "coverage_artifact_sha256": ident["coverage"],
            "mbo_blocks_sha256": ident["blocks"],
            "front_contract_series_sha256": ident["front"],
        }
    return {
        "disposition": disposition,
        "calendar_verification_state": prop["calendar_verification_state"],
        "policy_state": policy.meta.status,
        "quarantined_dates": sorted(policy.dates),
        "structural_quarantine": facts,
        "identities": identities,
        "ranges": {name: {"start": prop["proposal"][name]["start"],
                          "end": prop["proposal"][name]["end"],
                          "trading_days": prop["proposal"][name]["trading_days"]}
                   for name in expected_ranges},
        "source_proposal": prop,
    }


def verify_activation_preconditions() -> dict:
    """PUBLIC: re-verify every mechanical precondition for activation against
    the REAL repository and data root. No path injection: a caller can never
    substitute a fabricated tree.

    Every EXPECTED refusal surfaces as ``ActivationError``; programming errors
    are never swallowed."""
    with _as_activation_error("activation preconditions do not hold"):
        return _verify_activation_preconditions_from(*_roots(None, None))


def _candidate_payload(proven: dict) -> dict:
    """The COMPLETE candidate substance implied by a set of freshly proven
    preconditions. Both the generator and the activation-time verifier build
    this from live evidence, so an on-disk candidate is compared against
    recomputed truth rather than trusted for its own contents."""
    from nqresearch.holdout import CANDIDATE_ARTIFACT_TYPE, CANDIDATE_STATE_READY

    src = proven["source_proposal"]
    return {
        "artifact": CANDIDATE_ARTIFACT_TYPE,
        "state": CANDIDATE_STATE_READY,
        "structural_ready": True,
        # NEVER true in a generated artifact: activation is conferred only by
        # the human-approval audit entry plus config/data/partitions_active.yaml.
        "activation_ready": False,
        "calendar_verification_state": proven["calendar_verification_state"],
        "evidence_disposition": proven["disposition"],
        "research_eligibility_policy_state": proven["policy_state"],
        "quarantined_dates": proven["quarantined_dates"],
        "n_quarantined_calendar_dates": len(proven["quarantined_dates"]),
        "structural_quarantine": proven["structural_quarantine"],
        "bound_identities": proven["identities"],
        "proposal": src["proposal"],
        "mbo_sessions_per_partition": src["mbo_sessions_per_partition"],
        "mbo_blocks_per_partition": src["mbo_blocks_per_partition"],
        "checks": src["checks"],
        "activation_requires": [
            "a separately committed append-only audit entry recording explicit "
            "human approval of THIS candidate's exact SHA-256 and all eight "
            "identities, the exact partition ranges, the approving identity "
            "and UTC timestamp, and the quarantine disposition/calendar state",
            "config/data/partitions_active.yaml generated from that approval",
        ],
        "status": "PASS",
    }


def _finalize_activation_candidate_from(repo_root: Path,
                                        data_root: Path) -> dict:
    """PRIVATE: build the immutable structurally-ready activation CANDIDATE
    payload against the given roots."""
    return _candidate_payload(
        _verify_activation_preconditions_from(repo_root, data_root))


def finalize_activation_candidate() -> dict:
    """PUBLIC: build the immutable structurally-ready activation CANDIDATE
    payload for the REAL repository and data root.

    The candidate asserts MECHANICAL readiness only:
    ``state=READY_FOR_ACTIVATION_APPROVAL``, ``structural_ready=true``,
    ``activation_ready=false``. It can never activate research access by
    itself. Fail-closed; no override or path injection of any kind exists.
    Every EXPECTED refusal surfaces as ``ActivationError``.
    """
    with _as_activation_error("activation candidate cannot be finalized"):
        return _finalize_activation_candidate_from(*_roots(None, None))


def _read_candidate(data_root: Path) -> tuple[dict, str]:
    """Read the CANONICAL activation candidate — the path is fixed, never
    caller-supplied — and return its parsed document plus the exact SHA-256
    of its bytes. That SHA is the identity human approval must name."""
    from nqresearch.holdout import CANDIDATE_ARTIFACT_FILENAME

    cpath = _closeout(data_root) / CANDIDATE_ARTIFACT_FILENAME
    _require(cpath.is_file(), f"activation candidate missing: {cpath}")
    raw = cpath.read_bytes()
    try:
        return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ActivationError(
            f"activation candidate {cpath.name} is malformed: {e}; "
            "failing closed"
        ) from e


APPROVAL_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _validated_utc_instant(value) -> datetime:
    """Prove an approval timestamp really is a UTC instant BEFORE anything
    formats it with a literal ``Z``.

    Stamping ``Z`` onto a ``+08:00`` wall time would silently relabel local
    time as UTC and make the permanent record lie about WHEN approval
    happened. A non-zero offset is therefore REFUSED — never converted, never
    relabelled. A ``date`` is not a ``datetime``; neither are ``bool``,
    ``str``, ``None`` or arbitrary objects.

    Sub-second precision is refused for the same reason.
    ``APPROVAL_TIMESTAMP_FORMAT`` is deliberately fixed to whole seconds so
    the approval record is byte-comparable, which means a value carrying
    microseconds could only be recorded by DISCARDING them: 09:30:00.987654Z
    would be written as 09:30:00Z, which is not the instant that was
    approved. Truncating or rounding silently is exactly the failure mode
    this module exists to prevent, so such a value is rejected and the
    approver re-states a whole-second instant.
    """
    if not isinstance(value, datetime):
        raise ActivationError(
            "approved_at_utc must be a datetime, not "
            f"{type(value).__name__}; failing closed"
        )
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise ActivationError(
            "approved_at_utc must be timezone-aware (a naive datetime cannot "
            "be proven to be UTC); failing closed"
        )
    if offset != timedelta(0):
        raise ActivationError(
            f"approved_at_utc has UTC offset {offset}, not exactly zero: "
            "refusing to relabel a non-UTC instant with 'Z'; convert it to "
            "UTC explicitly and re-approve; failing closed"
        )
    if value.microsecond != 0:
        raise ActivationError(
            f"approved_at_utc carries {value.microsecond} microseconds, but "
            f"the approval format {APPROVAL_TIMESTAMP_FORMAT!r} records whole "
            "seconds only: refusing to truncate or round the approved "
            "instant; re-approve with a whole-second timestamp; failing closed"
        )
    # The fixed format must round-trip this instant EXACTLY.
    stamped = value.strftime(APPROVAL_TIMESTAMP_FORMAT)
    if (datetime.strptime(stamped, APPROVAL_TIMESTAMP_FORMAT)
            .replace(tzinfo=timezone.utc) != value):
        raise ActivationError(
            f"approved_at_utc {value.isoformat()} does not round-trip through "
            f"{APPROVAL_TIMESTAMP_FORMAT!r} (would be recorded as {stamped}); "
            "refusing to record an instant other than the approved one; "
            "failing closed"
        )
    return value


def _atomic_write_text(path: Path, text: str) -> None:
    """Crash-safe, CREATE-ONCE publication of the active configuration.

    The completed bytes are written into a sibling temp file and flushed to
    stable storage FIRST, then published with ``os.link()`` — an atomic
    create-if-absent operation on NTFS and on POSIX: the filesystem creates
    the destination entry only if no entry of that name exists, and raises
    ``FileExistsError`` otherwise. ``os.replace()`` is deliberately NOT used
    — it overwrites, and any ``exists()``-then-``replace()`` pair leaves a
    window in which a concurrent creator silently loses its file.

    Guarantees: the destination only ever appears carrying complete flushed
    bytes; an existing activation is never overwritten; a concurrent creator
    wins safely; a failure at any point leaves no partial activation; and a
    temporary file surviving a crash causes a FUTURE fail-closed refusal
    rather than being silently reused.
    """
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists():
        raise ActivationError(
            f"a stale temporary activation file {tmp.name} exists: it may be "
            "the residue of an interrupted activation and is never silently "
            "reused; resolve it under review; failing closed"
        )
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    published = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            # THE atomic create-if-absent step. Nothing checks the
            # destination before it, so there is no window to lose.
            os.link(tmp, path)
        except FileExistsError as e:
            raise ActivationError(
                f"{path.name} already exists at the moment of publication; "
                "refusing to overwrite an existing activation; failing closed"
            ) from e
        except OSError as e:
            raise ActivationError(
                f"could not publish {path.name} atomically ({e}); refusing a "
                "non-atomic fallback that could overwrite an existing "
                "activation; failing closed"
            ) from e
        published = True
    finally:
        # The temp entry is always removed: on success the destination is an
        # independent directory entry for the same complete content, and on
        # failure nothing partial is left behind.
        try:
            tmp.unlink()
        except OSError:
            if not published:
                raise


def _generate_active_partitions_from(
    approved_by: str,
    approval_reference: str,
    approved_at_utc: datetime,
    repo_root: Path,
    data_root: Path,
) -> Path:
    """PRIVATE: write ``config/data/partitions_active.yaml`` against the given
    roots — the ONLY record that confers activation.

    Refuses unless: the canonical candidate exists, validates against the
    STRICT candidate schema, and its COMPLETE substance equals the substance
    freshly recomputed from live evidence; the named human-approval audit
    entry already exists and binds the exact candidate SHA-256, all eight
    dependency identities, the exact ranges and the exact approval
    identity/timestamp; the policy is approved; and HOLDOUT remains sealed.

    ``approved_at_utc`` must be a timezone-aware ``datetime`` whose UTC offset
    is exactly zero AND whose microsecond component is zero; a naive,
    non-UTC, sub-second, or non-``datetime`` value is REFUSED rather than
    relabelled with a literal ``Z`` or truncated. The audit entry and the
    generated YAML therefore carry exactly the validated UTC instant.

    Writes only the tracked configuration file, once and atomically, and never
    opens or enumerates HOLDOUT records.
    """
    from nqresearch.holdout import (
        ACTIVE_PARTITIONS_FILENAME,
        CANDIDATE_ARTIFACT_FILENAME,
        ActivePartitions,
        _verify_activation_candidate,
        _verify_approval_bound_to_audit_record,
        _verify_artifact_envelope,
    )

    # The approval instant is proven to be UTC BEFORE anything formats it
    # with a literal 'Z' — a +08:00 wall time must never be relabelled UTC.
    stamp = _validated_utc_instant(approved_at_utc)

    root, droot = repo_root, data_root
    out = root / "config" / "data" / ACTIVE_PARTITIONS_FILENAME
    _require(not out.is_file(),
             f"{ACTIVE_PARTITIONS_FILENAME} already exists; refusing to "
             "overwrite an existing activation")

    # Every mechanical precondition must still hold RIGHT NOW.
    proven = _verify_activation_preconditions_from(root, droot)

    candidate, candidate_sha = _read_candidate(droot)
    with _as_activation_error("activation candidate is not usable"):
        _verify_artifact_envelope(CANDIDATE_ARTIFACT_FILENAME, candidate)
        _verify_activation_candidate(candidate)

    # The candidate's COMPLETE substance must equal the substance implied by
    # the preconditions just recomputed — not merely its bound identities.
    from nqresearch.qa.report import RESERVED_ENVELOPE_KEYS

    on_disk = {k: v for k, v in candidate.items()
               if k not in RESERVED_ENVELOPE_KEYS}
    expected = _candidate_payload(proven)
    differing = sorted(k for k in set(on_disk) | set(expected)
                       if on_disk.get(k) != expected.get(k))
    _require(not differing,
             f"activation candidate substance differs from the freshly "
             f"recomputed preconditions in {differing}")

    ranges = {name: proven["ranges"][name] for name in
              ("DEV", "SELECTION", "HOLDOUT")}
    payload = {
        "activated": True,
        "approval": {
            "approved_by": approved_by,
            "approval_reference": approval_reference,
            "approved_at_utc": stamp.strftime(APPROVAL_TIMESTAMP_FORMAT),
        },
        "activation_candidate_sha256": candidate_sha,
        **proven["identities"],
        "dev": {"start": ranges["DEV"]["start"], "end": ranges["DEV"]["end"]},
        "selection": {"start": ranges["SELECTION"]["start"],
                      "end": ranges["SELECTION"]["end"]},
        "holdout": {"start": ranges["HOLDOUT"]["start"],
                    "end": ranges["HOLDOUT"]["end"]},
    }
    # Validate the schema and the human-approval binding BEFORE writing.
    try:
        parts = ActivePartitions(**payload)
    except ValidationError as e:
        raise ActivationError(
            f"active partition configuration would be invalid: {e}"
        ) from e
    with _as_activation_error("human-approval audit entry does not authorise "
                              "this exact activation"):
        _verify_approval_bound_to_audit_record(parts, root)

    _atomic_write_text(out, yaml.safe_dump(payload, sort_keys=False))
    return out


def generate_active_partitions(
    approved_by: str,
    approval_reference: str,
    approved_at_utc: datetime,
) -> Path:
    """PUBLIC: write ``config/data/partitions_active.yaml`` for the REAL
    repository — the ONLY record that confers activation. No repository,
    data-root or candidate-path injection exists.

    Every EXPECTED refusal surfaces as ``ActivationError``."""
    with _as_activation_error("activation cannot proceed"):
        return _generate_active_partitions_from(
            approved_by, approval_reference, approved_at_utc,
            *_roots(None, None))


def _unused_date_guard(_d: date) -> None:  # pragma: no cover - typing anchor
    return None
