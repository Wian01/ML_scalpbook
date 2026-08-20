"""Shared synthetic builders for the date-level calendar-evidence model
(PA-0001). Synthetic trees only — never the live repo/data roots."""

import hashlib
import json

import yaml

from nqresearch.calendar_evidence import (
    EXPECTED_EXCEPTIONAL_DATES,
    STATE_DOCUMENT_VERIFIED,
    STATE_PENDING,
    STATE_TRIANGULATED,
)

_STRENGTH = {"CONFLICT_REQUIRES_REVIEW": 0, STATE_PENDING: 1,
             STATE_TRIANGULATED: 2, STATE_DOCUMENT_VERIFIED: 3}

SYN_EMAIL_FIELDS = {
    "sender": "CME Global Command Center <gcc@cmegroup.com>",
    "sender_mailbox": "gcc@cmegroup.com",
    "sender_domain": "cmegroup.com",
    "subject": "Request for archived schedules 00001234",
    "message_date_utc": "2099-01-01T00:00:00Z",
    "message_id": "<synthetic-0001@sfdc.invalid>",
    "body_statement": (
        "Unfortunately we do not have an archive for previous years "
        "holidays calendar."
    ),
    "referral_url": "https://www.cmegroup.com/trading-hours.html",
}


def synthetic_eml_bytes(from_addr=None, subject=None, date_hdr=None,
                        message_id=None, dkim=None, auth_results=None,
                        body=None) -> bytes:
    """A real, parseable RFC-822 message matching SYN_EMAIL_FIELDS by
    default; every field is overridable for adversarial mutations."""
    f = SYN_EMAIL_FIELDS
    headers = [
        ("From", from_addr if from_addr is not None else f["sender"]),
        ("To", "researcher@example.invalid"),
        ("Subject", subject if subject is not None else f["subject"]),
        ("Date", date_hdr if date_hdr is not None
         else "Fri, 01 Jan 2099 00:00:00 +0000"),
        ("Message-ID", message_id if message_id is not None
         else f["message_id"]),
        ("DKIM-Signature", dkim if dkim is not None
         else "v=1; a=rsa-sha256; d=cmegroup.com; s=SYN; b=deadbeef"),
        ("Authentication-Results", auth_results if auth_results is not None
         else ("mx.example.invalid; dkim=pass header.i=@cmegroup.com; "
               "spf=pass smtp.mailfrom=bounce.example; "
               "dmarc=pass header.from=cmegroup.com")),
        ("MIME-Version", "1.0"),
        ("Content-Type", 'text/plain; charset="utf-8"'),
    ]
    body_text = body if body is not None else (
        f["body_statement"] + "\nYou may refer to the CME Holiday page: "
        + f["referral_url"] + "\nRegards, GCC\n"
    )
    raw = "".join(f"{k}: {v}\r\n" for k, v in headers) + "\r\n" + body_text
    return raw.encode("utf-8")


def write_evidence_file(evid_dir, name, content: bytes) -> str:
    evid_dir.mkdir(parents=True, exist_ok=True)
    p = evid_dir / name
    p.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def rehash_source_file(matrix_doc, evid_dir, source_id, fname):
    """Recompute a source file's declared hash from the CURRENT bytes on
    disk — used by adversarial tests that mutate evidence content and must
    prove the failure comes from parsed-content inconsistency, not from a
    stale hash."""
    sha = hashlib.sha256((evid_dir / fname).read_bytes()).hexdigest()
    for s in matrix_doc["sources"]:
        if s["id"] == source_id:
            for f in s["files"]:
                if f["file"] == fname:
                    f["sha256"] = sha
                    return sha
    raise AssertionError((source_id, fname))


