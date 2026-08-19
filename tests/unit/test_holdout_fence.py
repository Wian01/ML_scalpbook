"""Mechanical holdout fence: FAIL-CLOSED behavior, boundary cases, and the
research-layer enforcement reproduced from the independent audit. Synthetic
temporary paths and dates only. Status: PENDING_INDEPENDENT_AUDIT."""

import inspect
from datetime import date

import pytest
import yaml

from nqresearch.holdout import (
    ACTIVE_PARTITIONS_FILENAME,
    HoldoutAccessError,
    HoldoutFenceError,
    PartitionsNotActiveError,
    _check_range,
    _load_active_partitions_from,
    assert_research_range_allowed,
    holdout_opening,
    load_active_partitions,
)

SYNTH = {
    "activated": True,
    "approval": {
        "approved_by": "synthetic approver",
        "approval_reference": "AL-9999 (synthetic)",
        "approved_at_utc": "2099-01-01T00:00:00+00:00",
    },
    "partition_proposal_sha256": "a" * 64,
    "effective_calendar_sha256": "b" * 64,
    "dev": {"start": "2099-01-05", "end": "2099-03-31"},
    "selection": {"start": "2099-04-01", "end": "2099-05-29"},
    "holdout": {"start": "2099-06-01", "end": "2099-08-31"},
}


def _repo(tmp_path, doc=None):
    root = tmp_path / "repo"
    (root / "config" / "data").mkdir(parents=True)
    if doc is not None:
        (root / "config" / "data" / ACTIVE_PARTITIONS_FILENAME).write_text(
            yaml.safe_dump(doc)
        )
    return root


def _parts(doc=SYNTH, tmp_path=None):
    # Build via the private loader against a synthetic tree.
    root = _repo(tmp_path, doc)
    return _load_active_partitions_from(root)


class TestFailClosed:
    def test_no_active_config_fails_closed(self, tmp_path):
        with pytest.raises(PartitionsNotActiveError, match="FAIL-CLOSED"):
            _load_active_partitions_from(_repo(tmp_path))

    def test_live_repo_fails_closed_and_public_api_has_no_injection(self):
        # The real repository has NO active partitions: the PUBLIC loader and
        # fence must fail closed, and neither accepts a config-injection
        # parameter that could bypass this.
        with pytest.raises(PartitionsNotActiveError):
            load_active_partitions()
        with pytest.raises(PartitionsNotActiveError):
            assert_research_range_allowed(date(2099, 1, 10), date(2099, 1, 20))
        for fn in (load_active_partitions, assert_research_range_allowed):
            params = set(inspect.signature(fn).parameters)
            assert not params & {"repo_root", "root", "config", "path"}, fn

    def test_malformed_yaml_fails_closed(self, tmp_path):
        root = _repo(tmp_path)
        (root / "config" / "data" / ACTIVE_PARTITIONS_FILENAME).write_text(
            "activated: true\nnot: [valid"
        )
        with pytest.raises(PartitionsNotActiveError, match="malformed"):
            _load_active_partitions_from(root)

    @pytest.mark.parametrize("mutate", [
        {"activated": False},
        {"approval": {**SYNTH["approval"], "approved_by": "  "}},
        {"approval": {**SYNTH["approval"], "approval_reference": ""}},
        {"approval": {**SYNTH["approval"],
                      "approved_at_utc": "2099-01-01T00:00:00"}},  # naive
        {"approval": {**SYNTH["approval"],
                      "approved_at_utc": "2099-01-01T00:00:00+02:00"}},  # non-UTC
        {"partition_proposal_sha256": "nothex"},
        {"effective_calendar_sha256": ""},
        {"holdout": {"start": "2099-03-01", "end": "2099-03-15"}},  # non-chrono
        {"dev": {"start": "2099-03-31", "end": "2099-01-05"}},      # inverted
        {"unexpected_extra": True},                                  # extra field
        {"dev": {"start": "2099-01-05", "end": "2099-03-31", "x": 1}},  # nested extra
    ])
    def test_invalid_configs_fail_closed(self, tmp_path, mutate):
        with pytest.raises(PartitionsNotActiveError):
            _parts({**SYNTH, **mutate}, tmp_path)


