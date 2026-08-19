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


def _calendar_evidence_state() -> str:
    """Artifact-level calendar verification state per PA-0001: complete only
    when every exceptional date is resolved (validated live against the
    evidence matrix, evidence files and coverage artifact); any failure
    stamps the pending state — never a completeness claim. Under PA-0002 a
    fully-quarantined pending set stamps the explicitly PROVISIONAL
    quarantined state."""
    from nqresearch import paths
    from nqresearch.calendar_evidence import current_calendar_verification_state
    from nqresearch.config import _repo_root

    return current_calendar_verification_state(_repo_root(), paths.data_root())


_SHA256_HEX = set("0123456789abcdef")

# The ONLY coverage WARN this corpus understands: the 2025-04-18 Good Friday
# pre-RTH short session that has no vendor records. Any other, renamed or
# additional non-PASS coverage check must fail closed pending review.
UNDERSTOOD_COVERAGE_WARN_CHECKS = frozenset({
    "pre_rth_short_sessions_without_data",
})
EXPECTED_COVERAGE_EXPECTED_SESSIONS = 516
# The single machine-readable fact the understood WARN is bound to: the
# 2025-04-18 Good Friday pre-RTH short session with no vendor records.
EXPECTED_PRE_RTH_MISSING_SESSIONS = ["2025-04-18"]
# Coverage may be PASS (everything clean) or WARN (exactly the understood
# Good Friday condition); coherence between the two is enforced by
# _coverage_substance_problems(), which BOTH the generation-time input
# validator and the activation verifier use.
PERMITTED_COVERAGE_STATUSES = (st.PASS, st.WARN)


def _is_sha256_hex(v) -> bool:
    """Exactly 64 LOWERCASE hex characters — uppercase, short, long and
    non-hex values are not valid identities."""
    return (isinstance(v, str) and len(v) == 64
            and all(c in _SHA256_HEX for c in v))


def _sha256_file(path: Path) -> str | None:
    import hashlib

    return (hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file() else None)


def _validate_input_artifact(path: Path, artifact_name: str,
                             required_keys: tuple,
                             permitted_statuses: tuple) -> list[str]:
    """Substantive validation of an artifact CONSUMED as input, so that
    'identities valid' can never mean merely 'a file existed and hashed'.

    Checks artifact type, required keys, permitted status semantics, and the
    current provenance envelope (clean committed tree, real ancestral commit,
    current effective config and package hashes). Returns a list of problems;
    empty means valid. The historical closeout artifacts legitimately fail
    the current-envelope checks until the reviewed regeneration — that is the
    intended outcome, not something to weaken.
    """
    from nqresearch import paths
    from nqresearch.config import effective_config_hash
    from nqresearch.qa.cache import package_source_hash

    problems = []
    if not path.is_file():
        return [f"{path.name}: missing"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"{path.name}: unparseable ({e})"]
    if doc.get("artifact") != artifact_name:
        problems.append(
            f"{path.name}: artifact type {doc.get('artifact')!r} != "
            f"{artifact_name!r}")
    for k in required_keys:
        if k not in doc:
            problems.append(f"{path.name}: missing key {k!r}")
    if doc.get("status") not in permitted_statuses:
        problems.append(
            f"{path.name}: status {doc.get('status')!r} not in "
            f"{permitted_statuses}")
    clean = doc.get("generation_git_clean")
    if clean is not True or not isinstance(clean, bool):
        problems.append(
            f"{path.name}: generation_git_clean={clean!r} (must be boolean "
            "true)")
    sha = doc.get("git_sha")
    if not _is_sha256_hex(str(sha)) and not (
            isinstance(sha, str) and len(sha) == 40
            and all(c in _SHA256_HEX for c in sha)):
        problems.append(f"{path.name}: invalid git_sha {sha!r}")
    else:
        from nqresearch.sources import (
            ProvenanceError,
            _verify_committed_ancestor,
        )
        try:
            _verify_committed_ancestor(sha, paths.ROOT)
        except ProvenanceError as e:
            problems.append(f"{path.name}: {e}")
    if doc.get("config_hash") != effective_config_hash():
        problems.append(f"{path.name}: stale config_hash")
    if doc.get("audit_code_hash") != package_source_hash():
        problems.append(f"{path.name}: stale audit_code_hash")
    if artifact_name == "mbp1_full_history_coverage":
        problems.extend(_coverage_substance_problems(doc, path.name))
    return problems