def synthetic_matrix_doc(evid_dir, date_states=None, observed_available=None,
                         session_present=None):
    """Fully valid synthetic evidence matrix over the REAL frozen date set.

    Defaults: every date DOCUMENT_VERIFIED via one synthetic official CME
    document; a parseable, header-consistent GCC email; a strong secondary
    source; a lower-tier and a tertiary source available for adversarial
    mutations. Returns (matrix_doc, sha_by_file).

    NOTE: meta.observed_reference.artifact_sha256 is filled in by
    write_coverage_for(); call it before validating/writing the matrix.
    """
    date_states = date_states or {}
    observed_available = observed_available or {}
    session_present = session_present or {}
    shas = {
        "official.bin": write_evidence_file(evid_dir, "official.bin", b"official doc"),
        "email.eml": write_evidence_file(evid_dir, "email.eml", synthetic_eml_bytes()),
        "strong.html": write_evidence_file(evid_dir, "strong.html", b"strong secondary"),
        "lower.html": write_evidence_file(evid_dir, "lower.html", b"lower secondary"),
        "kibot.html": write_evidence_file(evid_dir, "kibot.html", b"tertiary dates"),
    }
    all_dates = sorted(EXPECTED_EXCEPTIONAL_DATES)

    def src(sid, tier, fname, claims):
        return {
            "id": sid, "tier": tier, "title": f"synthetic {sid}",
            "url": "https://example.invalid/x",
            "retrieval_method": "SYNTHETIC",
            "retrieved_utc": "2099-01-01T00:00:00Z",
            "files": [{"file": fname, "sha256": shas[fname]}],
            "applicable_dates": all_dates,
            "claims": claims,
        }

    dates = []
    for iso in all_dates:
        state = date_states.get(iso, STATE_DOCUMENT_VERIFIED)
        present = session_present.get(iso, True)
        entry = {
            "date": iso,
            "holiday_group": EXPECTED_EXCEPTIONAL_DATES[iso],
            "instrument_scope": "CME equity index futures (synthetic)",
            "expected_ct": "synthetic 12:00 halt",
            "observed": {
                "session_present": present,
                "rth_span_seconds": 12600.0 if present else None,
                "expected_rth_span_seconds": 12600 if present else None,
                "data_available": observed_available.get(iso, True),
                "note": "synthetic",
            },
            "evidence": [
                {"source": "syn-official", "claim_id": "official-schedule",
                 "kind": "DIRECT"},
                {"source": "syn-email", "claim_id": "archive-unavailable",
                 "kind": "DIRECT"},
                {"source": "syn-strong", "claim_id": "secondary-schedule",
                 "kind": "DIRECT"},
            ],
            "agreement": "AGREES",
            "state": state,
        }
        dates.append(entry)
    doc = {
        "meta": {
            "purpose": "synthetic",
            "evidence_root": "reference/cme_calendar",
            "observed_reference": {
                "artifact": "qa/m0_closeout/mbp1_full_history_coverage.json",
                # set by write_coverage_for()
                "substance_digest_algorithm": "coverage-substance-v1",
                "substance_sha256": None,
            },
        },
        "archive_unavailability": {
            "statement": "synthetic archive unavailability",
            "email_source": "syn-email",
            "authentication": "recipient-recorded results (synthetic)",
            **SYN_EMAIL_FIELDS,
        },
        "sources": [
            src("syn-official", "OFFICIAL_CME", "official.bin",
                [{"id": "official-schedule", "text": "official schedule"}]),
            src("syn-email", "OFFICIAL_CME_CORRESPONDENCE", "email.eml",
                [{"id": "archive-unavailable",
                  "text": "archive unavailability only"}]),
            src("syn-strong", "SECONDARY_STRONG", "strong.html",
                [{"id": "secondary-schedule", "text": "secondary schedule"}]),
            src("syn-lower", "SECONDARY_LOWER", "lower.html",
                [{"id": "lower-row", "text": "early close 12:00"}]),
            src("syn-kibot", "TERTIARY_DATE_ONLY", "kibot.html",
                [{"id": "holiday-dates", "text": "holiday date exists"}]),
        ],
        "dates": dates,
    }
    return doc, shas