class TestHoldoutRefusal:
    def test_range_inside_dev_allowed(self, tmp_path):
        _check_range(date(2099, 1, 10), date(2099, 2, 10), _parts(SYNTH, tmp_path))

    def test_dev_through_selection_allowed(self, tmp_path):
        _check_range(date(2099, 3, 1), date(2099, 5, 1), _parts(SYNTH, tmp_path))

    @pytest.mark.parametrize("start,end", [
        (date(2099, 6, 1), date(2099, 6, 1)),     # exactly holdout start
        (date(2099, 8, 31), date(2099, 8, 31)),   # exactly holdout end
        (date(2099, 5, 20), date(2099, 6, 1)),    # touches boundary
        (date(2099, 7, 1), date(2099, 7, 15)),    # fully inside
        (date(2099, 5, 1), date(2099, 9, 30)),    # envelops holdout
    ])
    def test_any_holdout_overlap_refused(self, tmp_path, start, end):
        with pytest.raises(HoldoutAccessError):
            _check_range(start, end, _parts(SYNTH, tmp_path))

    def test_day_before_holdout_allowed(self, tmp_path):
        _check_range(date(2099, 5, 25), date(2099, 5, 29), _parts(SYNTH, tmp_path))

    def test_post_holdout_forward_refused(self, tmp_path):
        with pytest.raises(HoldoutFenceError):
            _check_range(date(2099, 9, 5), date(2099, 9, 10), _parts(SYNTH, tmp_path))

    def test_pre_dev_refused(self, tmp_path):
        with pytest.raises(HoldoutFenceError):
            _check_range(date(2098, 12, 1), date(2098, 12, 10),
                         _parts(SYNTH, tmp_path))

    def test_inverted_request_refused(self, tmp_path):
        with pytest.raises(HoldoutFenceError, match="malformed"):
            _check_range(date(2099, 2, 10), date(2099, 1, 10),
                         _parts(SYNTH, tmp_path))


class TestResearchLayerEnforcement:
    """The independent audit's live bypass proof, as regression tests."""

    def test_research_api_fails_closed_live_and_returns_nothing(self):
        # With partitions inactive, the DEFAULT research API must fail closed
        # — it can never return the 625 canonical files.
        from nqresearch.research import research_input_entries, research_input_files

        with pytest.raises(PartitionsNotActiveError):
            research_input_entries(date(2025, 1, 10), date(2025, 1, 20))
        with pytest.raises(PartitionsNotActiveError):
            research_input_files(date(2024, 8, 19), date(2026, 8, 14))

    def test_research_api_requires_explicit_range(self):
        from nqresearch.research import research_input_entries, research_input_files

        for fn in (research_input_entries, research_input_files):
            params = inspect.signature(fn).parameters
            assert list(params) == ["start", "end"]
            assert all(p.default is inspect.Parameter.empty
                       for p in params.values())

    def test_qa_corpus_api_is_explicitly_named_and_documented(self):
        from nqresearch import qa_corpus

        assert "QA-ONLY" in qa_corpus.__doc__
        assert "never research input" in qa_corpus.__doc__