def _coverage_substance_problems(doc: dict, name: str) -> list[str]:
    """Strict, MANDATORY-FIELD validation of the coverage artifact.

    Every substantive field must be PRESENT and exactly correct — an absent
    key is never treated as satisfying the invariant. The single understood
    WARN is bound to the actual machine-readable Good Friday fact
    (`missing_pre_rth_short_sessions == ["2025-04-18"]`), not merely to the
    check's name, and the top-level status must be coherent with the checks:
    PASS only when everything passes and no pre-RTH session is missing; WARN
    only for the exact understood condition.
    """
    problems: list[str] = []

    def _require_int(key: str, expected: int) -> None:
        if key not in doc:
            problems.append(f"{name}: missing required key {key!r}")
            return
        v = doc[key]
        if isinstance(v, bool) or type(v) is not int:
            problems.append(
                f"{name}: {key} must be a plain non-boolean int, got {v!r}")
            return
        if v != expected:
            problems.append(f"{name}: {key}={v} (expected {expected})")

    _require_int("n_expected_complete_sessions",
                 EXPECTED_COVERAGE_EXPECTED_SESSIONS)
    _require_int("n_fail", 0)
    _require_int("cross_file_order_violations", 0)

    if "missing_sessions" not in doc:
        problems.append(f"{name}: missing required key 'missing_sessions'")
    elif not isinstance(doc["missing_sessions"], list) or \
            doc["missing_sessions"] != []:
        problems.append(
            f"{name}: missing_sessions must be exactly [], got "
            f"{doc['missing_sessions']!r}")

    pre_key = "missing_pre_rth_short_sessions"
    pre = None
    if pre_key not in doc:
        problems.append(f"{name}: missing required key {pre_key!r}")
    elif not isinstance(doc[pre_key], list) or not all(
            isinstance(x, str) for x in doc[pre_key]):
        problems.append(
            f"{name}: {pre_key} must be a list of date strings, got "
            f"{doc[pre_key]!r}")
    else:
        pre = doc[pre_key]

    checks = doc.get("checks")
    if not isinstance(checks, list) or not checks:
        problems.append(f"{name}: coverage checks missing or empty")
        return problems
    names = []
    for c in checks:
        if not isinstance(c, dict) or not isinstance(c.get("check"), str) \
                or c.get("status") not in (st.PASS, st.WARN, st.FAIL):
            problems.append(f"{name}: malformed coverage check entry {c!r}")
            continue
        names.append(c["check"])
    if len(names) != len(set(names)):
        problems.append(f"{name}: duplicate coverage check names")
    if problems and not names:
        return problems

    non_pass = [c for c in checks if isinstance(c, dict)
                and c.get("status") != st.PASS]
    if not non_pass:
        expected_status = st.PASS
        if pre is not None and pre != []:
            problems.append(
                f"{name}: all coverage checks PASS but {pre_key}={pre!r} is "
                "not empty (incoherent)")
    elif (len(non_pass) == 1
            and non_pass[0].get("check") in UNDERSTOOD_COVERAGE_WARN_CHECKS
            and non_pass[0].get("status") == st.WARN):
        expected_status = st.WARN
        if pre is not None and pre != EXPECTED_PRE_RTH_MISSING_SESSIONS:
            problems.append(
                f"{name}: the understood WARN requires {pre_key} == "
                f"{EXPECTED_PRE_RTH_MISSING_SESSIONS}, got {pre!r}")
    else:
        expected_status = None
        problems.append(
            f"{name}: non-PASS coverage checks "
            f"{[(c.get('check'), c.get('status')) for c in non_pass]} are not "
            f"the single understood "
            f"{sorted(UNDERSTOOD_COVERAGE_WARN_CHECKS)} WARN")

    if expected_status is not None and doc.get("status") != expected_status:
        problems.append(
            f"{name}: top-level status {doc.get('status')!r} is incoherent "
            f"with its checks (expected {expected_status})")
    return problems


def _binding_verdict(binding: dict, non_blocking: tuple = ()) -> str:
    """Worst status across a binding's checks, ignoring explicitly
    non-blocking (deferred) checks."""
    return st.worst(c["status"] for c in binding.get("checks", [])
                    if c["check"] not in non_blocking)