def write_coverage_for(data_root, matrix_doc):
    """Coverage artifact whose sessions agree with the matrix observed
    blocks; binds the artifact's SHA-256 into the matrix doc's
    meta.observed_reference (call BEFORE writing/validating the matrix)."""
    cov_dir = data_root / "qa" / "m0_closeout"
    cov_dir.mkdir(parents=True, exist_ok=True)
    sessions = [
        {"session_id": d["date"],
         "rth_span_seconds": d["observed"]["rth_span_seconds"]}
        for d in matrix_doc["dates"] if d["observed"]["session_present"]
    ]
    p = cov_dir / "mbp1_full_history_coverage.json"
    # Coverage substance mirrors the real corpus state: only the understood
    # pre-RTH Good Friday WARN, zero FAILs, no missing sessions, no ordering
    # violations, and the frozen 516 expected-session count.
    p.write_text(json.dumps({
        **clean_envelope(),
        "artifact": "mbp1_full_history_coverage",
        "status": "WARN",
        "n_expected_complete_sessions": 516,
        "n_fail": 0,
        "missing_sessions": [],
        "cross_file_order_violations": 0,
        "missing_pre_rth_short_sessions": ["2025-04-18"],
        "checks": [
            {"check": "no_missing_expected_sessions", "status": "PASS",
             "detail": "synthetic"},
            {"check": "pre_rth_short_sessions_without_data", "status": "WARN",
             "detail": "synthetic understood WARN"},
            {"check": "no_session_fails", "status": "PASS",
             "detail": "synthetic"},
            {"check": "degraded_dates_assessed", "status": "PASS",
             "detail": "synthetic"},
            {"check": "cross_file_monotonic_order", "status": "PASS",
             "detail": "synthetic"},
        ],
        "sessions": sessions}))
    # The matrix binds the versioned SUBSTANCE digest (envelope-independent),
    # never the whole-file hash — the whole-file identity is bound separately
    # at activation.
    from nqresearch.calendar_evidence import (
        COVERAGE_SUBSTANCE_ALGORITHM,
        coverage_substance_sha256,
    )

    ref = matrix_doc["meta"]["observed_reference"]
    ref["substance_digest_algorithm"] = COVERAGE_SUBSTANCE_ALGORITHM
    ref["substance_sha256"] = coverage_substance_sha256(
        json.loads(p.read_text()))
    return p


def overrides_groups_for(matrix_doc, group_names):
    """Overrides group summaries computed the conservative way (weakest
    member) from a matrix doc, restricted to the frozen nine groups."""
    rollup, per_date = {}, {}
    for d in matrix_doc["dates"]:
        g, s = d["holiday_group"], d["state"]
        per_date.setdefault(g, {})[d["date"]] = s
        if g not in rollup or _STRENGTH[s] < _STRENGTH[rollup[g]]:
            rollup[g] = s
    return [
        {"holiday_group": name, "status": rollup[name],
         "dates": per_date[name]}
        for name in sorted(group_names)
    ]


def write_matrix(repo_root, matrix_doc):
    p = repo_root / "config" / "data" / "cme_calendar_evidence.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(matrix_doc, sort_keys=False))
    return hashlib.sha256(p.read_bytes()).hexdigest()


