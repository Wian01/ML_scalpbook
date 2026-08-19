import json
from datetime import date

import pytest

from nqresearch.qa.closeout import freeze_mbo_blocks, propose_partitions
from nqresearch.qa.status import PASS


def _deep_artifact(tmp_path, full, partial):
    p = tmp_path / "mbo_deep_audit.json"
    p.write_text(json.dumps({
        "full_rth_sessions": full,
        "partial_rth_sessions": partial,
    }))
    return p


class TestFreezeBlocks:
    def test_shortened_session_reclassified_complete(self, tmp_path):
        # 2026-07-03 half-day: observed span 0.5385 * 6.5h = 3.5h == expected.
        p = _deep_artifact(
            tmp_path,
            ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-06"],
            [{"session_id": "2026-07-03", "nq_outright_rth_rows": 1_015_860,
              "rth_span_coverage": 0.5385}],
        )
        r = freeze_mbo_blocks(p)
        rec = r["reclassifications"][0]
        assert rec["classification"] == "COMPLETE_SHORTENED_SESSION"
        # With 07-03 complete, 06-29..07-06 is ONE block (07-04 Sat, 07-05 Sun).
        assert r["n_blocks"] == 1
        assert r["blocks"][0]["n_sessions"] == 6
        assert r["status"] == PASS

    def test_holiday_does_not_break_block(self, tmp_path):
        # 2025-12-25 is a full holiday: 12-24 and 12-26 are contiguous.
        p = _deep_artifact(tmp_path, ["2025-12-24", "2025-12-26"], [])
        r = freeze_mbo_blocks(p)
        assert r["n_blocks"] == 1

    def test_genuine_partial_stays_flagged(self, tmp_path):
        p = _deep_artifact(
            tmp_path, ["2025-10-10"],
            [{"session_id": "2025-10-09", "nq_outright_rth_rows": 7_784_649,
              "rth_span_coverage": 0.4513}],
        )
        r = freeze_mbo_blocks(p)
        assert r["reclassifications"][0]["classification"] == "PARTIAL_UNEXPLAINED"
        assert r["status"] == "WARN"

    def test_acquisition_reason_recorded_as_unknown(self, tmp_path):
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        assert "UNKNOWN_NOT_RECORDED" in freeze_mbo_blocks(p)["acquisition_reason"]