def _policy_binding_core(root: Path, droot: Path) -> tuple[dict, list]:
    """Config-level PA-0002 facts provable at ANY generation stage. Never
    reads a previously generated closeout OUTPUT."""
    binding = {
        "amendment": "PA-0002",
        "evidence_disposition": None,
        "calendar_state_provisional": True,
        "research_eligibility_policy_sha256": None,
        "research_eligibility_policy_state": None,
        "quarantined_dates": [],
        "quarantined_dates_digest": None,
        "n_quarantined_calendar_dates": None,
    }
    checks = []
    try:
        from nqresearch.eligibility import (
            load_policy_for_reporting,
            policy_sha256,
        )

        policy, disposition = load_policy_for_reporting(root, droot)
        binding["evidence_disposition"] = disposition
        binding["research_eligibility_policy_sha256"] = policy_sha256(root)
        binding["research_eligibility_policy_state"] = policy.meta.status
        binding["quarantined_dates"] = sorted(policy.dates)
        binding["quarantined_dates_digest"] = policy.digest()
        binding["n_quarantined_calendar_dates"] = len(policy.dates)
        checks.append(st.check("eligibility_policy_bound_to_evidence_matrix",
                               st.PASS,
                               "policy binds the committed evidence matrix "
                               "SHA-256 and validates strictly"))
        checks.append(st.check("pending_dates_exactly_covered", st.PASS,
                               f"disposition {disposition}: every pending "
                               "date is covered exactly by the policy; no "
                               "conflict is dispositioned"))
    except Exception as e:  # fail-safe: record, never claim success
        checks.append(st.check("eligibility_policy_bound_to_evidence_matrix",
                               st.FAIL, f"unavailable/invalid: {e}"))
        checks.append(st.check("pending_dates_exactly_covered", st.FAIL,
                               "policy could not be validated"))
    checks.append(st.check(
        "calendar_disposition_truth_preserved", st.PASS,
        "quarantine is a research-policy disposition only: evidence states "
        "are unchanged (PENDING_EVIDENCE) and the calendar is never "
        "relabelled DOCUMENT_VERIFIED"))
    return binding, checks


def _block_stage_binding(candidate_sessions: list[str],
                         candidate_blocks: list[dict],
                         source_artifact: Path) -> dict:
    """PA-0002 binding for the MBO-BLOCK CANDIDATE currently being generated.

    Facts describe the CANDIDATE, never a previously written artifact. The
    full structural-quarantine proof needs partition ranges and roll decision
    sources, which do not exist at this stage, so it is explicitly DEFERRED
    rather than claimed.
    """
    from nqresearch import paths
    from nqresearch.config import _repo_root

    root, droot = _repo_root(), paths.data_root()
    binding, checks = _policy_binding_core(root, droot)
    q = set(binding["quarantined_dates"])

    cand_sessions = set(candidate_sessions)
    spans = [(b["mbo_lab_block_id"], b["start"], b["end"])
             for b in candidate_blocks]
    hit_sessions = sorted(q & cand_sessions)
    hit_spans = sorted(
        bid for bid, s, e in spans for d in q if s <= d <= e
    )
    binding["candidate"] = {
        "n_candidate_mbo_sessions": len(candidate_sessions),
        "n_candidate_mbo_blocks": len(candidate_blocks),
        "quarantined_dates_in_candidate_sessions": hit_sessions,
        "quarantined_dates_inside_candidate_block_spans": hit_spans,
    }
    checks.append(st.check(
        "quarantine_disjoint_from_candidate_mbo_blocks",
        st.PASS if not hit_sessions and not hit_spans else st.FAIL,
        f"{len(candidate_sessions)} candidate MBO sessions in "
        f"{len(candidate_blocks)} candidate blocks; quarantined dates in "
        f"candidate sessions: {hit_sessions}; inside candidate block spans: "
        f"{hit_spans}"))
    checks.append(st.check(
        "quarantine_structurally_safe", st.WARN,
        "DEFERRED to the partition-proposal stage: partition ranges and "
        "causal-roll decision sources are not available while freezing "
        "blocks, so full structural safety cannot be proven here"))

    # Only hash bytes actually consumed by THIS stage, and require each
    # recorded identity to be a real 64-lowercase-hex SHA-256.
    src = {"mbo_deep_audit": _sha256_file(Path(source_artifact))}
    binding["source_artifact_sha256"] = src
    bad = sorted(k for k, v in src.items() if not _is_sha256_hex(v))
    checks.append(st.check(
        "structural_artifact_identities_valid",
        st.PASS if not bad else st.FAIL,
        "valid SHA-256 recorded for every source artifact consumed at this "
        f"stage: {sorted(k for k, v in src.items() if _is_sha256_hex(v))}"
        + (f"; INVALID/MISSING: {bad}" if bad else "")))
    binding["checks"] = checks
    return binding