def eligibility_policy_doc(matrix_sha, dates=(), status=None,
                           meta_override=None, **semantics_override):
    """Schema-valid PA-0002 policy over the given (possibly empty) dates.

    Uses the REAL PA-0002 identity constants and a legitimate lifecycle
    state (default: APPROVED_FOR_ACTIVATION, so activation fixtures reach
    the checks under test); never an arbitrary placeholder.
    """
    from nqresearch.eligibility import (
        PA0002_AMENDMENT_PATH,
        PA0002_POLICY_ID,
        PA0002_REASON_CODE,
        POLICY_STATE_APPROVED,
    )
    semantics = {
        "qa_and_normalization_use": "ALLOWED_FOR_QA_AND_SESSION_RECONSTRUCTION",
        "research_use": "FORBIDDEN",
        "feature_window_crossing": "FORBIDDEN",
        "label_horizon_crossing": "FORBIDDEN",
        "evaluation_window_crossing": "FORBIDDEN",
        "rolling_state_reset_required_at_next_eligible_session": True,
        "prior_session_state_features_require_policy_review": True,
        "calendar_membership_unchanged": True,
        "partition_contiguity_unchanged": True,
        "coverage_counts_unchanged": True,
        "causal_roll_series_consumes_eligibility": False,
        "raw_data_unchanged": True,
        "n_mbo_blocks_quarantined": 0,
        "holdout_sealed": True,
    }
    semantics.update(semantics_override)
    meta = {
        "policy_id": PA0002_POLICY_ID,
        "policy_version": 1,
        "amendment": PA0002_AMENDMENT_PATH,
        "status": status or POLICY_STATE_APPROVED,
        "canonical_basis": "canonical §50 predefined holiday/partial-session",
        "evidence_matrix_sha256": matrix_sha,
        "rationale": "synthetic fixture rationale",
    }
    meta.update(meta_override or {})
    return {
        "meta": meta,
        "semantics": semantics,
        "quarantined_sessions": [
            {"date": d, "research_eligible": False,
             "reason_code": PA0002_REASON_CODE,
             "evidence_state_at_policy_time": "PENDING_EVIDENCE",
             "note": "synthetic fixture note"}
            for d in sorted(dates)
        ],
    }


def clean_envelope():
    """A COMPLETE provenance envelope satisfying the AL-0043/44/45 activation
    policy: clean generation at a REAL ancestral commit of the project
    repository, under the current effective config and package code. Carries
    all eight reserved envelope fields, as qa/report.py stamps them."""
    import subprocess

    import nqresearch
    from nqresearch import paths
    from nqresearch.config import effective_config_hash
    from nqresearch.qa.cache import package_source_hash

    sha = subprocess.run(["git", "-C", str(paths.ROOT), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    return {
        "generated_at_utc": "2099-01-01T00:00:00+00:00",
        "nqresearch_version": nqresearch.__version__,
        "git_sha": sha,
        "generation_git_clean": True,
        "restamp_note": "Generated from a clean committed tree at the "
                        "recorded git_sha.",
        "audit_code_hash": package_source_hash(),
        "config_hash": effective_config_hash(),
        "data_root": "synthetic",
    }


def write_structural_artifacts(data_root, matrix_doc=None):
    """Minimal but structurally valid MBO-block and front-series artifacts,
    with per-artifact permitted statuses and clean provenance envelopes, so
    activation's identity/structure/envelope checks can run against
    synthetic trees. Returns their SHA-256 identities."""
    close = data_root / "qa" / "m0_closeout"
    close.mkdir(parents=True, exist_ok=True)
    env = clean_envelope()
    out = {}
    for fname, doc in [
        ("mbo_blocks_frozen.json",
         {**env, "artifact": "mbo_blocks_frozen", "status": "PASS",
          "blocks": [{"mbo_lab_block_id": "MBO-BLK-001",
                      "start": "2099-01-06", "end": "2099-01-06",
                      "n_sessions": 1, "sessions": ["2099-01-06"]}],
          "n_blocks": 1}),
        ("mbp1_front_contract_series.json",
         {**env, "artifact": "mbp1_front_contract_series", "status": "PASS",
          "switches": [], "n_switches": 0, "per_session": []}),
    ]:
        p = close / fname
        p.write_text(json.dumps(doc))
        out[fname] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def write_eligibility_policy(repo_root, matrix_sha, dates=(), doc=None):
    p = repo_root / "config" / "data" / "research_eligibility.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(
        doc if doc is not None else eligibility_policy_doc(matrix_sha, dates),
        sort_keys=False))
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# A COMPLETE synthetic corpus that satisfies the frozen quarantine invariants
# (516 / 318-100-98 / 317 / 309 / 8 / 77 / 30 / 0 / 8). Used by the end-to-end
# activation test, which must exercise the real generator rather than a
# hand-written active configuration. Synthetic temporary trees only.
# ---------------------------------------------------------------------------