class TestPartitionGates:
    def test_spanning_block_fails_proposal(self, tmp_path):
        # Synthetic block spanning SELECTION/HOLDOUT (2026-03-31 + 2026-04-01).
        p = _deep_artifact(tmp_path, ["2026-03-31", "2026-04-01"], [])
        blocks = freeze_mbo_blocks(p)
        prop = propose_partitions(blocks)
        assert prop["status"] == "FAIL"
        gate = [c for c in prop["checks"]
                if c["check"] == "no_partition_spanning_mbo_blocks"][0]
        assert gate["status"] == "FAIL"
        assert prop["mbo_blocks_per_partition"]["SPANNING"]

    def test_partition_ranges_contiguous(self, tmp_path):
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        prop = propose_partitions(freeze_mbo_blocks(p))
        gate = [c for c in prop["checks"]
                if c["check"] == "partition_ranges_contiguous"][0]
        assert gate["status"] == "PASS"

    def test_real_corpus_counts_regression(self):
        # Real decoded MBO artifact + real effective calendar; skipped when
        # the data volume is unavailable.
        import pytest as _pytest
        from pathlib import Path

        from nqresearch import paths

        deep = paths.qa_m0() / "mbo_deep_audit.json"
        if not deep.is_file():
            _pytest.skip("mbo_deep_audit.json not available on this machine")
        blocks = freeze_mbo_blocks(deep)
        # Bind the live MBO-block artifact identity exactly as the CLI does
        # after writing it; without it the identity binding is incomplete.
        import hashlib as _h
        blocks_artifact = (paths.data_root() / "qa" / "m0_closeout"
                           / "mbo_blocks_frozen.json")
        blocks_sha = (_h.sha256(blocks_artifact.read_bytes()).hexdigest()
                      if blocks_artifact.is_file() else "a" * 64)
        prop = propose_partitions(blocks, mbo_blocks_artifact_sha256=blocks_sha)
        assert blocks["n_sessions_final"] == 77 and blocks["n_blocks"] == 30
        ms, mb = prop["mbo_sessions_per_partition"], prop["mbo_blocks_per_partition"]
        assert prop["proposal"]["DEV"]["trading_days"] == 318
        assert prop["proposal"]["SELECTION"]["trading_days"] == 100
        assert prop["proposal"]["HOLDOUT"]["trading_days"] == 98
        assert (ms["DEV"], len(mb["DEV"])) == (23, 8)
        assert (ms["SELECTION"], len(mb["SELECTION"])) == (23, 11)
        assert (ms["HOLDOUT"], len(mb["HOLDOUT"])) == (31, 11)
        assert mb["SPANNING"] == []
        # The three partition-STRUCTURE checks remain PASS...
        structural = {c["check"]: c["status"] for c in prop["checks"]}
        assert structural == {"boundaries_on_trading_days": "PASS",
                              "partition_ranges_contiguous": "PASS",
                              "no_partition_spanning_mbo_blocks": "PASS"}
        binding_checks = {c["check"]: c["status"]
                          for c in prop["research_eligibility_binding"]["checks"]}
        # ...and the quarantine itself is structurally safe (no violations)...
        assert binding_checks["quarantine_structurally_safe"] == "PASS"
        assert prop["research_eligibility_binding"]["candidate"][
            "quarantine_violations"] == []
        # The top-level verdict reflects the ACTUAL current state of the live
        # input artifacts rather than assuming any particular envelope: when
        # the coverage/front-series inputs are in sync with the current
        # commit/config/code the proposal is PASS; when they are not, it is
        # FAIL and the only recorded problems are envelope/identity
        # staleness — never a structural or quarantine violation.
        problems = prop["research_eligibility_binding"][
            "structural_input_validation_problems"]
        if problems:
            assert binding_checks[
                "structural_artifact_identities_valid"] == "FAIL"
            assert prop["status"] == "FAIL"
            allowed = ("generation_git_clean", "git_sha", "config_hash",
                       "audit_code_hash", "status", "artifact type",
                       "missing key", "missing")
            assert all(any(a in p for a in allowed) for p in problems), problems
        else:
            assert binding_checks[
                "structural_artifact_identities_valid"] == "PASS"
            assert prop["status"] == "PASS"

    def test_activation_ready_false_while_verification_pending(self, tmp_path):
        # The calendar must remain EXPLICITLY PROVISIONAL and never be
        # relabelled DOCUMENT_VERIFIED / evidence-complete. Under PA-0002 a
        # fully-quarantined pending set stamps the provisional quarantined
        # state; either provisional value is acceptable here, and
        # activation_ready must stay false regardless.
        from nqresearch.calendar_evidence import (
            CALENDAR_EVIDENCE_COMPLETE_STATE,
            CALENDAR_EVIDENCE_PENDING_STATE,
            CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
        )

        provisional = {CALENDAR_EVIDENCE_PENDING_STATE,
                       CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED}
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        blocks = freeze_mbo_blocks(p)
        assert blocks["state"] in provisional
        assert blocks["state"] != CALENDAR_EVIDENCE_COMPLETE_STATE
        assert blocks["activation_ready"] is False
        prop = propose_partitions(blocks)
        assert prop["calendar_verification_state"] in provisional
        assert prop["calendar_verification_state"] != "DOCUMENT_VERIFIED"
        assert prop["state"] == "PROPOSED_NOT_ACTIVE"
        assert prop["activation_ready"] is False
        assert len(prop["activation_ready_conditions"]) == 3

    def test_candidate_binding_describes_the_candidate_not_stale_output(
            self, tmp_path):
        # REPRODUCED REVIEW DEFECT: a 1-session synthetic candidate embedded
        # the REAL on-disk 77/30 facts and claimed every check PASS.
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        blocks = freeze_mbo_blocks(p)
        cand = blocks["research_eligibility_binding"]["candidate"]
        assert blocks["n_sessions_final"] == 1
        assert cand["n_candidate_mbo_sessions"] == 1
        assert cand["n_candidate_mbo_blocks"] == blocks["n_blocks"] == 1
        assert cand["n_candidate_mbo_sessions"] != 77
        checks = {c["check"]: c["status"]
                  for c in blocks["research_eligibility_binding"]["checks"]}
        # full structural safety is NOT provable at block stage
        assert checks["quarantine_structurally_safe"] == "WARN"
        assert "DEFERRED" in [
            c["detail"] for c in blocks["research_eligibility_binding"]["checks"]
            if c["check"] == "quarantine_structurally_safe"][0]
        # identities may only PASS because real source bytes were hashed
        src = blocks["research_eligibility_binding"]["source_artifact_sha256"]
        assert src["mbo_deep_audit"] and len(src["mbo_deep_audit"]) == 64
        assert checks["structural_artifact_identities_valid"] == "PASS"

    def test_changed_candidate_block_list_changes_the_binding(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        a = freeze_mbo_blocks(_deep_artifact(tmp_path / "a", ["2026-08-04"], []))
        b = freeze_mbo_blocks(_deep_artifact(
            tmp_path / "b", ["2026-08-04", "2026-08-05", "2026-08-06"], []))
        ca = a["research_eligibility_binding"]["candidate"]
        cb = b["research_eligibility_binding"]["candidate"]
        assert ca["n_candidate_mbo_sessions"] == 1
        assert cb["n_candidate_mbo_sessions"] == 3
        assert ca != cb

    def test_proposal_binding_uses_candidate_blocks_not_stale_proposal(
            self, tmp_path):
        blocks = freeze_mbo_blocks(_deep_artifact(tmp_path, ["2026-08-04"], []))
        prop = propose_partitions(blocks, mbo_blocks_artifact_sha256="a" * 64)
        cand = prop["research_eligibility_binding"]["candidate"]
        # candidate facts come from the blocks passed in, not the real
        # on-disk 77/30 proposal
        assert cand["n_candidate_mbo_sessions"] == 1
        assert cand["n_candidate_mbo_blocks"] == 1
        ident = prop["research_eligibility_binding"]["structural_artifact_sha256"]
        assert ident["mbo_blocks_sha256"] == "a" * 64

    def test_proposal_without_block_hash_marks_identities_failed(self,
                                                                 tmp_path):
        blocks = freeze_mbo_blocks(_deep_artifact(tmp_path, ["2026-08-04"], []))
        prop = propose_partitions(blocks)  # no artifact hash supplied
        checks = {c["check"]: c["status"]
                  for c in prop["research_eligibility_binding"]["checks"]}
        assert checks["structural_artifact_identities_valid"] == "FAIL"

    def test_real_candidate_reproduces_the_frozen_corpus_facts(self):
        # The REAL deep-audit input must still yield 77 sessions / 30 blocks,
        # zero spanning and eight rolls through the candidate-aware path.
        import json as _json

        from nqresearch import paths

        deep = paths.qa_m0() / "mbo_deep_audit.json"
        if not deep.is_file():
            pytest.skip("live MBO deep-audit artifact not available")
        blocks = freeze_mbo_blocks(deep)
        assert blocks["n_sessions_final"] == 77
        assert blocks["n_blocks"] == 30
        cand = blocks["research_eligibility_binding"]["candidate"]
        assert cand["n_candidate_mbo_sessions"] == 77
        assert cand["n_candidate_mbo_blocks"] == 30
        assert cand["quarantined_dates_in_candidate_sessions"] == []
        assert cand["quarantined_dates_inside_candidate_block_spans"] == []
        prop = propose_partitions(blocks, mbo_blocks_artifact_sha256="b" * 64)
        pc = prop["research_eligibility_binding"]["candidate"]
        assert pc["n_candidate_spanning_mbo_blocks"] == 0
        assert pc["n_causal_roll_switches"] == 8
        assert pc["n_coverage_expected_sessions"] == 516
        assert pc["n_observed_dev_sessions"] == 317
        assert pc["n_eligible_observed_dev_sessions"] == 309
        assert pc["n_excluded_observed_dev_sessions"] == 8
        assert pc["quarantine_violations"] == []
        assert pc["partition_trading_days"] == {"DEV": 318, "SELECTION": 100,
                                                "HOLDOUT": 98}
        assert prop["state"] == "PROPOSED_NOT_ACTIVE"
        assert prop["activation_ready"] is False
        _ = _json

    def test_quarantined_date_as_mbo_session_cannot_be_top_level_pass(
            self, tmp_path):
        # REPRODUCED REVIEW DEFECT: binding FAILs did not reach the top-level
        # status, so an unsafe candidate presented itself as PASS.
        blocks = freeze_mbo_blocks(
            _deep_artifact(tmp_path, ["2024-09-02"], []))
        bchecks = {c["check"]: c["status"]
                   for c in blocks["research_eligibility_binding"]["checks"]}
        assert bchecks["quarantine_disjoint_from_candidate_mbo_blocks"] == "FAIL"
        assert blocks["status"] == "FAIL"

        prop = propose_partitions(blocks, mbo_blocks_artifact_sha256="a" * 64)
        pchecks = {c["check"]: c["status"]
                   for c in prop["research_eligibility_binding"]["checks"]}
        assert pchecks["quarantine_structurally_safe"] == "FAIL"
        viol = prop["research_eligibility_binding"]["candidate"][
            "quarantine_violations"]
        assert any("candidate MBO session" in v for v in viol)
        assert any("inside candidate block" in v for v in viol)
        assert prop["status"] == "FAIL"

    def test_block_stage_deferred_warn_alone_does_not_fail_the_artifact(
            self, tmp_path):
        # The intentional block-stage DEFERRED WARN must stay non-blocking.
        blocks = freeze_mbo_blocks(
            _deep_artifact(tmp_path, ["2026-08-04"], []))
        checks = {c["check"]: c["status"]
                  for c in blocks["research_eligibility_binding"]["checks"]}
        assert checks["quarantine_structurally_safe"] == "WARN"
        assert blocks["status"] == "PASS"

    @pytest.mark.parametrize("bad", ["not-a-hash", "a" * 63, "a" * 65,
                                     "A" * 64, "", None, 12345])
    def test_malformed_structural_identity_fails_artifact(self, tmp_path, bad):
        blocks = freeze_mbo_blocks(
            _deep_artifact(tmp_path, ["2026-08-04"], []))
        prop = propose_partitions(blocks, mbo_blocks_artifact_sha256=bad)
        checks = {c["check"]: c["status"]
                  for c in prop["research_eligibility_binding"]["checks"]}
        assert checks["structural_artifact_identities_valid"] == "FAIL"
        assert prop["status"] == "FAIL"

    def test_stale_policy_binding_makes_both_candidates_non_pass(
            self, tmp_path, monkeypatch):
        import nqresearch.qa.closeout as co
        from nqresearch.eligibility import EligibilityPolicyError

        def _boom(*a, **k):
            raise EligibilityPolicyError("stale/invalid policy binding")

        monkeypatch.setattr(co, "_policy_binding_core",
                            lambda root, droot: (
                                {"amendment": "PA-0002",
                                 "quarantined_dates": []},
                                [__import__("nqresearch.qa.status",
                                            fromlist=["check"]).check(
                                    "eligibility_policy_bound_to_evidence_matrix",
                                    "FAIL", "stale")]))
        blocks = freeze_mbo_blocks(
            _deep_artifact(tmp_path, ["2026-08-04"], []))
        assert blocks["status"] == "FAIL"
        prop = propose_partitions(blocks, mbo_blocks_artifact_sha256="a" * 64)
        assert prop["status"] == "FAIL"
        _ = _boom


class TestCoverageSubstance:
    """The coverage WARN is only acceptable for the specifically understood
    pre-RTH Good Friday case."""

    MANDATORY = ["n_expected_complete_sessions", "n_fail", "missing_sessions",
                 "cross_file_order_violations",
                 "missing_pre_rth_short_sessions", "checks"]

    def _cov(self, **over):
        doc = {
            "artifact": "mbp1_full_history_coverage", "status": "WARN",
            "n_expected_complete_sessions": 516, "n_fail": 0,
            "missing_sessions": [], "cross_file_order_violations": 0,
            "missing_pre_rth_short_sessions": ["2025-04-18"],
            "checks": [
                {"check": "no_missing_expected_sessions", "status": "PASS"},
                {"check": "pre_rth_short_sessions_without_data",
                 "status": "WARN"},
                {"check": "no_session_fails", "status": "PASS"},
                {"check": "degraded_dates_assessed", "status": "PASS"},
                {"check": "cross_file_monotonic_order", "status": "PASS"},
            ],
        }
        doc.update(over)
        return doc

    def _pass_cov(self, **over):
        """A coherent all-PASS coverage state."""
        doc = self._cov(status="PASS", missing_pre_rth_short_sessions=[])
        doc["checks"] = [c for c in doc["checks"]
                         if c["check"] != "pre_rth_short_sessions_without_data"]
        doc.update(over)
        return doc

    def test_understood_state_has_no_problems(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        assert _coverage_substance_problems(self._cov(), "cov.json") == []

    def test_real_coverage_artifact_is_in_the_understood_state(self):
        import json as _j

        from nqresearch import paths
        from nqresearch.qa.closeout import _coverage_substance_problems

        p = (paths.data_root() / "qa" / "m0_closeout"
             / "mbp1_full_history_coverage.json")
        if not p.is_file():
            pytest.skip("live coverage artifact not available")
        doc = _j.loads(p.read_text(encoding="utf-8"))
        assert _coverage_substance_problems(doc, p.name) == []

    @pytest.mark.parametrize("over,needle", [
        ({"n_fail": 3}, "n_fail"),
        ({"missing_sessions": ["2025-05-05"]}, "missing_sessions"),
        ({"cross_file_order_violations": 2}, "cross_file_order_violations"),
        ({"n_expected_complete_sessions": 515},
         "n_expected_complete_sessions"),
        ({"checks": []}, "coverage checks"),
    ])
    def test_material_deviations_fail(self, over, needle):
        from nqresearch.qa.closeout import _coverage_substance_problems

        problems = _coverage_substance_problems(self._cov(**over), "cov.json")
        assert any(needle in p for p in problems), problems

    def test_unknown_or_renamed_warn_fails(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        for extra in ({"check": "some_other_condition", "status": "WARN"},
                      {"check": "pre_rth_short_sessions_without_data_v2",
                       "status": "WARN"},
                      {"check": "no_session_fails", "status": "FAIL"}):
            doc = self._cov()
            doc["checks"] = doc["checks"] + [extra]
            problems = _coverage_substance_problems(doc, "cov.json")
            assert problems, extra

    def test_coherent_pass_state_accepted(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        assert _coverage_substance_problems(self._pass_cov(), "cov.json") == []

    @pytest.mark.parametrize("key", MANDATORY)
    def test_each_mandatory_field_missing_fails(self, key):
        from nqresearch.qa.closeout import _coverage_substance_problems

        doc = {k: v for k, v in self._cov().items() if k != key}
        problems = _coverage_substance_problems(doc, "cov.json")
        assert any(key in p for p in problems), problems

    @pytest.mark.parametrize("key", MANDATORY)
    def test_each_mandatory_field_null_fails(self, key):
        from nqresearch.qa.closeout import _coverage_substance_problems

        assert _coverage_substance_problems(self._cov(**{key: None}),
                                            "cov.json")

    @pytest.mark.parametrize("key", ["n_expected_complete_sessions", "n_fail",
                                     "cross_file_order_violations"])
    @pytest.mark.parametrize("value", [True, False, "0", "516", 1.0, [], {}])
    def test_integer_fields_reject_boolean_and_string(self, key, value):
        from nqresearch.qa.closeout import _coverage_substance_problems

        assert _coverage_substance_problems(self._cov(**{key: value}),
                                            "cov.json")

    @pytest.mark.parametrize("value", [{}, "", "2025-04-18", 0,
                                       ["2025-04-18", 5]])
    def test_wrong_container_types_fail(self, value):
        from nqresearch.qa.closeout import _coverage_substance_problems

        assert _coverage_substance_problems(
            self._cov(missing_pre_rth_short_sessions=value), "cov.json")
        assert _coverage_substance_problems(
            self._cov(missing_sessions=value), "cov.json")

    def test_duplicate_check_names_fail(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        doc = self._cov()
        doc["checks"] = doc["checks"] + [dict(doc["checks"][0])]
        assert any("duplicate" in p for p in
                   _coverage_substance_problems(doc, "cov.json"))

    @pytest.mark.parametrize("entry", [
        {"check": 123, "status": "PASS"},
        {"check": "x", "status": "UNKNOWN"},
        {"check": "x"},
        "not-a-dict",
        None,
    ])
    def test_malformed_check_entries_fail(self, entry):
        from nqresearch.qa.closeout import _coverage_substance_problems

        doc = self._cov()
        doc["checks"] = doc["checks"] + [entry]
        assert any("malformed" in p for p in
                   _coverage_substance_problems(doc, "cov.json"))

    def test_understood_warn_name_with_wrong_date_fails(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        doc = self._cov(missing_pre_rth_short_sessions=["2099-12-31"])
        assert any("2025-04-18" in p for p in
                   _coverage_substance_problems(doc, "cov.json"))

    def test_additional_pending_date_fails(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        doc = self._cov(
            missing_pre_rth_short_sessions=["2025-04-18", "2026-04-03"])
        assert _coverage_substance_problems(doc, "cov.json")

    def test_additional_or_renamed_warn_fails(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        extra = self._cov()
        extra["checks"] = extra["checks"] + [
            {"check": "another_condition", "status": "WARN"}]
        assert _coverage_substance_problems(extra, "cov.json")

        renamed = self._cov()
        renamed["checks"] = [
            {"check": "pre_rth_short_sessions_without_data_v2",
             "status": "WARN"} if c["check"].startswith("pre_rth") else c
            for c in renamed["checks"]]
        assert _coverage_substance_problems(renamed, "cov.json")

    def test_pass_status_with_good_friday_warning_present_fails(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        # top-level PASS while the understood WARN check is still present
        doc = self._cov(status="PASS")
        assert any("incoherent" in p for p in
                   _coverage_substance_problems(doc, "cov.json"))
        # ...and all-PASS checks while the missing-session field is non-empty
        doc2 = self._pass_cov(missing_pre_rth_short_sessions=["2025-04-18"])
        assert any("not empty" in p for p in
                   _coverage_substance_problems(doc2, "cov.json"))

    def test_warn_status_with_all_checks_pass_fails(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        doc = self._pass_cov(status="WARN")
        assert any("incoherent" in p for p in
                   _coverage_substance_problems(doc, "cov.json"))

    def test_warn_without_exact_good_friday_list_fails(self):
        from nqresearch.qa.closeout import _coverage_substance_problems

        assert _coverage_substance_problems(
            self._cov(missing_pre_rth_short_sessions=[]), "cov.json")


class TestPartitionGatesMore:
    def test_non_contiguous_configuration_fails_gate(self, tmp_path, monkeypatch):
        # Deliberately broken boundary: DEV ends 2025-11-06 (Thu), leaving
        # trading day 2025-11-07 unassigned before SELECTION starts 11-10.
        import nqresearch.qa.closeout as co

        monkeypatch.setattr(co, "PROPOSED_DEV_END", date(2025, 11, 6))
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        prop = propose_partitions(freeze_mbo_blocks(p))
        gate = [c for c in prop["checks"]
                if c["check"] == "partition_ranges_contiguous"][0]
        assert gate["status"] == "FAIL"
        assert prop["status"] == "FAIL"

    def test_blocks_bound_to_effective_calendar_identity(self, tmp_path):
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        b = freeze_mbo_blocks(p)
        for key in ("baseline_file_sha256", "overrides_file_sha256",
                    "effective_calendar_sha256"):
            assert len(b["based_on"][key]) == 64


class TestPartitionProposal:
    def test_counts_and_state(self, tmp_path):
        p = _deep_artifact(
            tmp_path,
            ["2025-08-18", "2025-11-18", "2026-03-04", "2026-05-04", "2026-08-04"],
            [],
        )
        blocks = freeze_mbo_blocks(p)
        prop = propose_partitions(blocks)
        assert prop["state"] == "PROPOSED_NOT_ACTIVE"
        assert prop["boundaries_on_trading_days"] is True
        ms = prop["mbo_sessions_per_partition"]
        assert ms == {"DEV": 1, "SELECTION": 2, "HOLDOUT": 2}
        assert prop["proposal"]["HOLDOUT"]["tentative"] is True