class TestSessionBoundaryHazard:
    def test_utc_file_spans_selection_and_holdout_sessions(self):
        # The audit's boundary proof, kept as a regression fact: UTC file
        # 2026-03-31 carries events of BOTH the last SELECTION session and
        # the first HOLDOUT session — raw UTC-day paths are therefore never
        # valid fenced research data.
        from nqresearch.sessions import session_utc_dates

        sel_last = set(session_utc_dates(date(2026, 3, 31)))
        hold_first = set(session_utc_dates(date(2026, 4, 1)))
        shared = sel_last & hold_first
        assert shared == {date(2026, 3, 31)}

    def test_research_api_never_returns_paths_even_with_gates_open(self,
                                                                   monkeypatch):
        # Even when the fence and provenance gates pass, the Milestone 1
        # research API refuses: no raw UTC-day paths are ever returned.
        import nqresearch.research as research_mod
        from nqresearch.research import ResearchLoaderNotImplementedError

        monkeypatch.setattr(research_mod, "_gate", lambda s, e: None)
        with pytest.raises(ResearchLoaderNotImplementedError, match="never"):
            research_mod.research_session_records(date(2099, 1, 10),
                                                  date(2099, 1, 20))

    def test_research_gate_invokes_fence_and_provenance(self):
        src = __import__("inspect").getsource(
            __import__("nqresearch.research", fromlist=["_gate"])._gate
        )
        assert "assert_research_range_allowed" in src
        assert "require_provenance" in src


MANDATORY = ["boundaries_on_trading_days", "partition_ranges_contiguous",
             "no_partition_spanning_mbo_blocks"]