QUARANTINED_DATES = (
    "2024-09-02", "2024-11-29", "2025-01-01", "2025-01-20", "2025-02-17",
    "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-03", "2025-07-04",
)
# Exactly two of the ten have no observed session, so the frozen invariant
# "8 excluded observed DEV sessions" holds.
UNOBSERVED_QUARANTINED_DATES = ("2025-01-01", "2025-07-04")
MANDATORY_PROPOSAL_CHECKS = ("boundaries_on_trading_days",
                             "partition_ranges_contiguous",
                             "no_partition_spanning_mbo_blocks")


def _weekdays(start, end):
    from datetime import timedelta

    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _chunk(items, n_chunks):
    base, rem = divmod(len(items), n_chunks)
    out, i = [], 0
    for k in range(n_chunks):
        size = base + (1 if k < rem else 0)
        out.append(items[i:i + size])
        i += size
    return out


def _full_corpus_coverage(data_root, matrix_doc):
    """Coverage agreeing with the matrix AND carrying exactly 317 observed DEV
    sessions, eight of which are quarantined."""
    from nqresearch.qa.closeout import PROPOSED_DEV_END, PROPOSED_DEV_START

    quarantined = set(QUARANTINED_DATES)
    sessions = {
        d["date"]: {"session_id": d["date"],
                    "rth_span_seconds": d["observed"]["rth_span_seconds"]}
        for d in matrix_doc["dates"] if d["observed"]["session_present"]
    }
    lo, hi = PROPOSED_DEV_START.isoformat(), PROPOSED_DEV_END.isoformat()
    n_dev = sum(1 for s in sessions if lo <= s <= hi)
    for d in _weekdays(PROPOSED_DEV_START, PROPOSED_DEV_END):
        if n_dev >= 317:
            break
        iso = d.isoformat()
        if iso in sessions or iso in quarantined:
            continue
        sessions[iso] = {"session_id": iso, "rth_span_seconds": 23400.0}
        n_dev += 1
    assert n_dev == 317, n_dev
    doc = {
        **clean_envelope(),
        "artifact": "mbp1_full_history_coverage",
        "status": "WARN",
        "n_expected_complete_sessions": 516,
        "n_fail": 0,
        "missing_sessions": [],
        "cross_file_order_violations": 0,
        "missing_pre_rth_short_sessions": ["2025-04-18"],
        "checks": [
            {"check": "no_missing_expected_sessions", "status": "PASS",
             "detail": "synthetic"},
            {"check": "pre_rth_short_sessions_without_data", "status": "WARN",
             "detail": "synthetic understood WARN"},
            {"check": "no_session_fails", "status": "PASS",
             "detail": "synthetic"},
            {"check": "degraded_dates_assessed", "status": "PASS",
             "detail": "synthetic"},
            {"check": "cross_file_monotonic_order", "status": "PASS",
             "detail": "synthetic"},
        ],
        "sessions": [sessions[k] for k in sorted(sessions)],
    }
    close = data_root / "qa" / "m0_closeout"
    close.mkdir(parents=True, exist_ok=True)
    p = close / "mbp1_full_history_coverage.json"
    p.write_text(json.dumps(doc, indent=2))
    from nqresearch.calendar_evidence import (
        COVERAGE_SUBSTANCE_ALGORITHM,
        coverage_substance_sha256,
    )

    ref = matrix_doc["meta"]["observed_reference"]
    ref["substance_digest_algorithm"] = COVERAGE_SUBSTANCE_ALGORITHM
    ref["substance_sha256"] = coverage_substance_sha256(
        json.loads(p.read_text()))
    return p