def _proposal_stage_binding(blocks_frozen: dict, proposal_counts: dict,
                            mbo_blocks_artifact_sha256: str | None) -> dict:
    """PA-0002 binding for the PARTITION-PROPOSAL CANDIDATE being generated.

    Structural facts come from the CANDIDATE blocks passed in and the
    candidate partition counts being produced — never from a previously
    written partition_proposal.json. The exact newly-written MBO-block
    artifact hash is bound here, together with the coverage and front-series
    identities the activation verifier will later require.
    """
    from datetime import date as _date

    from nqresearch import paths
    from nqresearch.config import _repo_root

    root, droot = _repo_root(), paths.data_root()
    binding, checks = _policy_binding_core(root, droot)
    q = set(binding["quarantined_dates"])
    close = droot / "qa" / "m0_closeout"

    cand_sessions = set()
    spans = []
    for b in blocks_frozen.get("blocks", []):
        cand_sessions |= set(b["sessions"])
        spans.append((b["mbo_lab_block_id"], b["start"], b["end"]))

    dev = (PROPOSED_DEV_START.isoformat(), PROPOSED_DEV_END.isoformat())
    sel = (PROPOSED_SELECTION_START.isoformat(),
           PROPOSED_SELECTION_END.isoformat())
    hold = (PROPOSED_HOLDOUT_START.isoformat(),
            PROPOSED_HOLDOUT_END.isoformat())
    boundaries = {dev[0], dev[1], sel[0], sel[1], hold[0], hold[1]}

    # Coverage is an INPUT to the proposal stage (observed session universe).
    cov_path = close / "mbp1_full_history_coverage.json"
    front_path = close / "mbp1_front_contract_series.json"
    observed, decision_sources, cov_expected = [], set(), None
    try:
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
        observed = [s["session_id"] for s in cov.get("sessions", [])]
        cov_expected = cov.get("n_expected_complete_sessions")
    except Exception:
        pass
    try:
        fr = json.loads(front_path.read_text(encoding="utf-8"))
        decision_sources = {s["decided_from_session"]
                            for s in fr.get("switches", [])}
        n_switches = fr.get("n_switches")
    except Exception:
        n_switches = None

    dev_obs = [s for s in observed if dev[0] <= s <= dev[1]]
    dev_eligible = [s for s in dev_obs if s not in q]
    violations = []
    for d in sorted(q):
        if not (dev[0] <= d <= dev[1]):
            violations.append(f"{d}: not in DEV")
        if sel[0] <= d <= sel[1] or hold[0] <= d <= hold[1]:
            violations.append(f"{d}: in SELECTION/HOLDOUT")
        if d in boundaries:
            violations.append(f"{d}: partition boundary")
        if d in cand_sessions:
            violations.append(f"{d}: candidate MBO session")
        for bid, s, e in spans:
            if s <= d <= e:
                violations.append(f"{d}: inside candidate block {bid}")
        if d in decision_sources:
            violations.append(f"{d}: causal-roll decision source")

    binding["candidate"] = {
        "n_candidate_mbo_sessions": len(cand_sessions),
        "n_candidate_mbo_blocks": blocks_frozen.get("n_blocks"),
        "n_candidate_spanning_mbo_blocks": proposal_counts.get("n_spanning"),
        "n_coverage_expected_sessions": cov_expected,
        "n_observed_dev_sessions": len(dev_obs),
        "n_eligible_observed_dev_sessions": len(dev_eligible),
        "n_excluded_observed_dev_sessions": len(dev_obs) - len(dev_eligible),
        "n_causal_roll_switches": n_switches,
        "partition_trading_days": proposal_counts.get("trading_days"),
        "quarantine_violations": violations,
    }
    binding["n_excluded_observed_dev_sessions"] = \
        len(dev_obs) - len(dev_eligible)
    binding["n_eligible_observed_dev_sessions"] = len(dev_eligible)
    checks.append(st.check(
        "quarantine_structurally_safe",
        st.PASS if not violations else st.FAIL,
        f"no quarantined date is a partition boundary, candidate MBO "
        f"session, inside a candidate block span, or a causal-roll decision "
        f"source (violations: {violations})"))

    ident = {
        "coverage_artifact_sha256": _sha256_file(cov_path),
        "front_contract_series_sha256": _sha256_file(front_path),
        "mbo_blocks_sha256": mbo_blocks_artifact_sha256,
    }
    binding["structural_artifact_sha256"] = ident
    bad = sorted(k for k, v in ident.items() if not _is_sha256_hex(v))
    # "Identities valid" must mean the INPUTS were substantively validated,
    # not merely that a file existed and produced some hash.
    problems = list(_validate_input_artifact(
        cov_path, "mbp1_full_history_coverage",
        ("sessions", "n_expected_complete_sessions"),
        PERMITTED_COVERAGE_STATUSES))
    problems += _validate_input_artifact(
        front_path, "mbp1_front_contract_series",
        ("switches", "n_switches"), (st.PASS,))
    binding["structural_input_validation_problems"] = problems
    checks.append(st.check(
        "structural_artifact_identities_valid",
        st.PASS if not bad and not problems else st.FAIL,
        "every bound identity is a 64-lowercase-hex SHA-256 and every "
        "consumed input passed type/keys/status/envelope validation"
        + (f"; INVALID IDENTITIES: {bad}" if bad else "")
        + (f"; INPUT PROBLEMS: {problems}" if problems else "")))
    binding["checks"] = checks
    _ = _date  # keep import local and explicit
    return binding

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
    binding = _block_stage_binding(
        [d.isoformat() for d in dates], frozen, mbo_deep_artifact)
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
        "state": _calendar_evidence_state(),
        "activation_ready": False,
        "activation_ready_conditions": [
            "every exceptional date is either evidence-resolved per PA-0001 "
            "(DOCUMENT_VERIFIED / TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE) "
            "or dispositioned by the reviewed PA-0002 research-eligibility "
            "quarantine; no conflicts (config/data/cme_calendar_evidence.yaml "
            "+ config/data/research_eligibility.yaml)",
            "all structural partition checks PASS",
            "explicit human partition approval has been recorded, binding "
            "the exact proposal, effective-calendar, evidence-matrix, "
            "CME-correspondence and research-eligibility-policy hashes in "
            "the append-only audit log",
        ],
        "provisional_note": (
            "Block IDs inherit the calendar evidence state: until every "
            "exceptional session of the effective calendar is resolved at "
            "date level per PA-0001 (see cme_calendar_evidence.yaml and "
            "cme_calendar_overrides.yaml meta.baseline_verification), blocks "
            "and partition dates must not be described as fully "
            "authoritative. The status field expresses computational "
            "validity only, never activation readiness."
        ),
        "research_eligibility_binding": binding,
        "n_sessions_final": len(dates),
        "reclassifications": reclassified,
        "blocks": frozen,
        "n_blocks": len(frozen),
        "acquisition_reason": "UNKNOWN_NOT_RECORDED_PENDING_USER_INPUT",
        "checks": checks,
        # The top-level verdict INCLUDES the research-eligibility binding: a
        # candidate must never present PASS while an embedded mandatory
        # safety/identity check says FAIL. The block-stage
        # quarantine_structurally_safe WARN is deliberately non-blocking
        # here because full proof is only available at proposal generation.
        "status": st.worst([c["status"] for c in checks]
                           + [_binding_verdict(
                               binding,
                               non_blocking=("quarantine_structurally_safe",))]),
    }


