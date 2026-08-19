"""Date-level CME calendar evidence model (PA-0001): adversarial validation
tests over synthetic matrices, plus verification of the REAL committed matrix
against the real immutable evidence files and coverage artifact."""

import pytest
import yaml

import conftest as fx
from nqresearch.calendar_evidence import (
    CALENDAR_EVIDENCE_COMPLETE_STATE,
    CALENDAR_EVIDENCE_PENDING_STATE,
    EXPECTED_EXCEPTIONAL_DATES,
    STATE_CONFLICT,
    STATE_DOCUMENT_VERIFIED,
    STATE_PENDING,
    STATE_TRIANGULATED,
    CalendarEvidenceError,
    EvidenceMatrix,
    current_calendar_verification_state,
    evidence_complete,
    group_states,
    load_matrix,
    load_validated_matrix,
    unresolved_dates,
    validate_matrix,
    verify_observed_against_coverage,
)


def _build(tmp_path, **kw):
    evid = tmp_path / "reference" / "cme_calendar"
    doc, shas = fx.synthetic_matrix_doc(evid, **kw)
    return doc, evid, shas


def _validate(doc, evid):
    validate_matrix(EvidenceMatrix(**doc), evid)


class TestSyntheticMatrixValidation:
    def test_fully_verified_matrix_validates_and_is_complete(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        m = EvidenceMatrix(**doc)
        validate_matrix(m, evid)
        assert evidence_complete(m)
        assert unresolved_dates(m) == {}

    def test_missing_email_file_fails(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        (evid / "email.eml").unlink()
        with pytest.raises(CalendarEvidenceError, match="missing"):
            _validate(doc, evid)

    def test_changed_email_bytes_fail(self, tmp_path):
        # Missing or CHANGED CME email evidence fails.
        doc, evid, _ = _build(tmp_path)
        (evid / "email.eml").write_bytes(b"forged reply")
        with pytest.raises(CalendarEvidenceError, match="hash mismatch"):
            _validate(doc, evid)

    def test_fabricated_document_hash_fails(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        doc["sources"][0]["files"][0]["sha256"] = "0" * 64
        with pytest.raises(CalendarEvidenceError, match="hash mismatch"):
            _validate(doc, evid)

    def test_non_cme_sender_domain_fails(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        doc["archive_unavailability"]["sender_domain"] = "example.com"
        with pytest.raises(CalendarEvidenceError, match="cmegroup.com"):
            _validate(doc, evid)

    def test_unknown_state_fails(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        doc["dates"][0]["state"] = "TOTALLY_VERIFIED_TRUST_ME"
        with pytest.raises(Exception, match="unknown evidence state"):
            _validate(doc, evid)

    def test_missing_or_extra_or_renamed_dates_fail(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        removed = doc["dates"].pop(0)
        with pytest.raises(CalendarEvidenceError, match="exactly the frozen"):
            _validate(doc, evid)
        doc["dates"].insert(0, removed)
        doc["dates"][0] = {**removed, "holiday_group": "Renamed Group"}
        with pytest.raises(CalendarEvidenceError, match="bound to group"):
            _validate(doc, evid)


class TestTierGating:
    def _set_state(self, doc, iso, state, evidence):
        for d in doc["dates"]:
            if d["date"] == iso:
                d["state"] = state
                d["evidence"] = evidence
                return d
        raise AssertionError(iso)

    def test_email_never_proves_historical_times(self, tmp_path):
        # The GCC email as the ONLY corroboration cannot triangulate.
        doc, evid, _ = _build(tmp_path)
        self._set_state(doc, "2025-06-19", STATE_TRIANGULATED, [
            {"source": "syn-email", "claim_id": "archive-unavailable",
             "kind": "DIRECT"},
        ])
        with pytest.raises(CalendarEvidenceError,
                           match="qualifying independent secondary"):
            _validate(doc, evid)

    def test_email_never_supports_document_verified(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        self._set_state(doc, "2025-06-19", STATE_DOCUMENT_VERIFIED, [
            {"source": "syn-email", "claim_id": "archive-unavailable",
             "kind": "DIRECT"},
        ])
        with pytest.raises(CalendarEvidenceError, match="official CME"):
            _validate(doc, evid)

    def test_kibot_only_date_cannot_triangulate(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        self._set_state(doc, "2025-06-19", STATE_TRIANGULATED, [
            {"source": "syn-email", "claim_id": "archive-unavailable",
             "kind": "DIRECT"},
            {"source": "syn-kibot", "claim_id": "holiday-dates",
             "kind": "DATE_ONLY"},
        ])
        with pytest.raises(CalendarEvidenceError,
                           match="qualifying independent secondary"):
            _validate(doc, evid)

    def test_lower_tier_only_date_cannot_triangulate(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        self._set_state(doc, "2025-06-19", STATE_TRIANGULATED, [
            {"source": "syn-email", "claim_id": "archive-unavailable",
             "kind": "DIRECT"},
            {"source": "syn-lower", "claim_id": "lower-row",
             "kind": "DIRECT"},
        ])
        with pytest.raises(CalendarEvidenceError,
                           match="qualifying independent secondary"):
            _validate(doc, evid)

    def test_tertiary_source_may_not_carry_schedule_claims(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        for d in doc["dates"]:
            if d["date"] == "2025-06-19":
                d["evidence"].append({"source": "syn-kibot",
                                      "claim_id": "holiday-dates",
                                      "kind": "DIRECT"})
        with pytest.raises(CalendarEvidenceError, match="date-only source"):
            _validate(doc, evid)

    def test_invented_claim_id_on_valid_source_fails(self, tmp_path):
        # A date-level reference must bind to a claim its source actually
        # declares — an invented claim id on an otherwise valid source fails.
        doc, evid, _ = _build(tmp_path)
        for d in doc["dates"]:
            if d["date"] == "2025-06-19":
                d["evidence"].append({"source": "syn-official",
                                      "claim_id": "invented-claim",
                                      "kind": "DIRECT"})
        with pytest.raises(CalendarEvidenceError, match="does not declare"):
            _validate(doc, evid)

    def test_renamed_source_claim_breaks_references(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        for s in doc["sources"]:
            if s["id"] == "syn-official":
                s["claims"][0]["id"] = "renamed-claim"
        with pytest.raises(CalendarEvidenceError, match="does not declare"):
            _validate(doc, evid)

    def test_duplicate_claim_ids_within_source_fail(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        for s in doc["sources"]:
            if s["id"] == "syn-official":
                s["claims"].append(dict(s["claims"][0]))
        with pytest.raises(Exception, match="duplicate claim ids"):
            _validate(doc, evid)

    def test_missing_observed_data_blocks_triangulation(self, tmp_path):
        doc, evid, _ = _build(tmp_path,
                              date_states={"2025-04-18": STATE_TRIANGULATED},
                              observed_available={"2025-04-18": False})
        with pytest.raises(CalendarEvidenceError,
                           match="observed canonical"):
            _validate(doc, evid)

    def test_triangulation_without_email_citation_fails(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        self._set_state(doc, "2025-06-19", STATE_TRIANGULATED, [
            {"source": "syn-strong", "claim_id": "secondary-schedule",
             "kind": "DIRECT"},
        ])
        with pytest.raises(CalendarEvidenceError,
                           match="archive-unavailability"):
            _validate(doc, evid)

    def test_out_of_scope_citation_fails(self, tmp_path):
        # A 2026-scoped source can never support a 2024/2025 date.
        doc, evid, _ = _build(tmp_path)
        for s in doc["sources"]:
            if s["id"] == "syn-official":
                s["applicable_dates"] = [d for d in s["applicable_dates"]
                                         if d.startswith("2026")]
        with pytest.raises(CalendarEvidenceError,
                           match="outside its declared applicable"):
            _validate(doc, evid)


class TestPathContainment:
    """Declared evidence paths must stay strictly inside their roots — a
    matching SHA-256 can NEVER make an out-of-root file acceptable."""

    def _declare_official_file(self, doc, declared, sha):
        for s in doc["sources"]:
            if s["id"] == "syn-official":
                s["files"] = [{"file": declared, "sha256": sha}]
                return
        raise AssertionError("syn-official missing")

    def test_dotdot_traversal_fails_even_with_matching_hash(self, tmp_path):
        import hashlib

        doc, evid, _ = _build(tmp_path)
        content = b"official doc"
        outside = evid.parent / "outside.bin"  # exists, hash matches
        outside.write_bytes(content)
        self._declare_official_file(
            doc, "../outside.bin", hashlib.sha256(content).hexdigest())
        with pytest.raises(CalendarEvidenceError, match="containment"):
            _validate(doc, evid)

    @pytest.mark.parametrize("declared", [
        "C:evil.bin",                    # drive-relative
        "C:\\evil\\evil.bin",            # drive-qualified absolute
        "\\evil.bin",                    # root-relative
        "/evil.bin",                     # root-relative (posix form)
        "\\\\server\\share\\evil.bin",   # UNC
    ])
    def test_absolute_drive_root_unc_paths_fail(self, tmp_path, declared):
        doc, evid, _ = _build(tmp_path)
        self._declare_official_file(doc, declared, "0" * 64)
        with pytest.raises(CalendarEvidenceError, match="containment"):
            _validate(doc, evid)

    def test_explicit_absolute_path_fails(self, tmp_path):
        import hashlib

        doc, evid, _ = _build(tmp_path)
        content = b"official doc"
        outside = tmp_path / "abs-outside.bin"
        outside.write_bytes(content)
        self._declare_official_file(
            doc, str(outside), hashlib.sha256(content).hexdigest())
        with pytest.raises(CalendarEvidenceError, match="containment"):
            _validate(doc, evid)

    def test_symlink_escape_fails_where_platform_permits(self, tmp_path):
        import hashlib
        import os

        doc, evid, _ = _build(tmp_path)
        content = b"official doc"
        outside_dir = tmp_path / "escape-target"
        outside_dir.mkdir()
        (outside_dir / "f.bin").write_bytes(content)
        link = evid / "link"
        try:
            os.symlink(outside_dir, link, target_is_directory=True)
        except OSError:
            # Windows: unprivileged symlinks may be refused; junctions are
            # not — they exercise the same alias-escape resolution.
            import subprocess

            r = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside_dir)],
                capture_output=True)
            if r.returncode != 0 or not link.exists():
                pytest.skip("platform permits neither symlinks nor junctions")
        self._declare_official_file(
            doc, "link/f.bin", hashlib.sha256(content).hexdigest())
        with pytest.raises(CalendarEvidenceError, match="containment"):
            _validate(doc, evid)

    def test_prefix_collision_is_not_containment(self):
        # Pure containment semantics: …/root2 is never inside …/root.
        from pathlib import Path

        from nqresearch.rawguard import _is_within

        assert not _is_within(Path("X:/data/root2/f.bin"),
                              Path("X:/data/root"))
        assert _is_within(Path("X:/data/root/sub/f.bin"),
                          Path("X:/data/root"))

    def test_valid_nested_evidence_path_works(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        sha = fx.write_evidence_file(evid / "secondary", "file.html",
                                     b"nested ok")
        self._declare_official_file(doc, "secondary/file.html", sha)
        _validate(doc, evid)  # must not raise

    def _env_for_load(self, tmp_path):
        import shutil

        from nqresearch.config import _repo_root

        repo = tmp_path / "repo"
        (repo / "config" / "data").mkdir(parents=True)
        shutil.copy(_repo_root() / "config" / "data" / "cme_calendar.yaml",
                    repo / "config" / "data" / "cme_calendar.yaml")
        data_root = tmp_path / "dataroot"
        doc, _, _ = _build(data_root)
        fx.write_coverage_for(data_root, doc)
        return repo, data_root, doc

    def test_escaped_evidence_root_fails(self, tmp_path):
        doc_env = self._env_for_load(tmp_path)
        repo, data_root, doc = doc_env
        (tmp_path / "elsewhere").mkdir()
        doc["meta"]["evidence_root"] = "../elsewhere"
        fx.write_matrix(repo, doc)
        with pytest.raises(CalendarEvidenceError, match="containment"):
            load_validated_matrix(repo, data_root)

    def test_escaped_coverage_artifact_fails(self, tmp_path):
        repo, data_root, doc = self._env_for_load(tmp_path)
        doc["meta"]["observed_reference"]["artifact"] = (
            "../outside-coverage.json")
        fx.write_matrix(repo, doc)
        with pytest.raises(CalendarEvidenceError, match="containment"):
            load_validated_matrix(repo, data_root)

    def test_coverage_artifact_outside_qa_fails(self, tmp_path):
        import shutil

        repo, data_root, doc = self._env_for_load(tmp_path)
        cov = (data_root / "qa" / "m0_closeout"
               / "mbp1_full_history_coverage.json")
        moved = data_root / "reference" / "cov.json"
        shutil.copy(cov, moved)
        doc["meta"]["observed_reference"]["artifact"] = "reference/cov.json"
        fx.write_matrix(repo, doc)
        with pytest.raises(CalendarEvidenceError, match="qa"):
            load_validated_matrix(repo, data_root)


class TestConflictsAndRollups:
    def test_discrepancy_requires_conflict_state(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        doc["dates"][0]["agreement"] = "DISCREPANCY"
        with pytest.raises(CalendarEvidenceError, match="discrepancy"):
            _validate(doc, evid)

    def test_conflict_state_blocks_completeness(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        doc["dates"][0]["state"] = STATE_CONFLICT
        doc["dates"][0]["agreement"] = "DISCREPANCY"
        m = EvidenceMatrix(**doc)
        validate_matrix(m, evid)
        assert not evidence_complete(m)
        assert unresolved_dates(m) == {doc["dates"][0]["date"]: STATE_CONFLICT}

    def test_one_verified_year_never_promotes_group(self, tmp_path):
        # Labor Day: 2025-09-01 verified, 2024-09-02 pending → group pending.
        doc, _, _ = _build(tmp_path,
                           date_states={"2024-09-02": STATE_PENDING})
        m = EvidenceMatrix(**doc)
        rollup = group_states(m)
        assert rollup["Labor Day (2024-09-02, 2025-09-01)"] == STATE_PENDING

    def test_conflict_is_weakest_in_rollup(self, tmp_path):
        doc, _, _ = _build(tmp_path)
        for d in doc["dates"]:
            if d["date"] == "2024-09-02":
                d["state"] = STATE_CONFLICT
                d["agreement"] = "DISCREPANCY"
        m = EvidenceMatrix(**doc)
        assert group_states(m)[
            "Labor Day (2024-09-02, 2025-09-01)"] == STATE_CONFLICT


class TestObservedCrossCheck:
    def _cov_path(self, data_root):
        return (data_root / "qa" / "m0_closeout"
                / "mbp1_full_history_coverage.json")

    def test_fabricated_observed_span_fails(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        data_root = tmp_path / "dataroot"
        fx.write_coverage_for(data_root, doc)
        doc["dates"][0]["observed"]["rth_span_seconds"] = 99999.0
        with pytest.raises(CalendarEvidenceError, match="span mismatch"):
            verify_observed_against_coverage(
                EvidenceMatrix(**doc), self._cov_path(data_root))

    def test_claimed_session_absent_from_coverage_fails(self, tmp_path):
        doc, evid, _ = _build(tmp_path,
                              session_present={"2024-09-02": False})
        data_root = tmp_path / "dataroot"
        fx.write_coverage_for(data_root, doc)
        for d in doc["dates"]:
            if d["date"] == "2024-09-02":
                d["observed"]["session_present"] = True
                d["observed"]["rth_span_seconds"] = 12600.0
        with pytest.raises(CalendarEvidenceError, match="has none"):
            verify_observed_against_coverage(
                EvidenceMatrix(**doc), self._cov_path(data_root))

    def test_substantive_coverage_change_fails_digest_check(self, tmp_path):
        # A substantive change invalidates the substance digest, and that is
        # detected BEFORE any per-date comparison could succeed.
        import json

        doc, evid, _ = _build(tmp_path)
        data_root = tmp_path / "dataroot"
        p = fx.write_coverage_for(data_root, doc)
        cov = json.loads(p.read_text())
        cov["extra_note"] = "materially different coverage result"
        p.write_text(json.dumps(cov))
        with pytest.raises(CalendarEvidenceError,
                           match="SUBSTANCE digest mismatch"):
            verify_observed_against_coverage(
                EvidenceMatrix(**doc), self._cov_path(data_root))

    def test_envelope_only_regeneration_still_validates(self, tmp_path):
        # THE circularity fix: regenerating coverage with a new commit,
        # config hash and code hash must NOT invalidate the matrix.
        import json

        doc, evid, _ = _build(tmp_path)
        data_root = tmp_path / "dataroot"
        p = fx.write_coverage_for(data_root, doc)
        cov = json.loads(p.read_text())
        cov.update({"git_sha": "b" * 40, "config_hash": "c" * 64,
                    "audit_code_hash": "d" * 64,
                    "generated_at_utc": "2099-01-01T00:00:00Z",
                    "generation_git_clean": True,
                    "restamp_note": "regenerated", "data_root": "X:\\other",
                    "nqresearch_version": "9.9.9"})
        p.write_text(json.dumps(cov, indent=4))   # also different formatting
        verify_observed_against_coverage(
            EvidenceMatrix(**doc), self._cov_path(data_root))  # must not raise

    @pytest.mark.parametrize("bad", [None, "nothex", "ab" * 16, 5, ""])
    def test_missing_or_invalid_substance_digest_fails(self, tmp_path, bad):
        doc, evid, _ = _build(tmp_path)
        data_root = tmp_path / "dataroot"
        fx.write_coverage_for(data_root, doc)
        doc["meta"]["observed_reference"]["substance_sha256"] = bad
        with pytest.raises(CalendarEvidenceError, match="substance_sha256"):
            verify_observed_against_coverage(
                EvidenceMatrix(**doc), self._cov_path(data_root))

    @pytest.mark.parametrize("algo", [None, "", "coverage-substance-v0",
                                      "sha256", 1])
    def test_missing_or_unknown_digest_algorithm_fails(self, tmp_path, algo):
        doc, evid, _ = _build(tmp_path)
        data_root = tmp_path / "dataroot"
        fx.write_coverage_for(data_root, doc)
        doc["meta"]["observed_reference"]["substance_digest_algorithm"] = algo
        with pytest.raises(CalendarEvidenceError,
                           match="substance_digest_algorithm"):
            verify_observed_against_coverage(
                EvidenceMatrix(**doc), self._cov_path(data_root))

    def test_matching_digest_but_wrong_per_date_observation_still_fails(
            self, tmp_path):
        # A valid digest must not buy trust in the per-date claims: they are
        # still checked individually.
        doc, evid, _ = _build(tmp_path)
        data_root = tmp_path / "dataroot"
        fx.write_coverage_for(data_root, doc)
        # digest was computed from the artifact; now corrupt only the MATRIX
        doc["dates"][0]["observed"]["rth_span_seconds"] = 4242.0
        with pytest.raises(CalendarEvidenceError, match="span mismatch"):
            verify_observed_against_coverage(
                EvidenceMatrix(**doc), self._cov_path(data_root))


class TestCoverageSubstanceDigest:
    """coverage-substance-v1: deterministic, envelope-independent, and
    sensitive to every substantive field."""

    def _doc(self):
        return {
            "artifact": "mbp1_full_history_coverage", "status": "WARN",
            "generated_at_utc": "2026-08-19T00:00:00Z",
            "nqresearch_version": "0.1.0", "git_sha": "a" * 40,
            "generation_git_clean": True, "restamp_note": "note",
            "audit_code_hash": "b" * 64, "config_hash": "c" * 64,
            "data_root": "D:\\nq-research\\data",
            "n_expected_complete_sessions": 516, "n_fail": 0, "n_warn": 8,
            "missing_sessions": [], "cross_file_order_violations": 0,
            "missing_pre_rth_short_sessions": ["2025-04-18"],
            "checks": [{"check": "no_session_fails", "status": "PASS"}],
            "sessions": [
                {"session_id": "2024-08-19", "rth_span_seconds": 23400.0,
                 "expected_rth_span_seconds": 23400,
                 "calendar_status": "normal", "qa_status": "PASS"},
                {"session_id": "2024-08-20", "rth_span_seconds": 23400.0,
                 "expected_rth_span_seconds": 23400,
                 "calendar_status": "normal", "qa_status": "PASS"},
            ],
        }

    @pytest.mark.parametrize("field", [
        "generated_at_utc", "nqresearch_version", "git_sha",
        "generation_git_clean", "restamp_note", "audit_code_hash",
        "config_hash", "data_root",
    ])
    def test_envelope_fields_do_not_change_the_digest(self, field):
        from nqresearch.calendar_evidence import coverage_substance_sha256

        base = self._doc()
        before = coverage_substance_sha256(base)
        mutated = dict(base)
        mutated[field] = "ZZZ-changed" if field != "generation_git_clean" \
            else False
        assert coverage_substance_sha256(mutated) == before

    def test_json_formatting_and_key_order_do_not_change_the_digest(self):
        import json

        from nqresearch.calendar_evidence import coverage_substance_sha256

        base = self._doc()
        before = coverage_substance_sha256(base)
        reordered = dict(reversed(list(base.items())))
        assert coverage_substance_sha256(reordered) == before
        round_tripped = json.loads(json.dumps(base, indent=7))
        assert coverage_substance_sha256(round_tripped) == before

    @pytest.mark.parametrize("field,value", [
        ("artifact", "something_else"),
        ("status", "PASS"),
        ("n_expected_complete_sessions", 515),
        ("n_fail", 1),
        ("n_warn", 9),
        ("missing_sessions", ["2025-05-05"]),
        ("cross_file_order_violations", 1),
        ("missing_pre_rth_short_sessions", ["2099-12-31"]),
        ("checks", [{"check": "other", "status": "WARN"}]),
    ])
    def test_substantive_fields_change_the_digest(self, field, value):
        from nqresearch.calendar_evidence import coverage_substance_sha256

        base = self._doc()
        mutated = dict(base)
        mutated[field] = value
        assert coverage_substance_sha256(mutated) != \
            coverage_substance_sha256(base)

    @pytest.mark.parametrize("key,value", [
        ("session_id", "2099-01-01"),
        ("rth_span_seconds", 12600.0),
        ("expected_rth_span_seconds", 12600),
        ("calendar_status", "shortened"),
        ("qa_status", "WARN"),
    ])
    def test_session_level_changes_change_the_digest(self, key, value):
        from nqresearch.calendar_evidence import coverage_substance_sha256

        base = self._doc()
        before = coverage_substance_sha256(base)
        mutated = self._doc()
        mutated["sessions"][0][key] = value
        assert coverage_substance_sha256(mutated) != before

    def test_adding_or_removing_a_session_changes_the_digest(self):
        from nqresearch.calendar_evidence import coverage_substance_sha256

        base = self._doc()
        before = coverage_substance_sha256(base)
        added = self._doc()
        added["sessions"].append({"session_id": "2024-08-21",
                                  "rth_span_seconds": 23400.0})
        removed = self._doc()
        removed["sessions"].pop()
        assert coverage_substance_sha256(added) != before
        assert coverage_substance_sha256(removed) != before

    def test_embedded_self_digest_is_excluded(self):
        from nqresearch.calendar_evidence import coverage_substance_sha256

        base = self._doc()
        before = coverage_substance_sha256(base)
        with_self = dict(base)
        with_self["coverage_substance_sha256"] = before
        assert coverage_substance_sha256(with_self) == before

    @pytest.mark.parametrize("bad", [None, [], "text", 42, {"": None}])
    def test_malformed_documents_rejected(self, bad):
        from nqresearch.calendar_evidence import coverage_substance_sha256

        if isinstance(bad, dict):
            # dict of only-envelope keys is empty after filtering
            bad = {"git_sha": "x", "config_hash": "y"}
        with pytest.raises(CalendarEvidenceError):
            coverage_substance_sha256(bad)

    def test_non_finite_values_rejected(self):
        from nqresearch.calendar_evidence import coverage_substance_sha256

        base = self._doc()
        base["sessions"][0]["rth_span_seconds"] = float("nan")
        with pytest.raises(CalendarEvidenceError,
                           match="not strictly serialisable"):
            coverage_substance_sha256(base)

    def test_algorithm_identifier_is_versioned(self):
        from nqresearch.calendar_evidence import COVERAGE_SUBSTANCE_ALGORITHM

        assert COVERAGE_SUBSTANCE_ALGORITHM == "coverage-substance-v1"

    def test_live_matrix_declares_the_versioned_digest_of_the_live_artifact(
            self):
        import json

        import yaml as _yaml

        from nqresearch import paths
        from nqresearch.calendar_evidence import (
            COVERAGE_SUBSTANCE_ALGORITHM,
            coverage_substance_sha256,
        )
        from nqresearch.config import _repo_root

        m = _yaml.safe_load(
            (_repo_root() / "config" / "data" / "cme_calendar_evidence.yaml")
            .read_text(encoding="utf-8"))
        ref = m["meta"]["observed_reference"]
        assert ref["substance_digest_algorithm"] == COVERAGE_SUBSTANCE_ALGORITHM
        assert "artifact_sha256" not in ref  # live whole-file binding removed
        cov = json.loads(
            (paths.data_root() / "qa" / "m0_closeout"
             / "mbp1_full_history_coverage.json").read_text(encoding="utf-8"))
        assert ref["substance_sha256"] == coverage_substance_sha256(cov)


class TestEmailSubstantiveVerification:
    """The .eml BYTES are parsed; every adversarial mutation below also
    RECOMPUTES the evidence-file hash in the matrix, proving the failure
    comes from parsed-content inconsistency — never from a stale hash."""

    def _mutated(self, tmp_path, match, **eml_overrides):
        doc, evid, _ = _build(tmp_path)
        fx.write_evidence_file(evid, "email.eml",
                               fx.synthetic_eml_bytes(**eml_overrides))
        fx.rehash_source_file(doc, evid, "syn-email", "email.eml")
        with pytest.raises(CalendarEvidenceError, match=match):
            _validate(doc, evid)

    def test_changed_from_mailbox_fails(self, tmp_path):
        self._mutated(tmp_path, "From mailbox",
                      from_addr="GCC <gcc@cmegroup.com.evil.example>")

    def test_changed_subject_fails(self, tmp_path):
        self._mutated(tmp_path, "subject", subject="Totally different")

    def test_changed_date_fails(self, tmp_path):
        self._mutated(tmp_path, "Date",
                      date_hdr="Sat, 02 Jan 2099 00:00:00 +0000")

    def test_changed_message_id_fails(self, tmp_path):
        self._mutated(tmp_path, "Message-ID",
                      message_id="<forged@elsewhere.invalid>")

    def test_missing_cme_dkim_signature_fails(self, tmp_path):
        self._mutated(tmp_path, "DKIM-Signature",
                      dkim="v=1; a=rsa-sha256; d=attacker.example; b=x")

    @pytest.mark.parametrize("auth,what", [
        ("mx.x; dkim=fail header.i=@cmegroup.com; spf=pass; "
         "dmarc=pass header.from=cmegroup.com", "DKIM pass"),
        ("mx.x; dkim=pass header.i=@cmegroup.com; spf=pass; "
         "dmarc=fail header.from=cmegroup.com", "DMARC pass"),
        ("mx.x; dkim=pass header.i=@cmegroup.com; spf=softfail; "
         "dmarc=pass header.from=cmegroup.com", "SPF pass"),
        # Exact-token binding: suffix/prefix look-alike domains never pass.
        ("mx.x; dkim=pass header.i=@evilcmegroup.com; spf=pass; "
         "dmarc=pass header.from=cmegroup.com", "DKIM pass"),
        ("mx.x; dkim=pass header.i=@cmegroup.com.evil.example; spf=pass; "
         "dmarc=pass header.from=cmegroup.com", "DKIM pass"),
        ("mx.x; dkim=pass header.i=@cmegroup.com; spf=pass; "
         "dmarc=pass header.from=evilcmegroup.com", "DMARC pass"),
        ("mx.x; dkim=pass header.i=@cmegroup.com; spf=pass; "
         "dmarc=pass header.from=cmegroup.com.evil.example", "DMARC pass"),
    ])
    def test_bad_authentication_results_fail(self, tmp_path, auth, what):
        self._mutated(tmp_path, what, auth_results=auth)

    def test_changed_body_statement_fails(self, tmp_path):
        self._mutated(
            tmp_path, "statement",
            body=("We can absolutely send you every archive you want.\n"
                  + fx.SYN_EMAIL_FIELDS["referral_url"] + "\n"))

    def test_missing_referral_url_fails(self, tmp_path):
        self._mutated(
            tmp_path, "referral",
            body=fx.SYN_EMAIL_FIELDS["body_statement"] + "\nno link here\n")

    def test_non_eml_suffix_fails(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        fx.write_evidence_file(evid, "email.msg", fx.synthetic_eml_bytes())
        for s in doc["sources"]:
            if s["id"] == "syn-email":
                s["files"] = [{"file": "email.msg",
                               "sha256": __import__("hashlib").sha256(
                                   (evid / "email.msg").read_bytes()
                               ).hexdigest()}]
        with pytest.raises(CalendarEvidenceError, match="eml suffix"):
            _validate(doc, evid)

    def test_multiple_files_on_email_source_fail(self, tmp_path):
        doc, evid, _ = _build(tmp_path)
        for s in doc["sources"]:
            if s["id"] == "syn-email":
                s["files"] = s["files"] + [
                    {"file": "strong.html",
                     "sha256": __import__("hashlib").sha256(
                         (evid / "strong.html").read_bytes()).hexdigest()}]
        with pytest.raises(CalendarEvidenceError, match="exactly one"):
            _validate(doc, evid)


class TestVerificationState:
    def test_state_pending_when_incomplete_and_complete_when_resolved(
            self, tmp_path):
        import shutil

        from nqresearch.config import _repo_root

        repo = tmp_path / "repo"
        (repo / "config" / "data").mkdir(parents=True)
        shutil.copy(_repo_root() / "config" / "data" / "cme_calendar.yaml",
                    repo / "config" / "data" / "cme_calendar.yaml")
        data_root = tmp_path / "dataroot"
        doc, _, _ = _build(data_root)
        fx.write_coverage_for(data_root, doc)  # binds artifact sha into doc
        fx.write_matrix(repo, doc)
        assert current_calendar_verification_state(
            repo, data_root) == CALENDAR_EVIDENCE_COMPLETE_STATE
        doc["dates"][0]["state"] = STATE_PENDING
        fx.write_matrix(repo, doc)
        assert current_calendar_verification_state(
            repo, data_root) == CALENDAR_EVIDENCE_PENDING_STATE

    def test_state_never_complete_on_validation_failure(self, tmp_path):
        # Fail-safe direction: any validation error yields the pending state.
        assert current_calendar_verification_state(
            tmp_path, tmp_path) == CALENDAR_EVIDENCE_PENDING_STATE


class TestRealCommittedMatrix:
    """The REAL committed matrix must validate against the REAL immutable
    evidence directory and coverage artifact, and must currently be
    INCOMPLETE (10 pending dates) with activation impossible."""

    def _real(self):
        from nqresearch import paths
        from nqresearch.config import _repo_root

        repo_root = _repo_root()
        data_root = paths.data_root()
        if not (data_root / "reference" / "cme_calendar").is_dir():
            pytest.skip("live evidence directory not available")
        return repo_root, data_root

    def test_real_matrix_validates_and_is_incomplete(self):
        repo_root, data_root = self._real()
        m = load_validated_matrix(repo_root, data_root)
        assert not evidence_complete(m)
        unresolved = unresolved_dates(m)
        assert unresolved == {
            "2024-09-02": STATE_PENDING, "2024-11-29": STATE_PENDING,
            "2025-01-01": STATE_PENDING, "2025-01-20": STATE_PENDING,
            "2025-02-17": STATE_PENDING, "2025-04-18": STATE_PENDING,
            "2025-05-26": STATE_PENDING, "2025-06-19": STATE_PENDING,
            "2025-07-03": STATE_PENDING, "2025-07-04": STATE_PENDING,
        }
        # No conflicts anywhere.
        assert all(d.state != STATE_CONFLICT for d in m.dates)

    def test_real_resolved_states(self):
        repo_root, data_root = self._real()
        m = load_validated_matrix(repo_root, data_root)
        states = {d.date.isoformat(): d.state for d in m.dates}
        assert states["2025-01-09"] == STATE_DOCUMENT_VERIFIED
        for iso in ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
                    "2026-05-25", "2026-06-19", "2026-07-03"]:
            assert states[iso] == STATE_DOCUMENT_VERIFIED, iso
        for iso in ["2024-11-28", "2024-12-24", "2024-12-25", "2025-09-01",
                    "2025-11-27", "2025-11-28", "2025-12-24", "2025-12-25"]:
            assert states[iso] == STATE_TRIANGULATED, iso

    def test_real_overrides_agree_with_matrix_rollups(self):
        repo_root, data_root = self._real()
        m = load_validated_matrix(repo_root, data_root)
        rollups = group_states(m)
        ov = yaml.safe_load(
            (repo_root / "config" / "data" / "cme_calendar_overrides.yaml")
            .read_text(encoding="utf-8"))
        bv = ov["meta"]["baseline_verification"]
        assert bv["status"] == CALENDAR_EVIDENCE_PENDING_STATE
        date_states = {d.date.isoformat(): d.state for d in m.dates}
        for g in bv["groups"]:
            assert g["status"] == rollups[g["holiday_group"]], g
            for iso, st in g["dates"].items():
                assert date_states[str(iso)] == st, (g, iso)
        special = {g["holiday_group"]: g for g in bv["special_closures"]}
        assert special["National Day of Mourning (2025-01-09)"][
            "status"] == STATE_DOCUMENT_VERIFIED

    def test_real_jan9_reference_hash_matches_pdf_evidence(self):
        repo_root, data_root = self._real()
        m = load_matrix(repo_root)
        pdf_sha = {s.id: s for s in m.sources}[
            "cme-mourning-2025-pdf"].files[0].sha256
        ov = yaml.safe_load(
            (repo_root / "config" / "data" / "cme_calendar_overrides.yaml")
            .read_text(encoding="utf-8"))
        ref = {r["id"]: r for r in ov["meta"]["references"]}[
            "cme-2025-01-09-mourning"]
        assert ref["document_sha256"] == pdf_sha
        assert ref["document_sha256_status"] == "VERIFIED_MANUAL_RETRIEVAL"

    def test_real_activation_still_impossible(self):
        # End-to-end: with the real repo + real data volume the public loader
        # still fails closed (partitions file absent; evidence incomplete).
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            load_active_partitions,
        )

        with pytest.raises(PartitionsNotActiveError):
            load_active_partitions()

    def test_group_name_consistency_with_holdout_frozen_plan(self):
        from nqresearch.holdout import EXPECTED_BASELINE_GROUPS

        matrix_groups = set(EXPECTED_EXCEPTIONAL_DATES.values())
        assert matrix_groups == (EXPECTED_BASELINE_GROUPS
                                 | {"National Day of Mourning (2025-01-09)"})
