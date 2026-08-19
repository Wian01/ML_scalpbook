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
    """A provenance envelope satisfying the AL-0043/44/45 activation policy:
    clean generation at a REAL ancestral commit of the project repository,
    under the current effective config and package code."""
    import subprocess

    from nqresearch import paths
    from nqresearch.config import effective_config_hash
    from nqresearch.qa.cache import package_source_hash

    sha = subprocess.run(["git", "-C", str(paths.ROOT), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    return {
        "git_sha": sha,
        "generation_git_clean": True,
        "restamp_note": "Generated from a clean committed tree at the "
                        "recorded git_sha.",
        "config_hash": effective_config_hash(),
        "audit_code_hash": package_source_hash(),
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