def _full_corpus_blocks(data_root):
    """30 MBO blocks holding 77 sessions, distributed 23/23/31, none of them
    a quarantined date and none spanning a partition boundary."""
    from datetime import date

    from nqresearch.qa.closeout import (
        PROPOSED_DEV_END,
        PROPOSED_HOLDOUT_END,
        PROPOSED_HOLDOUT_START,
        PROPOSED_SELECTION_END,
        PROPOSED_SELECTION_START,
    )

    # DEV blocks start after the last quarantined DEV date (2025-07-04), so no
    # block span can ever contain one.
    plan = [
        ("DEV", date(2025, 8, 1), PROPOSED_DEV_END, 9, 23),
        ("SELECTION", PROPOSED_SELECTION_START, PROPOSED_SELECTION_END, 9, 23),
        ("HOLDOUT", PROPOSED_HOLDOUT_START, PROPOSED_HOLDOUT_END, 12, 31),
    ]
    blocks, per_partition, n = [], {}, 0
    for name, start, end, n_blocks, n_sessions in plan:
        days = [d.isoformat() for d in _weekdays(start, end)][:n_sessions]
        assert len(days) == n_sessions, (name, len(days))
        ids = []
        for chunk in _chunk(days, n_blocks):
            n += 1
            bid = f"MBO-BLK-{n:03d}"
            ids.append(bid)
            blocks.append({"mbo_lab_block_id": bid, "start": chunk[0],
                           "end": chunk[-1], "n_sessions": len(chunk),
                           "sessions": chunk})
        per_partition[name] = ids
    per_partition["SPANNING"] = []
    doc = {**clean_envelope(), "artifact": "mbo_blocks_frozen", "status": "PASS",
           "blocks": blocks, "n_blocks": len(blocks),
           "n_sessions_final": sum(b["n_sessions"] for b in blocks)}
    assert doc["n_blocks"] == 30 and doc["n_sessions_final"] == 77
    p = data_root / "qa" / "m0_closeout" / "mbo_blocks_frozen.json"
    p.write_text(json.dumps(doc, indent=2))
    return p, per_partition


def _full_corpus_front_series(data_root):
    """Eight causal roll switches, none decided from a quarantined session and
    none touching the 2026-08-17 partial edge session."""
    switches = [
        {"session_id": s, "decided_from_session": d, "front": "NQZ4"}
        for s, d in [
            ("2024-09-13", "2024-09-12"), ("2024-12-13", "2024-12-12"),
            ("2025-03-14", "2025-03-13"), ("2025-06-13", "2025-06-12"),
            ("2025-09-12", "2025-09-11"), ("2025-12-12", "2025-12-11"),
            ("2026-03-13", "2026-03-12"), ("2026-06-12", "2026-06-11"),
        ]
    ]
    assert not (set(s["decided_from_session"] for s in switches)
                & set(QUARANTINED_DATES))
    doc = {**clean_envelope(), "artifact": "mbp1_front_contract_series",
           "status": "PASS",
           "rule": "strictly CAUSAL front/roll rule (decided from the prior "
                   "completed session only)",
           "switches": switches, "n_switches": len(switches),
           "per_session": []}
    p = data_root / "qa" / "m0_closeout" / "mbp1_front_contract_series.json"
    p.write_text(json.dumps(doc, indent=2))
    return p