def propose_partitions(blocks_frozen: dict,
                       mbo_blocks_artifact_sha256: str | None = None) -> dict:
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
    binding = _proposal_stage_binding(
        blocks_frozen,
        {"n_spanning": len(mbo_blocks["SPANNING"]),
         "trading_days": {
             "DEV": trading_days(PROPOSED_DEV_START, PROPOSED_DEV_END),
             "SELECTION": trading_days(PROPOSED_SELECTION_START,
                                       PROPOSED_SELECTION_END),
             "HOLDOUT": trading_days(PROPOSED_HOLDOUT_START,
                                     PROPOSED_HOLDOUT_END)}},
        mbo_blocks_artifact_sha256)
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
        "calendar_verification_state": _calendar_evidence_state(),
        "activation_ready": False,
        "activation_ready_conditions": [
            "every exceptional date is either evidence-resolved per PA-0001 "
            "(DOCUMENT_VERIFIED / TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE) "
            "or dispositioned by the reviewed PA-0002 research-eligibility "
            "quarantine; no conflicts (config/data/cme_calendar_evidence.yaml "
            "+ config/data/research_eligibility.yaml)",
            "all structural partition checks PASS",
            "explicit human partition approval has been recorded, binding "
            "the exact proposal, effective-calendar, evidence-matrix, "
            "CME-correspondence and research-eligibility-policy hashes in "
            "the append-only audit log",
        ],
        "note": (
            "Boundaries derived only from coverage, calendar validity, MBO "
            "placement, and desired period lengths — never model outcomes. "
            "The ~2026-04-01 holdout boundary remains TENTATIVE per canonical "
            "§5.3 until explicitly approved. Activation/freezing requires "
            "explicit human approval and a follow-up protocol step."
        ),
        "research_eligibility_binding": binding,
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
        # The exact three structural checks are preserved above (activation
        # requires that exact set), but the top-level verdict ALSO
        # incorporates the research-eligibility binding: a proposal must
        # never present PASS while an embedded mandatory safety or identity
        # check says FAIL.
        "status": st.worst([c["status"] for c in checks]
                           + [_binding_verdict(binding)]),
    }