class TestActivationEvidence:
    def _synthetic_repo(self, tmp_path, baseline_status="DOCUMENT_VERIFIED",
                        groups=None, with_evidence=True):
        """Synthetic repo root with real calendar baseline + custom overrides
        whose baseline_verification content is controllable."""
        import shutil

        import yaml as _yaml

        from nqresearch.calendar import clear_calendar_cache
        from nqresearch.config import _repo_root
        from nqresearch.holdout import EXPECTED_BASELINE_GROUPS

        root = tmp_path / "synthrepo"
        (root / "config" / "data").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "pyproject.toml").write_text("[project]\nname='x'\n")
        shutil.copy(_repo_root() / "config" / "data" / "cme_calendar.yaml",
                    root / "config" / "data" / "cme_calendar.yaml")
        if groups is None:
            groups = [
                {"holiday_group": name, "status": baseline_status,
                 **({"source_reference": "CME schedule (synthetic)",
                     "document_sha256": "e" * 64} if with_evidence else {})}
                for name in sorted(EXPECTED_BASELINE_GROUPS)
            ]
        doc = {
            "meta": {"baseline_verification": {"status": baseline_status,
                                               "groups": groups}},
            "early_close_overrides": {"2025-01-09": "08:30"},
        }
        (root / "config" / "data" / "cme_calendar_overrides.yaml").write_text(
            _yaml.safe_dump(doc)
        )
        clear_calendar_cache()
        return root

    def _evidence_env(self, tmp_path, proposal_doc, declared_sha=None,
                      baseline_status="DOCUMENT_VERIFIED", groups=None,
                      with_evidence=True, audit_entry=True):
        import hashlib
        import json as _json

        from nqresearch.calendar import calendar_identity

        repo_root = self._synthetic_repo(tmp_path, baseline_status,
                                         groups, with_evidence)
        data_root = tmp_path / "dataroot"
        (data_root / "qa" / "m0_closeout").mkdir(parents=True)
        ppath = data_root / "qa" / "m0_closeout" / "partition_proposal.json"
        ppath.write_text(_json.dumps(proposal_doc))
        actual_sha = hashlib.sha256(ppath.read_bytes()).hexdigest()
        declared = declared_sha or actual_sha
        # Immutable human-approval evidence: the audit-log entry named by the
        # approval_reference must cite the approved proposal SHA.
        log = repo_root / "docs" / "implementation-audit-log.md"
        if audit_entry:
            log.write_text(
                "# log\n\n## AL-9999 synthetic approval\n\n"
                f"approved proposal sha256 {declared}\n"
            )
        else:
            log.write_text("# log\n\n## AL-0001 unrelated\n")
        cal_sha = calendar_identity(repo_root)["effective_calendar_sha256"]
        doc = {**SYNTH,
               "partition_proposal_sha256": declared,
               "effective_calendar_sha256": cal_sha}
        parts = _parts(doc, tmp_path)
        return parts, repo_root, data_root

    def _proposal(self, **over):
        doc = {
            "artifact": "partition_proposal",
            "status": "PASS",
            "state": "APPROVED_FOR_ACTIVATION",
            "activation_ready": True,
            "calendar_verification_state": "DOCUMENT_VERIFIED",
            "checks": [{"check": c, "status": "PASS"} for c in MANDATORY],
            "proposal": {
                "DEV": {"start": "2099-01-05", "end": "2099-03-31"},
                "SELECTION": {"start": "2099-04-01", "end": "2099-05-29"},
                "HOLDOUT": {"start": "2099-06-01", "end": "2099-08-31"},
            },
        }
        doc.update(over)
        return doc

    def test_valid_evidence_accepted(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(tmp_path, self._proposal())
        _verify_activation_evidence(parts, repo_root, data_root)

    def test_live_provisional_proposal_rejected(self, tmp_path):
        # THE reproduced audit finding: a proposal with the EXACT current
        # provisional states must fail closed even with matching hashes.
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal(
            state="PROPOSED_NOT_ACTIVE",
            activation_ready=False,
            calendar_verification_state="PROVISIONAL_DOCUMENT_VERIFICATION_PENDING",
        )
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="can never activate"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_real_live_proposal_artifact_rejected(self):
        # Against the REAL data volume: the current on-disk provisional
        # proposal must never satisfy activation.
        import hashlib
        from pathlib import Path

        from nqresearch import paths
        from nqresearch.calendar import calendar_identity
        from nqresearch.config import _repo_root
        from nqresearch.holdout import ActivePartitions, _verify_activation_evidence

        live = paths.data_root() / "qa" / "m0_closeout" / "partition_proposal.json"
        if not live.is_file():
            pytest.skip("live proposal artifact not available")
        parts = ActivePartitions(**{
            **SYNTH,
            "dev": {"start": "2024-08-19", "end": "2025-11-07"},
            "selection": {"start": "2025-11-10", "end": "2026-03-31"},
            "holdout": {"start": "2026-04-01", "end": "2026-08-14"},
            "partition_proposal_sha256":
                hashlib.sha256(live.read_bytes()).hexdigest(),
            "effective_calendar_sha256":
                calendar_identity(_repo_root())["effective_calendar_sha256"],
        })
        with pytest.raises(PartitionsNotActiveError):
            _verify_activation_evidence(parts, _repo_root(), paths.data_root())

    def test_fabricated_hash_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), declared_sha="c" * 64
        )
        with pytest.raises(PartitionsNotActiveError, match="actual approved"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_range_mismatch_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal()
        doc["proposal"]["HOLDOUT"]["start"] = "2099-06-02"
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError, match="exactly equal"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_failed_structural_checks_fail(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal()
        doc["checks"][0]["status"] = "FAIL"
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError, match="structural"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_incomplete_mandatory_check_set_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal()
        doc["checks"] = doc["checks"][:2]  # one mandatory check missing
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError, match="exactly match"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_contradictory_state_rejected(self, tmp_path):
        # PROPOSED_NOT_ACTIVE + activation_ready=true must fail on STATE.
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal(state="PROPOSED_NOT_ACTIVE", activation_ready=True)
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="APPROVED_FOR_ACTIVATION"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_approved_state_with_ready_false_rejected(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal(activation_ready=False)
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError, match="contradicts"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_approved_state_with_pending_calendar_rejected(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal(
            calendar_verification_state="PROVISIONAL_DOCUMENT_VERIFICATION_PENDING"
        )
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError, match="contradicts"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_missing_expected_group_fails(self, tmp_path):
        from nqresearch.holdout import (
            EXPECTED_BASELINE_GROUPS,
            _verify_activation_evidence,
        )

        groups = [
            {"holiday_group": name, "status": "DOCUMENT_VERIFIED",
             "source_reference": "syn", "document_sha256": "e" * 64}
            for name in sorted(EXPECTED_BASELINE_GROUPS)[:-1]  # one missing
        ]
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), groups=groups
        )
        with pytest.raises(PartitionsNotActiveError, match="nine-group"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_duplicate_and_unexpected_group_fail(self, tmp_path):
        from nqresearch.holdout import (
            EXPECTED_BASELINE_GROUPS,
            _verify_activation_evidence,
        )

        base = [
            {"holiday_group": name, "status": "DOCUMENT_VERIFIED",
             "source_reference": "syn", "document_sha256": "e" * 64}
            for name in sorted(EXPECTED_BASELINE_GROUPS)
        ]
        dup = base + [dict(base[0])]
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), groups=dup
        )
        with pytest.raises(PartitionsNotActiveError, match="duplicate"):
            _verify_activation_evidence(parts, repo_root, data_root)
        extra = base + [{"holiday_group": "Invented Day (2099-01-01)",
                         "status": "DOCUMENT_VERIFIED",
                         "source_reference": "syn",
                         "document_sha256": "e" * 64}]
        parts2, repo_root2, data_root2 = self._evidence_env(
            tmp_path / "b", self._proposal(), groups=extra
        )
        with pytest.raises(PartitionsNotActiveError, match="nine-group"):
            _verify_activation_evidence(parts2, repo_root2, data_root2)

    def test_verified_group_without_document_identity_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), with_evidence=False
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="official-document evidence"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_unbound_approval_evidence_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), audit_entry=False
        )
        with pytest.raises(PartitionsNotActiveError, match="no entry"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_audit_entry_without_sha_binding_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(tmp_path, self._proposal())
        (repo_root / "docs" / "implementation-audit-log.md").write_text(
            "# log\n\n## AL-9999 synthetic approval\n\nno sha cited here\n"
        )
        with pytest.raises(PartitionsNotActiveError, match="does not cite"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_pending_jan9_document_identity_blocks(self, tmp_path):
        # A declared-but-pending document identity in the references (the
        # real Jan-9 situation) blocks activation.
        import yaml as _yaml

        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(tmp_path, self._proposal())
        ov = repo_root / "config" / "data" / "cme_calendar_overrides.yaml"
        doc = _yaml.safe_load(ov.read_text())
        doc["meta"]["references"] = [{"id": "cme-2025-01-09-mourning",
                                      "document_sha256": None}]
        ov.write_text(_yaml.safe_dump(doc))
        with pytest.raises(PartitionsNotActiveError, match="pending/invalid"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_pending_baseline_verification_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(),
            baseline_status="OBSERVATIONALLY_CONSISTENT_DOCUMENT_PENDING",
        )
        with pytest.raises(PartitionsNotActiveError, match="baseline"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_missing_proposal_artifact_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        repo_root = self._synthetic_repo(tmp_path)
        parts = _parts(SYNTH, tmp_path)
        with pytest.raises(PartitionsNotActiveError, match="evidence missing"):
            _verify_activation_evidence(parts, repo_root,
                                        tmp_path / "empty_dataroot")

    def test_wrong_calendar_identity_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(tmp_path, self._proposal())
        parts = parts.model_copy(
            update={"effective_calendar_sha256": "d" * 64}
        )
        with pytest.raises(PartitionsNotActiveError, match="calendar"):
            _verify_activation_evidence(parts, repo_root, data_root)


class TestLegacyApiRemoved:
    def test_sources_has_no_public_research_api(self):
        from nqresearch import sources

        assert not hasattr(sources, "research_input_entries")
        assert not hasattr(sources, "research_input_files")


class TestNoOverride:
    def test_holdout_opening_always_refuses(self):
        with pytest.raises(HoldoutFenceError, match="not implemented"):
            holdout_opening()

    def test_fence_has_no_override_parameter(self):
        params = inspect.signature(assert_research_range_allowed).parameters
        assert not any("override" in p or "allow" in p for p in params)