def _full_corpus_proposal(data_root, per_partition, cal_state):
    from nqresearch.qa.closeout import (
        PROPOSED_DEV_END,
        PROPOSED_DEV_START,
        PROPOSED_HOLDOUT_END,
        PROPOSED_HOLDOUT_START,
        PROPOSED_SELECTION_END,
        PROPOSED_SELECTION_START,
    )

    close = data_root / "qa" / "m0_closeout"
    sha = {
        "coverage_artifact_sha256": hashlib.sha256(
            (close / "mbp1_full_history_coverage.json").read_bytes()
        ).hexdigest(),
        "mbo_blocks_sha256": hashlib.sha256(
            (close / "mbo_blocks_frozen.json").read_bytes()).hexdigest(),
        "front_contract_series_sha256": hashlib.sha256(
            (close / "mbp1_front_contract_series.json").read_bytes()
        ).hexdigest(),
    }
    doc = {
        **clean_envelope(),
        "artifact": "partition_proposal",
        # The neutral proposal is NEVER relabelled: the activation candidate
        # is a separate artifact with its own identity.
        "state": "PROPOSED_NOT_ACTIVE",
        "activation_ready": False,
        "calendar_verification_state": cal_state,
        "research_eligibility_binding": {"structural_artifact_sha256": sha},
        "proposal": {
            "DEV": {"start": PROPOSED_DEV_START.isoformat(),
                    "end": PROPOSED_DEV_END.isoformat(), "trading_days": 318},
            "SELECTION": {"start": PROPOSED_SELECTION_START.isoformat(),
                          "end": PROPOSED_SELECTION_END.isoformat(),
                          "trading_days": 100},
            "HOLDOUT": {"start": PROPOSED_HOLDOUT_START.isoformat(),
                        "end": PROPOSED_HOLDOUT_END.isoformat(),
                        "tentative": True, "trading_days": 98},
            "FORWARD": {"start": "2026-08-17", "note": "synthetic"},
        },
        "mbo_sessions_per_partition": {"DEV": 23, "SELECTION": 23,
                                       "HOLDOUT": 31},
        "mbo_blocks_per_partition": per_partition,
        "checks": [{"check": c, "status": "PASS", "detail": "synthetic"}
                   for c in MANDATORY_PROPOSAL_CHECKS],
        "status": "PASS",
    }
    p = close / "partition_proposal.json"
    p.write_text(json.dumps(doc, indent=2))
    return p


def full_corpus_tree(tmp_path):
    """Build a COMPLETE synthetic repo + data root whose evidence satisfies
    every frozen activation invariant under the PA-0002 quarantine
    disposition. Returns ``(repo_root, data_root)``."""
    import shutil

    from nqresearch.calendar import clear_calendar_cache
    from nqresearch.calendar_evidence import (
        CALENDAR_EVIDENCE_PENDING_STATE,
        CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
        STATE_PENDING,
    )
    from nqresearch.config import _repo_root
    from nqresearch.eligibility import POLICY_STATE_APPROVED
    from nqresearch.holdout import EXPECTED_BASELINE_GROUPS

    root = tmp_path / "synthrepo"
    (root / "config" / "data").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    shutil.copy(_repo_root() / "config" / "data" / "cme_calendar.yaml",
                root / "config" / "data" / "cme_calendar.yaml")
    data_root = tmp_path / "dataroot"

    matrix_doc, _ = synthetic_matrix_doc(
        data_root / "reference" / "cme_calendar",
        date_states={d: STATE_PENDING for d in QUARANTINED_DATES},
        session_present={d: False for d in UNOBSERVED_QUARANTINED_DATES},
    )
    _full_corpus_coverage(data_root, matrix_doc)
    _, per_partition = _full_corpus_blocks(data_root)
    _full_corpus_front_series(data_root)
    _full_corpus_proposal(data_root, per_partition,
                          CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED)

    matrix_sha = write_matrix(root, matrix_doc)
    write_eligibility_policy(
        root, matrix_sha,
        doc=eligibility_policy_doc(matrix_sha, QUARANTINED_DATES,
                                   status=POLICY_STATE_APPROVED))
    (root / "config" / "data" / "cme_calendar_overrides.yaml").write_text(
        yaml.safe_dump({
            "meta": {"baseline_verification": {
                # Truthful: document verification really is still pending;
                # quarantine never relabels the calendar as verified.
                "status": CALENDAR_EVIDENCE_PENDING_STATE,
                "groups": overrides_groups_for(matrix_doc,
                                               EXPECTED_BASELINE_GROUPS)}},
            "early_close_overrides": {"2025-01-09": "08:30"},
        }, sort_keys=False))
    (root / "docs" / "implementation-audit-log.md").write_text(
        "# Implementation audit log\n", encoding="utf-8")
    clear_calendar_cache()
    return root, data_root
