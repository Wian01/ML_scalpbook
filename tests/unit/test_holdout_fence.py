"""Mechanical holdout fence: FAIL-CLOSED behavior, boundary cases, and the
research-layer enforcement reproduced from the independent audit. Synthetic
temporary paths and dates only. Status: PENDING_INDEPENDENT_AUDIT."""

import inspect
from datetime import date

import pytest
import yaml
from pydantic import BaseModel

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
        "approval_reference": "AL-9999",
        "approved_at_utc": "2099-01-01T00:00:00+00:00",
    },
    "activation_candidate_sha256": "9" * 64,
    "partition_proposal_sha256": "a" * 64,
    "effective_calendar_sha256": "b" * 64,
    "evidence_matrix_sha256": "e" * 64,
    "cme_correspondence_sha256": "f" * 64,
    "research_eligibility_sha256": "d" * 64,
    "coverage_artifact_sha256": "1" * 64,
    "mbo_blocks_sha256": "2" * 64,
    "front_contract_series_sha256": "3" * 64,
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
        {"activation_candidate_sha256": "nothex"},   # candidate identity
        {"partition_proposal_sha256": "nothex"},
        {"effective_calendar_sha256": ""},
        {"evidence_matrix_sha256": "nothex"},           # PA-0001 binding
        {"cme_correspondence_sha256": ""},              # PA-0001 binding
        {"research_eligibility_sha256": "nothex"},      # PA-0002 binding
        {"coverage_artifact_sha256": "nothex"},         # structural binding
        {"mbo_blocks_sha256": ""},                      # structural binding
        {"front_contract_series_sha256": "zz"},         # structural binding
        {"holdout": {"start": "2099-03-01", "end": "2099-03-15"}},  # non-chrono
        {"dev": {"start": "2099-03-31", "end": "2099-01-05"}},      # inverted
        {"unexpected_extra": True},                                  # extra field
        {"dev": {"start": "2099-01-05", "end": "2099-03-31", "x": 1}},  # nested extra
    ])
    def test_invalid_configs_fail_closed(self, tmp_path, mutate):
        with pytest.raises(PartitionsNotActiveError):
            _parts({**SYNTH, **mutate}, tmp_path)

    # `activated` is the single flag that turns research access on. Every
    # truthy-but-not-boolean value must be REFUSED: YAML happily produces
    # ints, floats and bare strings, and `if not self.activated` would have
    # accepted 1, "true" and "yes" as an activation.
    COERCIVE_ACTIVATED = [0, 1, -1, "true", "false", "yes", "no", "True",
                          "False", "on", "off", "", None, [], {}, [True],
                          {"activated": True}, 1.0, 0.0, "1", "0"]

    @pytest.mark.parametrize("value", COERCIVE_ACTIVATED)
    def test_only_literal_boolean_true_activates(self, tmp_path, value):
        with pytest.raises(PartitionsNotActiveError):
            _parts({**SYNTH, "activated": value}, tmp_path)

    def test_literal_boolean_true_is_accepted(self, tmp_path):
        parts = _parts({**SYNTH, "activated": True}, tmp_path)
        assert parts.activated is True

    @pytest.mark.parametrize("text", ["true", "yes", "1", "on", "y", "True"])
    def test_raw_yaml_truthy_spellings(self, tmp_path, text):
        # Written as RAW YAML, so this exercises the LOADER rather than a
        # Python-level dict. Spellings PyYAML resolves to a real boolean must
        # activate; every other truthy spelling must fail closed.
        import yaml as _yaml

        root = _repo(tmp_path)
        body = _yaml.safe_dump({**SYNTH})
        body = body.replace("activated: true", f"activated: {text}")
        (root / "config" / "data" / ACTIVE_PARTITIONS_FILENAME).write_text(body)
        if _yaml.safe_load(body)["activated"] is True:
            # A genuine YAML boolean: this IS `true`, so it must load.
            assert _load_active_partitions_from(root).activated is True
        else:
            with pytest.raises(PartitionsNotActiveError):
                _load_active_partitions_from(root)

    def test_every_schema_boolean_is_strict(self):
        # No activation-critical boolean may fall back to ordinary `bool`.
        # StrictBool is Annotated[bool, Strict()], so strictness lives in the
        # field METADATA, not in the annotation.
        import inspect

        import nqresearch.holdout as h

        def _is_strict(field):
            return any(getattr(m, "strict", None) is True
                       for m in (field.metadata or []))

        checked = 0
        for name, obj in vars(h).items():
            if not (inspect.isclass(obj) and issubclass(obj, BaseModel)):
                continue
            for fname, field in obj.model_fields.items():
                if field.annotation is not bool:
                    continue
                assert _is_strict(field), f"{name}.{fname} is a lax bool"
                checked += 1
        assert checked >= 4, checked

    def test_activated_field_is_strictbool(self):
        from nqresearch.holdout import ActivePartitions

        field = ActivePartitions.model_fields["activated"]
        assert field.annotation is bool
        assert any(getattr(m, "strict", None) is True
                   for m in (field.metadata or []))


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
    def _synthetic_repo(self, tmp_path, overrides_status=None, groups=None,
                        matrix_doc=None, data_root=None, jan9_ref=None,
                        policy_dates=None, policy_doc=None):
        """Synthetic repo root: real calendar baseline + a synthetic
        date-level evidence matrix (PA-0001) + coherent overrides."""
        import shutil

        import yaml as _yaml

        import conftest as fx
        from nqresearch.calendar import clear_calendar_cache
        from nqresearch.calendar_evidence import (
            CALENDAR_EVIDENCE_COMPLETE_STATE,
        )
        from nqresearch.config import _repo_root
        from nqresearch.holdout import EXPECTED_BASELINE_GROUPS

        root = tmp_path / "synthrepo"
        (root / "config" / "data").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "pyproject.toml").write_text("[project]\nname='x'\n")
        shutil.copy(_repo_root() / "config" / "data" / "cme_calendar.yaml",
                    root / "config" / "data" / "cme_calendar.yaml")
        data_root = data_root or (tmp_path / "dataroot")
        if matrix_doc is None:
            matrix_doc, _ = fx.synthetic_matrix_doc(
                data_root / "reference" / "cme_calendar")
        # coverage first: it binds the artifact SHA into the matrix doc
        fx.write_coverage_for(data_root, matrix_doc)
        fx.write_structural_artifacts(data_root)
        matrix_sha = fx.write_matrix(root, matrix_doc)
        # PA-0002 policy must cover exactly the PENDING dates of this matrix
        pending = sorted(d["date"] for d in matrix_doc["dates"]
                         if d["state"] == "PENDING_EVIDENCE")
        fx.write_eligibility_policy(
            root, matrix_sha,
            pending if policy_dates is None else policy_dates,
            doc=policy_doc)
        if groups is None:
            groups = fx.overrides_groups_for(matrix_doc,
                                             EXPECTED_BASELINE_GROUPS)
        meta = {"baseline_verification": {
            "status": overrides_status or CALENDAR_EVIDENCE_COMPLETE_STATE,
            "groups": groups}}
        if jan9_ref is not None:
            meta["references"] = [jan9_ref]
        doc = {
            "meta": meta,
            "early_close_overrides": {"2025-01-09": "08:30"},
        }
        (root / "config" / "data" / "cme_calendar_overrides.yaml").write_text(
            _yaml.safe_dump(doc)
        )
        clear_calendar_cache()
        return root, data_root

    # Friendly names used by the audit-omission tests, mapped to the exact
    # machine-readable approval field names.
    AUDIT_FIELDS = {
        "candidate": "activation_candidate_sha256",
        "proposal": "partition_proposal_sha256",
        "calendar": "effective_calendar_sha256",
        "matrix": "evidence_matrix_sha256",
        "email": "cme_correspondence_sha256",
        "policy": "research_eligibility_sha256",
        "coverage": "coverage_artifact_sha256",
        "blocks": "mbo_blocks_sha256",
        "front": "front_contract_series_sha256",
    }

    def _evidence_env(self, tmp_path, proposal_doc=None, candidate_doc=None,
                      declared_sha=None, declared_candidate_sha=None,
                      overrides_status=None, groups=None, matrix_doc=None,
                      audit_entry=True, audit_omit=(), jan9_ref=None,
                      wrong_matrix_sha=False, wrong_email_sha=False,
                      policy_dates=None, policy_doc=None,
                      wrong_policy_sha=False, wrong_blocks_sha=False,
                      bound_identity_override=None):
        import hashlib
        import json as _json

        import conftest as _fx
        from nqresearch.calendar import calendar_identity
        from nqresearch.calendar_evidence import (
            CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
            DISPOSITION_PENDING_DATES_QUARANTINED,
            matrix_file_sha256,
        )
        from nqresearch.holdout import (
            APPROVAL_DECISION_VALUE,
            CANDIDATE_ARTIFACT_FILENAME,
        )

        repo_root, data_root = self._synthetic_repo(
            tmp_path, overrides_status=overrides_status, groups=groups,
            matrix_doc=matrix_doc, jan9_ref=jan9_ref,
            policy_dates=policy_dates, policy_doc=policy_doc)
        close = data_root / "qa" / "m0_closeout"
        close.mkdir(parents=True, exist_ok=True)
        cov_sha = hashlib.sha256(
            (close / "mbp1_full_history_coverage.json").read_bytes()
        ).hexdigest()
        blocks_sha = hashlib.sha256(
            (close / "mbo_blocks_frozen.json").read_bytes()).hexdigest()
        front_sha = hashlib.sha256(
            (close / "mbp1_front_contract_series.json").read_bytes()
        ).hexdigest()

        # The NEUTRAL proposal: independently identifiable, PROPOSED_NOT_ACTIVE,
        # embedding the SAME structural identities the active configuration
        # binds (one truth, not two), with a clean CURRENT provenance envelope.
        proposal_doc = {**_fx.clean_envelope(),
                        **(self._proposal() if proposal_doc is None
                           else proposal_doc)}
        if "research_eligibility_binding" not in proposal_doc:
            proposal_doc["research_eligibility_binding"] = {
                "structural_artifact_sha256": {
                    "coverage_artifact_sha256": cov_sha,
                    "mbo_blocks_sha256": blocks_sha,
                    "front_contract_series_sha256": front_sha,
                }
            }
        ppath = close / "partition_proposal.json"
        ppath.write_text(_json.dumps(proposal_doc))
        declared = declared_sha or hashlib.sha256(
            ppath.read_bytes()).hexdigest()

        matrix_sha = matrix_file_sha256(repo_root)
        email_sha = hashlib.sha256(
            (data_root / "reference" / "cme_calendar" / "email.eml")
            .read_bytes()).hexdigest()
        policy_sha = hashlib.sha256(
            (repo_root / "config" / "data" / "research_eligibility.yaml")
            .read_bytes()).hexdigest()
        cal_sha = calendar_identity(repo_root)["effective_calendar_sha256"]
        identities = {
            "partition_proposal_sha256": declared,
            "effective_calendar_sha256": cal_sha,
            "evidence_matrix_sha256": ("1" * 64 if wrong_matrix_sha
                                       else matrix_sha),
            "cme_correspondence_sha256": ("2" * 64 if wrong_email_sha
                                          else email_sha),
            "research_eligibility_sha256": ("3" * 64 if wrong_policy_sha
                                            else policy_sha),
            "coverage_artifact_sha256": cov_sha,
            "mbo_blocks_sha256": ("4" * 64 if wrong_blocks_sha
                                  else blocks_sha),
            "front_contract_series_sha256": front_sha,
        }

        # The activation CANDIDATE: a SEPARATE artifact with its own identity.
        candidate_doc = {**_fx.clean_envelope(),
                         **(self._candidate() if candidate_doc is None
                            else candidate_doc)}
        if candidate_doc.get("bound_identities") == "AUTO":
            candidate_doc["bound_identities"] = {
                **identities, **(bound_identity_override or {})}
        cpath = close / CANDIDATE_ARTIFACT_FILENAME
        cpath.write_text(_json.dumps(candidate_doc))
        candidate_sha = declared_candidate_sha or hashlib.sha256(
            cpath.read_bytes()).hexdigest()

        # Immutable human-approval evidence: the audit-log entry named by
        # approval_reference must carry the exact decision value, the CANDIDATE
        # identity plus all EIGHT dependency identities, the exact partition
        # ranges, the approving identity and exact UTC timestamp, and the
        # quarantine disposition and calendar state — every one of them as an
        # unambiguous machine-readable field.
        cited = {"decision": APPROVAL_DECISION_VALUE,
                 "activation_candidate_sha256": candidate_sha, **identities}
        for name, rng in (("dev", SYNTH["dev"]), ("selection", SYNTH["selection"]),
                          ("holdout", SYNTH["holdout"])):
            cited[f"{name}_range"] = f"{rng['start']}..{rng['end']}"
        cited["approved_by"] = SYNTH["approval"]["approved_by"]
        cited["approved_at_utc"] = "2099-01-01T00:00:00Z"
        cited["quarantine_disposition"] = DISPOSITION_PENDING_DATES_QUARANTINED
        cited["calendar_state"] = CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED
        for omit in audit_omit:
            cited.pop(self.AUDIT_FIELDS.get(omit, omit), None)
        log = repo_root / "docs" / "implementation-audit-log.md"
        if audit_entry:
            log.write_text(
                "# log\n\n## AL-9999 synthetic approval\n\n"
                + "".join(f"- {k}: {v}\n" for k, v in cited.items()))
        else:
            log.write_text("# log\n\n## AL-0001 unrelated\n")

        parts = _parts({**SYNTH,
                        "activation_candidate_sha256": candidate_sha,
                        **identities}, tmp_path)
        return parts, repo_root, data_root

    def _proposal(self, **over):
        """The NEUTRAL partition proposal: never relabelled, never
        activation-ready."""
        from nqresearch.holdout import CANDIDATE_STATE_NOT_ACTIVE

        doc = {
            "artifact": "partition_proposal",
            "status": "PASS",
            "state": CANDIDATE_STATE_NOT_ACTIVE,
            "activation_ready": False,
            "checks": [{"check": c, "status": "PASS", "detail": "synthetic"}
                       for c in MANDATORY],
            "proposal": {
                "DEV": {"start": "2099-01-05", "end": "2099-03-31",
                        "trading_days": 60},
                "SELECTION": {"start": "2099-04-01", "end": "2099-05-29",
                              "trading_days": 42},
                "HOLDOUT": {"start": "2099-06-01", "end": "2099-08-31",
                            "tentative": True, "trading_days": 65},
                "FORWARD": {"start": "2099-09-01", "note": "synthetic"},
            },
            "mbo_sessions_per_partition": {"DEV": 1, "SELECTION": 0,
                                           "HOLDOUT": 0},
            "mbo_blocks_per_partition": {"DEV": ["MBO-BLK-001"],
                                         "SELECTION": [], "HOLDOUT": [],
                                         "SPANNING": []},
        }
        doc.update(over)
        return doc

    def _candidate(self, **over):
        """The activation CANDIDATE: a separate artifact asserting MECHANICAL
        readiness only, whose substance must agree with freshly recomputed
        evidence."""
        from nqresearch.calendar_evidence import (
            CALENDAR_EVIDENCE_COMPLETE_STATE,
            DISPOSITION_EVIDENCE_COMPLETE,
        )
        from nqresearch.eligibility import POLICY_STATE_APPROVED
        from nqresearch.holdout import (
            CANDIDATE_ARTIFACT_TYPE,
            CANDIDATE_STATE_READY,
        )

        src = self._proposal()
        doc = {
            "artifact": CANDIDATE_ARTIFACT_TYPE,
            "state": CANDIDATE_STATE_READY,
            "structural_ready": True,
            # NEVER true in a generated artifact.
            "activation_ready": False,
            # must equal the state implied by the disposition (both branches)
            "calendar_verification_state": CALENDAR_EVIDENCE_COMPLETE_STATE,
            "evidence_disposition": DISPOSITION_EVIDENCE_COMPLETE,
            "research_eligibility_policy_state": POLICY_STATE_APPROVED,
            "quarantined_dates": [],
            "n_quarantined_calendar_dates": 0,
            "structural_quarantine": {},
            "bound_identities": "AUTO",   # filled in by _evidence_env
            "proposal": src["proposal"],
            "mbo_sessions_per_partition": src["mbo_sessions_per_partition"],
            "mbo_blocks_per_partition": src["mbo_blocks_per_partition"],
            "checks": src["checks"],
            "activation_requires": ["a separately committed approval entry",
                                    "config/data/partitions_active.yaml"],
            "status": "PASS",
        }
        doc.update(over)
        return doc

    def test_valid_evidence_accepted(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(tmp_path, self._proposal())
        _verify_activation_evidence(parts, repo_root, data_root)

    def test_live_provisional_proposal_rejected(self, tmp_path):
        # THE reproduced audit finding: a candidate with the EXACT current
        # provisional states must fail closed even with matching hashes.
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._candidate(
            state="PROPOSED_NOT_ACTIVE",
            activation_ready=False,
            calendar_verification_state="PROVISIONAL_DOCUMENT_VERIFICATION_PENDING",
        )
        parts, repo_root, data_root = self._evidence_env(tmp_path,
                                                         candidate_doc=doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="can never activate"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_relabelled_neutral_proposal_rejected(self, tmp_path):
        # The neutral proposal must NEVER be overwritten or relabelled as the
        # candidate: a single artifact can never be both the mechanical source
        # and the approved candidate.
        from nqresearch.holdout import (
            CANDIDATE_STATE_READY,
            _verify_activation_evidence,
        )

        doc = self._proposal(state=CANDIDATE_STATE_READY)
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="must remain independently identifiable"):
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

    def test_candidate_hash_mismatch_fails(self, tmp_path):
        # The candidate is bound by its OWN identity, separately from the
        # neutral proposal: a fabricated candidate SHA fails here.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, declared_candidate_sha="c" * 64)
        with pytest.raises(PartitionsNotActiveError,
                           match="actual activation candidate"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_missing_candidate_artifact_fails(self, tmp_path):
        from nqresearch.holdout import (
            CANDIDATE_ARTIFACT_FILENAME,
            _verify_activation_evidence,
        )

        parts, repo_root, data_root = self._evidence_env(tmp_path)
        (data_root / "qa" / "m0_closeout" / CANDIDATE_ARTIFACT_FILENAME).unlink()
        with pytest.raises(PartitionsNotActiveError,
                           match="activation candidate"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_range_mismatch_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._candidate()
        doc["proposal"]["HOLDOUT"]["start"] = "2099-06-02"
        parts, repo_root, data_root = self._evidence_env(tmp_path,
                                                         candidate_doc=doc)
        with pytest.raises(PartitionsNotActiveError, match="exactly equal"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_proposal_range_divergence_fails(self, tmp_path):
        # The candidate, the neutral proposal and the active configuration
        # must all describe the SAME partitions.
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal()
        doc["proposal"]["SELECTION"]["end"] = "2099-05-28"
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="exactly equal the neutral proposal"):
            _verify_activation_evidence(parts, repo_root, data_root)

    @pytest.mark.parametrize("mutation,match", [
        ({"quarantined_dates": ["2099-01-01"],
          "n_quarantined_calendar_dates": 1}, "quarantined dates"),
        ({"evidence_disposition": "PENDING_DATES_QUARANTINED"},
         "evidence disposition"),
        ({"research_eligibility_policy_state": "SOMETHING_ELSE"},
         "policy state"),
        ({"structural_quarantine": {"n_quarantined": 10}},
         "structural-quarantine facts"),
        ({"mbo_sessions_per_partition": {"DEV": 99}},
         "mbo_sessions_per_partition"),
        ({"checks": [{"check": "boundaries_on_trading_days",
                      "status": "PASS", "detail": "synthetic"}]},
         "structural checks"),
    ])
    def test_candidate_substance_must_match_recomputed_evidence(
            self, tmp_path, mutation, match):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, candidate_doc=self._candidate(**mutation))
        with pytest.raises(PartitionsNotActiveError, match=match):
            _verify_activation_evidence(parts, repo_root, data_root)

    @pytest.mark.parametrize("field", [
        "coverage_artifact_sha256", "partition_proposal_sha256",
        "effective_calendar_sha256", "research_eligibility_sha256",
    ])
    def test_candidate_identity_divergence_fails(self, tmp_path, field):
        # The candidate's own hash and approval entry are BOTH consistent
        # here, so the failure is proven to come from the eight-identity
        # binding rather than from a stale hash.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, bound_identity_override={field: "0" * 64})
        with pytest.raises(PartitionsNotActiveError,
                           match=f"candidate binds {field}"):
            _verify_activation_evidence(parts, repo_root, data_root)

    @pytest.mark.parametrize("mutation", [
        {"unexpected_field": True},
        {"bound_identities": {"invented_sha256": "0" * 64}},
        {"n_quarantined_calendar_dates": 3},
        {"activation_requires": []},
        {"status": "WARN"},
    ])
    def test_candidate_strict_schema_rejects_malformed_substance(
            self, tmp_path, mutation):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, candidate_doc=self._candidate(**mutation))
        with pytest.raises(PartitionsNotActiveError,
                           match="candidate substance is not valid"):
            _verify_activation_evidence(parts, repo_root, data_root)

    # NESTED strictness: an invented field one level down must not ride along
    # inside a structural check or inside the FORWARD descriptor.
    def _nested(self, **over):
        doc = self._candidate()
        for key, value in over.items():
            doc[key] = value
        return doc

    @pytest.mark.parametrize("invented", [
        {"severity": "low"}, {"status_note": "ok"}, {"waived": True},
    ])
    def test_invented_field_inside_a_check_is_refused(self, tmp_path,
                                                     invented):
        from nqresearch.holdout import _verify_activation_evidence

        checks = [dict(c) for c in self._proposal()["checks"]]
        checks[0].update(invented)
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, candidate_doc=self._nested(checks=checks))
        with pytest.raises(PartitionsNotActiveError,
                           match="candidate substance is not valid"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_check_missing_detail_is_refused(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        checks = [{k: v for k, v in c.items() if k != "detail"}
                  for c in self._proposal()["checks"]]
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, candidate_doc=self._nested(checks=checks))
        with pytest.raises(PartitionsNotActiveError,
                           match="candidate substance is not valid"):
            _verify_activation_evidence(parts, repo_root, data_root)

    @pytest.mark.parametrize("invented", [
        {"end": "2099-12-31"}, {"eligible": True}, {"trading_days": 7},
    ])
    def test_invented_field_inside_forward_is_refused(self, tmp_path,
                                                      invented):
        from nqresearch.holdout import _verify_activation_evidence

        proposal = {k: dict(v) for k, v in self._proposal()["proposal"].items()}
        proposal["FORWARD"].update(invented)
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, candidate_doc=self._nested(proposal=proposal))
        with pytest.raises(PartitionsNotActiveError,
                           match="candidate substance is not valid"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_every_candidate_submodel_forbids_extras(self):
        # The PA-0003 claim must be TRUE of every declared model.
        import inspect

        import nqresearch.holdout as h

        models = [h.ActivationCandidate, h._CandidateProposal,
                  h._CandidateRange, h._CandidateForward, h._CandidateCheck,
                  h._CandidateIdentities]
        for m in models:
            assert m.model_config.get("extra") == "forbid", m.__name__
        # ...and every mapping-typed field must be covered by an exact-equality
        # comparison in the verifier, since the schema cannot constrain it.
        free_form = {name for name, f in h.ActivationCandidate.model_fields.items()
                     if f.annotation is dict}
        assert free_form == {"structural_quarantine",
                             "mbo_sessions_per_partition",
                             "mbo_blocks_per_partition"}, free_form
        src = inspect.getsource(h._verify_activation_evidence)
        for name in free_form:
            assert name in src, name

    @pytest.mark.parametrize("mutation,match", [
        ({"generation_git_clean": False}, "generation_git_clean"),
        ({"git_sha": "b" * 40}, "commit object"),
        ({"config_hash": "0" * 64}, "different effective configuration"),
        ({"artifact": "partition_proposal"},
         "not a partition_activation_candidate"),
    ])
    def test_candidate_envelope_and_type_required(self, tmp_path, mutation,
                                                  match):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, candidate_doc={**self._candidate(), **mutation})
        with pytest.raises(PartitionsNotActiveError, match=match):
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

        doc = self._candidate(state="PROPOSED_NOT_ACTIVE",
                              activation_ready=True)
        parts, repo_root, data_root = self._evidence_env(tmp_path,
                                                         candidate_doc=doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="READY_FOR_ACTIVATION_APPROVAL"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_candidate_cannot_self_certify_activation(self, tmp_path):
        # A generated artifact declaring itself activation-ready must be
        # REFUSED: activation is conferred only by the human-approval audit
        # entry plus the active configuration.
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._candidate(activation_ready=True)
        parts, repo_root, data_root = self._evidence_env(tmp_path,
                                                         candidate_doc=doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="NEVER self-certify"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_neutral_proposal_cannot_self_certify_activation(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal(activation_ready=True)
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="NEVER self-certify"):
            _verify_activation_evidence(parts, repo_root, data_root)

    @pytest.mark.parametrize("bad", [False, None, "true", 1, 0])
    def test_structural_ready_must_be_boolean_true(self, tmp_path, bad):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._candidate(structural_ready=bad)
        parts, repo_root, data_root = self._evidence_env(tmp_path,
                                                         candidate_doc=doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="structural_ready"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_approved_state_with_pending_calendar_rejected(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._candidate(
            calendar_verification_state="PROVISIONAL_DOCUMENT_VERIFICATION_PENDING"
        )
        parts, repo_root, data_root = self._evidence_env(tmp_path,
                                                         candidate_doc=doc)
        with pytest.raises(PartitionsNotActiveError, match="contradicts"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_missing_expected_group_fails(self, tmp_path):
        import conftest as fx
        from nqresearch.holdout import (
            EXPECTED_BASELINE_GROUPS,
            _verify_activation_evidence,
        )

        matrix_doc, _ = fx.synthetic_matrix_doc(
            tmp_path / "dataroot" / "reference" / "cme_calendar")
        groups = fx.overrides_groups_for(
            matrix_doc, EXPECTED_BASELINE_GROUPS)[:-1]  # one missing
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), matrix_doc=matrix_doc, groups=groups
        )
        with pytest.raises(PartitionsNotActiveError, match="nine-group"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_duplicate_and_unexpected_group_fail(self, tmp_path):
        import conftest as fx
        from nqresearch.holdout import (
            EXPECTED_BASELINE_GROUPS,
            _verify_activation_evidence,
        )

        matrix_doc, _ = fx.synthetic_matrix_doc(
            tmp_path / "dataroot" / "reference" / "cme_calendar")
        base = fx.overrides_groups_for(matrix_doc, EXPECTED_BASELINE_GROUPS)
        dup = base + [dict(base[0])]
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), matrix_doc=matrix_doc, groups=dup
        )
        with pytest.raises(PartitionsNotActiveError, match="duplicate"):
            _verify_activation_evidence(parts, repo_root, data_root)
        matrix_doc2, _ = fx.synthetic_matrix_doc(
            (tmp_path / "b") / "dataroot" / "reference" / "cme_calendar")
        extra = fx.overrides_groups_for(matrix_doc2, EXPECTED_BASELINE_GROUPS)
        extra = extra + [{"holiday_group": "Invented Day (2099-01-01)",
                          "status": "DOCUMENT_VERIFIED", "dates": {}}]
        parts2, repo_root2, data_root2 = self._evidence_env(
            tmp_path / "b", self._proposal(), matrix_doc=matrix_doc2,
            groups=extra
        )
        with pytest.raises(PartitionsNotActiveError, match="nine-group"):
            _verify_activation_evidence(parts2, repo_root2, data_root2)

    def test_rollup_mismatch_fails_even_when_complete(self, tmp_path):
        # One verified year must NEVER promote a multi-year group: overrides
        # claiming DOCUMENT_VERIFIED for a group whose conservative matrix
        # roll-up is weaker (here TRIANGULATED) fail closed even though every
        # date is resolved.
        import conftest as fx
        from nqresearch.calendar_evidence import STATE_TRIANGULATED
        from nqresearch.holdout import (
            EXPECTED_BASELINE_GROUPS,
            _verify_activation_evidence,
        )

        matrix_doc, _ = fx.synthetic_matrix_doc(
            tmp_path / "dataroot" / "reference" / "cme_calendar",
            date_states={"2024-09-02": STATE_TRIANGULATED})
        groups = fx.overrides_groups_for(matrix_doc, EXPECTED_BASELINE_GROUPS)
        for g in groups:
            if g["holiday_group"].startswith("Labor Day"):
                g["status"] = "DOCUMENT_VERIFIED"  # stronger than roll-up
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), matrix_doc=matrix_doc, groups=groups
        )
        with pytest.raises(PartitionsNotActiveError, match="rolls up"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_pending_but_unquarantined_date_blocks_activation(self, tmp_path):
        # PA-0002: a pending date blocks unless it is covered EXACTLY by the
        # reviewed quarantine policy. Here the policy covers nothing.
        import conftest as fx
        from nqresearch.calendar_evidence import STATE_PENDING
        from nqresearch.holdout import _verify_activation_evidence

        matrix_doc, _ = fx.synthetic_matrix_doc(
            tmp_path / "dataroot" / "reference" / "cme_calendar",
            date_states={"2025-06-19": STATE_PENDING})
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), matrix_doc=matrix_doc,
            policy_dates=[]
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="does not exactly cover"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_verified_date_cannot_be_silently_quarantined(self, tmp_path):
        # A policy naming a DOCUMENT_VERIFIED date (nothing pending) fails.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), policy_dates=["2026-01-19"]
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="never silently quarantined"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_conflict_cannot_be_resolved_by_quarantine(self, tmp_path):
        import conftest as fx
        from nqresearch.calendar_evidence import STATE_CONFLICT
        from nqresearch.holdout import _verify_activation_evidence

        matrix_doc, _ = fx.synthetic_matrix_doc(
            tmp_path / "dataroot" / "reference" / "cme_calendar")
        for d in matrix_doc["dates"]:
            if d["date"] == "2025-06-19":
                d["state"] = STATE_CONFLICT
                d["agreement"] = "DISCREPANCY"
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), matrix_doc=matrix_doc,
            policy_dates=["2025-06-19"]
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="NEVER be resolved by quarantine"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_wrong_matrix_hash_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), wrong_matrix_sha=True
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="evidence matrix"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_wrong_correspondence_hash_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), wrong_email_sha=True
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="correspondence"):
            _verify_activation_evidence(parts, repo_root, data_root)

    @pytest.mark.parametrize("omit", [("candidate",), ("proposal",),
                                      ("calendar",), ("matrix",), ("email",),
                                      ("policy",), ("coverage",), ("blocks",),
                                      ("front",), ("decision",),
                                      ("matrix", "email")])
    def test_audit_entry_missing_evidence_hashes_fails(self, tmp_path, omit):
        # Human approval must bind the EXACT candidate identity and all eight
        # dependency identities: an entry missing any required machine-readable
        # field fails closed.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), audit_omit=omit
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="missing the machine-readable"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_tampered_evidence_file_fails(self, tmp_path):
        # Changed evidence bytes (email or document) fail the hash check.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal()
        )
        (data_root / "reference" / "cme_calendar" / "email.eml").write_bytes(
            b"tampered email"
        )
        with pytest.raises(PartitionsNotActiveError, match="hash mismatch"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_missing_coverage_artifact_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal()
        )
        (data_root / "qa" / "m0_closeout"
         / "mbp1_full_history_coverage.json").unlink()
        with pytest.raises(PartitionsNotActiveError,
                           match="coverage artifact missing"):
            _verify_activation_evidence(parts, repo_root, data_root)

    @pytest.mark.parametrize("state", [
        "PROPOSED_PENDING_INDEPENDENT_REVIEW",
        "IMPLEMENTED_PENDING_ACTIVATION_APPROVAL",
    ])
    def test_unapproved_policy_lifecycle_blocks_activation(self, tmp_path,
                                                           state):
        # Only APPROVED_FOR_ACTIVATION may ever activate — even with an
        # otherwise activation-ready proposal.
        import conftest as fx
        from nqresearch.holdout import _verify_activation_evidence

        matrix_doc, _ = fx.synthetic_matrix_doc(
            tmp_path / "dataroot" / "reference" / "cme_calendar")
        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), matrix_doc=matrix_doc,
            policy_doc=fx.eligibility_policy_doc("0" * 64, [], status=state),
        )
        with pytest.raises(PartitionsNotActiveError):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_policy_hash_mismatch_fails_in_evidence_complete_branch(
            self, tmp_path):
        # The policy hash is bound in BOTH dispositions, not only quarantine.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), wrong_policy_sha=True
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="research-eligibility"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_proposal_state_mismatch_fails_in_evidence_complete_branch(
            self, tmp_path):
        # An evidence-complete disposition may not hide behind a provisional
        # label either.
        from nqresearch.calendar_evidence import (
            CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
        )
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._candidate(
            calendar_verification_state=CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED
        )
        parts, repo_root, data_root = self._evidence_env(tmp_path,
                                                         candidate_doc=doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="does not match the actual disposition"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_tampered_structural_artifact_fails_by_hash(self, tmp_path):
        import json

        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        p = data_root / "qa" / "m0_closeout" / "mbo_blocks_frozen.json"
        doc = json.loads(p.read_text())
        doc["blocks"] = []          # a session silently removed
        doc["n_blocks"] = 0
        p.write_text(json.dumps(doc))
        with pytest.raises(PartitionsNotActiveError,
                           match="identity mismatch"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_declared_structural_hash_mismatch_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(), wrong_blocks_sha=True)
        with pytest.raises(PartitionsNotActiveError,
                           match="identity mismatch"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_missing_structural_artifact_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        (data_root / "qa" / "m0_closeout"
         / "mbp1_front_contract_series.json").unlink()
        with pytest.raises(PartitionsNotActiveError,
                           match="structural artifact missing"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_wrong_artifact_type_fails(self, tmp_path):
        import json

        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        # Substitute a different artifact whose declared hash we also update,
        # proving the TYPE check is independent of the hash check.
        p = data_root / "qa" / "m0_closeout" / "mbo_blocks_frozen.json"
        p.write_text(json.dumps({"artifact": "something_else",
                                 "status": "PASS", "blocks": [],
                                 "n_blocks": 0}))
        import hashlib as _h
        parts = parts.model_copy(update={
            "mbo_blocks_sha256": _h.sha256(p.read_bytes()).hexdigest()})
        with pytest.raises(PartitionsNotActiveError, match="declares artifact"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def _mutate_artifact(self, data_root, fname, **fields):
        """Rewrite an artifact and re-declare its hash, so the failure is
        proven to come from content, never a stale hash."""
        import hashlib as _h
        import json as _j

        p = data_root / "qa" / "m0_closeout" / fname
        doc = _j.loads(p.read_text())
        doc.update(fields)
        p.write_text(_j.dumps(doc))
        return _h.sha256(p.read_bytes()).hexdigest()

    @pytest.mark.parametrize("fname,attr", [
        ("mbo_blocks_frozen.json", "mbo_blocks_sha256"),
        ("mbp1_front_contract_series.json", "front_contract_series_sha256"),
    ])
    def test_warn_status_rejected_for_pass_only_artifacts(self, tmp_path,
                                                          fname, attr):
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        sha = self._mutate_artifact(data_root, fname, status="WARN")
        parts = parts.model_copy(update={attr: sha})
        with pytest.raises(PartitionsNotActiveError,
                           match="permitted statuses"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_substantive_coverage_change_trips_matrix_substance_digest(
            self, tmp_path):
        # A SUBSTANTIVE coverage change invalidates the matrix substance
        # digest, which is checked before any date-level claim is trusted.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        sha = self._mutate_artifact(data_root,
                                    "mbp1_full_history_coverage.json",
                                    status="PASS")
        parts = parts.model_copy(update={"coverage_artifact_sha256": sha})
        with pytest.raises(PartitionsNotActiveError,
                           match="SUBSTANCE digest mismatch"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_wrong_whole_file_sha_rejected_even_when_substance_matches(
            self, tmp_path):
        # THE two-identity guarantee: an envelope-only edit keeps the
        # substance digest valid, but the exact whole-file identity bound by
        # ActivePartitions must still match.
        import json as _j

        from nqresearch.calendar_evidence import coverage_substance_sha256
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        p = (data_root / "qa" / "m0_closeout"
             / "mbp1_full_history_coverage.json")
        before = coverage_substance_sha256(_j.loads(p.read_text()))
        # envelope-only mutation: substance digest unchanged, file SHA changes
        self._mutate_artifact(data_root, "mbp1_full_history_coverage.json",
                              generated_at_utc="2099-01-01T00:00:00Z")
        after = coverage_substance_sha256(_j.loads(p.read_text()))
        assert after == before  # substance identity survives
        with pytest.raises(PartitionsNotActiveError,
                           match="identity mismatch"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def _structural_env(self, tmp_path, parts, data_root, sha):
        """Stub matrix + proposal that agree with a mutated coverage artifact
        on BOTH identities (exact file SHA and substance digest), so the
        coverage ACCEPTANCE rule is what fires rather than an earlier
        identity check."""
        import json as _j
        import types

        from nqresearch.calendar_evidence import (
            COVERAGE_SUBSTANCE_ALGORITHM,
            coverage_substance_sha256,
        )

        cov_doc = _j.loads(
            (data_root / "qa" / "m0_closeout"
             / "mbp1_full_history_coverage.json").read_text())
        parts = parts.model_copy(update={"coverage_artifact_sha256": sha})
        stub_matrix = types.SimpleNamespace(meta={"observed_reference": {
            "substance_digest_algorithm": COVERAGE_SUBSTANCE_ALGORITHM,
            "substance_sha256": coverage_substance_sha256(cov_doc)}})
        proposal = {"research_eligibility_binding": {
            "structural_artifact_sha256": {
                "coverage_artifact_sha256": sha,
                "mbo_blocks_sha256": parts.mbo_blocks_sha256,
                "front_contract_series_sha256":
                    parts.front_contract_series_sha256}}}
        return parts, stub_matrix, proposal

    def test_incoherent_coverage_pass_rejected(self, tmp_path):
        # PASS is a PERMITTED coverage status, but only when coherent: here
        # the understood WARN check is still present, so it must fail.
        from nqresearch.holdout import _verify_structural_artifacts

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        sha = self._mutate_artifact(data_root,
                                    "mbp1_full_history_coverage.json",
                                    status="PASS")
        parts, matrix, proposal = self._structural_env(tmp_path, parts,
                                                       data_root, sha)
        with pytest.raises(PartitionsNotActiveError,
                           match="not in the understood state"):
            _verify_structural_artifacts(parts, matrix, data_root, repo_root,
                                         proposal)

    def test_coherent_coverage_pass_accepted(self, tmp_path):
        # A substantively coherent all-PASS coverage artifact IS acceptable.
        from nqresearch.holdout import _verify_structural_artifacts

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        p = data_root / "qa" / "m0_closeout" / "mbp1_full_history_coverage.json"
        import hashlib as _h
        import json as _j
        doc = _j.loads(p.read_text())
        doc["status"] = "PASS"
        doc["missing_pre_rth_short_sessions"] = []
        doc["checks"] = [c for c in doc["checks"]
                         if c["check"] != "pre_rth_short_sessions_without_data"]
        p.write_text(_j.dumps(doc))
        sha = _h.sha256(p.read_bytes()).hexdigest()
        parts, matrix, proposal = self._structural_env(tmp_path, parts,
                                                       data_root, sha)
        _verify_structural_artifacts(parts, matrix, data_root, repo_root,
                                     proposal)  # must not raise

    @pytest.mark.parametrize("mutation", [
        {"n_fail": 2},
        {"missing_sessions": ["2025-05-05"]},
        {"cross_file_order_violations": 1},
        {"missing_pre_rth_short_sessions": ["2099-12-31"]},
    ])
    def test_unsound_coverage_rejected_at_activation(self, tmp_path,
                                                     mutation):
        from nqresearch.holdout import _verify_structural_artifacts

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        sha = self._mutate_artifact(data_root,
                                    "mbp1_full_history_coverage.json",
                                    **mutation)
        parts, matrix, proposal = self._structural_env(tmp_path, parts,
                                                       data_root, sha)
        with pytest.raises(PartitionsNotActiveError,
                           match="not in the understood state"):
            _verify_structural_artifacts(parts, matrix, data_root, repo_root,
                                         proposal)

    @pytest.mark.parametrize("mutation,match", [
        ({"generation_git_clean": None}, "generation_git_clean"),
        ({"generation_git_clean": False}, "generation_git_clean"),
        ({"generation_git_clean": "true"}, "generation_git_clean"),
        ({"git_sha": None}, "git_sha"),
        ({"git_sha": "b" * 40}, "commit object"),
        ({"config_hash": "0" * 64}, "different effective configuration"),
        ({"audit_code_hash": "0" * 64}, "different package code"),
    ])
    def test_envelope_integrity_required_for_activation(self, tmp_path,
                                                        mutation, match):
        # Legacy envelopes (no generation_git_clean), dirty generation,
        # non-ancestor SHAs and stale config/code bindings all fail.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        sha = self._mutate_artifact(data_root, "mbo_blocks_frozen.json",
                                    **mutation)
        parts = parts.model_copy(update={"mbo_blocks_sha256": sha})
        with pytest.raises(PartitionsNotActiveError, match=match):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_proposal_missing_embedded_structural_binding_fails(self,
                                                                tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal()
        doc["research_eligibility_binding"] = {}  # no embedded identities
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="embeds no structural_artifact_sha256"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_embedded_vs_active_structural_hash_mismatch_fails(self,
                                                               tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal()
        doc["research_eligibility_binding"] = {
            "structural_artifact_sha256": {
                "coverage_artifact_sha256": "5" * 64,
                "mbo_blocks_sha256": "6" * 64,
                "front_contract_series_sha256": "7" * 64,
            }
        }
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError,
                           match="embedded in the approved partition"):
            _verify_activation_evidence(parts, repo_root, data_root)

    @pytest.mark.parametrize("mutation,match", [
        ({"generation_git_clean": None}, "generation_git_clean"),
        ({"generation_git_clean": False}, "generation_git_clean"),
        ({"generation_git_clean": "true"}, "generation_git_clean"),
        ({"git_sha": None}, "git_sha"),
        ({"git_sha": "zz"}, "git_sha"),
        ({"git_sha": "b" * 40}, "commit object"),
        ({"config_hash": "0" * 64}, "different effective configuration"),
        ({"audit_code_hash": "0" * 64}, "different package code"),
        ({"artifact": "something_else"}, "not a partition_proposal"),
    ])
    def test_proposal_envelope_required_for_activation(self, tmp_path,
                                                       mutation, match):
        # The proposal itself must carry a clean CURRENT envelope before any
        # of its status/checks/state/ranges/identities are trusted.
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal()
        doc.update(mutation)
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        with pytest.raises(PartitionsNotActiveError, match=match):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_legacy_proposal_envelope_missing_fields_rejected(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        doc = self._proposal()
        parts, repo_root, data_root = self._evidence_env(tmp_path, doc)
        # strip the whole envelope, as a pre-policy artifact would lack it
        import hashlib as _h
        import json as _j

        ppath = data_root / "qa" / "m0_closeout" / "partition_proposal.json"
        d = _j.loads(ppath.read_text())
        for k in ("generation_git_clean", "git_sha", "config_hash",
                  "audit_code_hash", "restamp_note"):
            d.pop(k, None)
        ppath.write_text(_j.dumps(d))
        parts = parts.model_copy(update={
            "partition_proposal_sha256":
                _h.sha256(ppath.read_bytes()).hexdigest()})
        with pytest.raises(PartitionsNotActiveError,
                           match="generation_git_clean"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_clean_proposal_still_valid_after_audit_only_descendant_commit(
            self, tmp_path):
        # A proposal generated at an implementation commit must remain
        # acceptable once an audit-log-only commit has moved HEAD past it.
        import subprocess

        from nqresearch import paths
        from nqresearch.holdout import _verify_artifact_envelope

        parent = subprocess.run(
            ["git", "-C", str(paths.ROOT), "rev-parse", "HEAD~1"],
            capture_output=True, text=True).stdout.strip()
        head = subprocess.run(
            ["git", "-C", str(paths.ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True).stdout.strip()
        assert parent and parent != head
        import conftest as _fx
        doc = {**_fx.clean_envelope(), "git_sha": parent,
               "artifact": "partition_proposal"}
        _verify_artifact_envelope("partition_proposal.json", doc)  # no raise

    def test_synthetic_legacy_envelope_is_activation_ineligible(self):
        # A SYNTHETIC pre-policy artifact (no generation_git_clean, stale
        # config/code hashes) must be activation-ineligible. Deliberately
        # synthetic: this invariant must not depend on the mutable live
        # artifacts still being un-regenerated.
        from nqresearch.holdout import _verify_artifact_envelope

        legacy = {
            "artifact": "mbo_blocks_frozen", "status": "PASS",
            "generated_at_utc": "2026-08-18T15:31:30Z",
            "nqresearch_version": "0.1.0",
            "git_sha": "3c7aee5e0f240b69d136ff341b608644dafc7a52",
            "audit_code_hash": "0" * 64, "config_hash": "0" * 64,
            "data_root": "D:\\nq-research\\data",
            "blocks": [], "n_blocks": 0,
        }
        assert "generation_git_clean" not in legacy
        with pytest.raises(PartitionsNotActiveError,
                           match="generation_git_clean"):
            _verify_artifact_envelope("mbo_blocks_frozen.json", legacy)

    def test_exact_and_substance_identities_are_checked_independently(
            self, tmp_path):
        # The two coverage identities are never compared with each other:
        # a wrong exact-file SHA fails on identity, and a wrong matrix
        # substance digest fails on substance — separately.
        import types

        from nqresearch.calendar_evidence import COVERAGE_SUBSTANCE_ALGORITHM
        from nqresearch.holdout import (
            _verify_activation_evidence,
            _verify_structural_artifacts,
        )

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        bad_file = parts.model_copy(
            update={"coverage_artifact_sha256": "9" * 64})
        with pytest.raises(PartitionsNotActiveError, match="identity mismatch"):
            _verify_activation_evidence(bad_file, repo_root, data_root)

        bad_matrix = types.SimpleNamespace(meta={"observed_reference": {
            "substance_digest_algorithm": COVERAGE_SUBSTANCE_ALGORITHM,
            "substance_sha256": "8" * 64}})
        proposal = {"research_eligibility_binding": {
            "structural_artifact_sha256": {
                "coverage_artifact_sha256": parts.coverage_artifact_sha256,
                "mbo_blocks_sha256": parts.mbo_blocks_sha256,
                "front_contract_series_sha256":
                    parts.front_contract_series_sha256}}}
        with pytest.raises(PartitionsNotActiveError,
                           match="substance digest does not equal"):
            _verify_structural_artifacts(parts, bad_matrix, data_root,
                                         repo_root, proposal)

    @pytest.mark.parametrize("ref,match", [
        ({"substance_digest_algorithm": "coverage-substance-v0",
          "substance_sha256": "a" * 64}, "substance digest algorithm"),
        ({"substance_sha256": "a" * 64}, "substance digest algorithm"),
        ({"substance_digest_algorithm": "coverage-substance-v1"},
         "no valid coverage substance digest"),
        ({"substance_digest_algorithm": "coverage-substance-v1",
          "substance_sha256": "nothex"}, "no valid coverage substance digest"),
    ])
    def test_activation_rejects_bad_matrix_substance_declaration(
            self, tmp_path, ref, match):
        import types

        from nqresearch.holdout import _verify_structural_artifacts

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal())
        stub = types.SimpleNamespace(meta={"observed_reference": ref})
        proposal = {"research_eligibility_binding": {
            "structural_artifact_sha256": {
                "coverage_artifact_sha256": parts.coverage_artifact_sha256,
                "mbo_blocks_sha256": parts.mbo_blocks_sha256,
                "front_contract_series_sha256":
                    parts.front_contract_series_sha256}}}
        with pytest.raises(PartitionsNotActiveError, match=match):
            _verify_structural_artifacts(parts, stub, data_root, repo_root,
                                         proposal)

    def test_jan9_reference_wrong_hash_fails(self, tmp_path):
        # A well-formed but wrong Jan-9 document hash must not activate.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(),
            jan9_ref={"id": "cme-2025-01-09-mourning",
                      "document_sha256": "9" * 64},
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="does not match the verified"):
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
        with pytest.raises(PartitionsNotActiveError,
                           match="missing the machine-readable"):
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

    def test_pending_overrides_status_fails(self, tmp_path):
        # The live overrides status (PROVISIONAL_DOCUMENT_VERIFICATION_
        # PENDING) must block even when everything else is coherent.
        from nqresearch.holdout import _verify_activation_evidence

        parts, repo_root, data_root = self._evidence_env(
            tmp_path, self._proposal(),
            overrides_status="PROVISIONAL_DOCUMENT_VERIFICATION_PENDING",
        )
        with pytest.raises(PartitionsNotActiveError,
                           match="calendar-evidence status"):
            _verify_activation_evidence(parts, repo_root, data_root)

    def test_missing_proposal_artifact_fails(self, tmp_path):
        from nqresearch.holdout import _verify_activation_evidence

        repo_root, data_root = self._synthetic_repo(tmp_path)
        parts = _parts(SYNTH, tmp_path)
        (data_root / "qa" / "m0_closeout"
         / "partition_proposal.json").unlink(missing_ok=True)
        with pytest.raises(PartitionsNotActiveError, match="evidence missing"):
            _verify_activation_evidence(parts, repo_root, data_root)

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
