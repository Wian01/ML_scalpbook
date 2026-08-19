"""DuckDB experiment registry: §37 fields, deterministic IDs, immutability,
lifecycle, trial counting, retention, reproducibility (§47). Synthetic
metadata only â€” no market experiment is registered."""

import json

import pytest
import yaml
from pydantic import ValidationError

from nqresearch.experiments.models import (
    STATE_FAILED,
    STATE_PASSED,
    STATE_PLANNED,
    STATE_RUNNING,
    STATE_SUSPECT,
    PreRegistration,
)
from nqresearch.experiments.registry import (
    ExperimentRegistry,
    ImmutableSpecError,
    InvalidTransitionError,
    RegistryError,
)

SYNTHETIC = dict(
    research_question="synthetic question (foundation test only)",
    hypothesis="synthetic hypothesis",
    dataset_version="synthetic-ds-0",
    source_dataset_hashes={"synthetic-ds": "e3b0c44298fc1c149afbf4c8996fb924"
                                           "27ae41e4649b934ca495991b7852b855"},
    partition="SYNTHETIC",
    sample_table_version="st-0",
    feature_family_versions={"fam_a": "0.0-synthetic"},
    label_version="lbl-0",
    volatility_estimator_version="vol-0",
    horizon="60s",
    latency_ms=500,
    fold_scheme="walk-forward-synthetic",
    seeds=[1234],
    model_type="synthetic",
    hyperparameters={"depth": 1},
    primary_metric="synthetic_skill",
    secondary_metrics=["m2"],
    acceptance_criterion="synthetic criterion",
    kill_criteria=["synthetic kill"],
    cost_model_version="cost-0",
)


EMPTY_MANIFEST = {"outputs": [], "note": "synthetic/null run"}


@pytest.fixture()
def reg(tmp_path):
    r = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                           experiments_dir=tmp_path / "experiments")
    yield r
    r.close()


def _prereg(**over):
    return PreRegistration(**{**SYNTHETIC, **over})


class TestRegistration:
    def test_register_and_show(self, reg, tmp_path):
        exp_id = reg.register(_prereg())
        assert exp_id == "EXP-0001"
        info = reg.show(exp_id)
        assert info["status"] == STATE_PLANNED
        assert info["trial_number"] == 1
        assert info["prereg"]["horizon"] == "60s"
        assert (tmp_path / "experiments" / exp_id / "prereg.yaml").is_file()
        assert info["audit"][0]["event"] == "REGISTERED"

    def test_ids_deterministic_sequential(self, reg):
        assert [reg.register(_prereg()) for _ in range(3)] == \
            ["EXP-0001", "EXP-0002", "EXP-0003"]
        assert reg.trial_count() == 3

    def test_missing_required_field_rejected(self):
        bad = dict(SYNTHETIC)
        del bad["kill_criteria"]
        with pytest.raises(ValidationError):
            PreRegistration(**bad)

    def test_empty_required_field_rejected(self):
        with pytest.raises(ValidationError):
            _prereg(hypothesis="   ")

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            _prereg(surprise_field=1)

    def test_existing_directory_refused_no_overwrite(self, reg, tmp_path):
        (tmp_path / "experiments" / "EXP-0001").mkdir(parents=True)
        with pytest.raises(RegistryError, match="never reused"):
            reg.register(_prereg())

    def test_reproducibility_fields_captured(self, reg):
        info = reg.show(reg.register(_prereg()))
        repro = info["reproducibility"]
        for key in ("git_sha", "python_version", "os_platform",
                    "dependency_lock_sha256", "config_hash", "code_hash",
                    "random_seeds", "experiment_id"):
            assert key in repro
        assert repro["random_seeds"] == [1234]
        assert len(repro["dependency_lock_sha256"]) == 64


class TestLifecycle:
    def test_valid_paths(self, reg):
        for terminal in (STATE_PASSED, STATE_FAILED, "INCONCLUSIVE", STATE_SUSPECT):
            exp_id = reg.register(_prereg())
            reg.begin_run(exp_id)
            reg.transition(exp_id, terminal, outputs=EMPTY_MANIFEST)
            assert reg.show(exp_id)["status"] == terminal

    def test_planned_cannot_jump_to_terminal(self, reg):
        exp_id = reg.register(_prereg())
        with pytest.raises(InvalidTransitionError):
            reg.transition(exp_id, STATE_PASSED)

    def test_terminal_never_rewritten(self, reg):
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)
        reg.transition(exp_id, STATE_FAILED, outputs=EMPTY_MANIFEST)
        for attempt in (STATE_PASSED, STATE_RUNNING, STATE_PLANNED):
            with pytest.raises(InvalidTransitionError, match="never"):
                reg.transition(exp_id, attempt)

    def test_unknown_state_rejected(self, reg):
        exp_id = reg.register(_prereg())
        with pytest.raises(InvalidTransitionError):
            reg.transition(exp_id, "DONE")

    def test_running_cannot_return_to_planned(self, reg):
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)
        with pytest.raises(InvalidTransitionError):
            reg.transition(exp_id, STATE_PLANNED)

    def test_refused_transition_is_audited(self, reg):
        exp_id = reg.register(_prereg())
        with pytest.raises(InvalidTransitionError):
            reg.transition(exp_id, STATE_PASSED)
        events = [a["event"] for a in reg.show(exp_id)["audit"]]
        assert "TRANSITION_REFUSED" in events

    def test_failed_runs_remain_visible(self, reg):
        a = reg.register(_prereg())
        reg.begin_run(a)
        reg.transition(a, STATE_FAILED, outputs=EMPTY_MANIFEST)
        b = reg.register(_prereg())
        listing = reg.list()
        assert {r["experiment_id"] for r in listing} == {a, b}
        assert any(r["status"] == STATE_FAILED for r in listing)


class TestImmutability:
    def test_modified_prereg_yaml_blocks_transitions(self, reg, tmp_path):
        exp_id = reg.register(_prereg())
        yaml_path = tmp_path / "experiments" / exp_id / "prereg.yaml"
        doc = yaml.safe_load(yaml_path.read_text())
        doc["hypothesis"] = "retroactively rewritten hypothesis"
        yaml_path.write_text(yaml.safe_dump(doc))
        with pytest.raises(ImmutableSpecError, match="NEW experiment"):
            reg.begin_run(exp_id)
        # show() itself fails closed on the tampered record; the refusal audit
        # is inspected via the PRIVATE diagnostic accessor.
        with pytest.raises(ImmutableSpecError):
            reg.show(exp_id)
        events = [a["event"] for a in reg._show_unverified(exp_id)["audit"]]
        assert "TRANSITION_REFUSED" in events

    def test_new_configuration_is_new_experiment(self, reg):
        a = reg.register(_prereg())
        b = reg.register(_prereg(hyperparameters={"depth": 2}))
        assert a != b
        assert reg.trial_count() == 2  # every configuration counts as a trial


class TestSchemaAndPersistence:
    def test_schema_version_enforced(self, tmp_path):
        r = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")
        r._con.execute(
            "UPDATE registry_meta SET value='999' WHERE key='schema_version'"
        )
        r.close()
        with pytest.raises(RegistryError, match="migration required"):
            ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")

    def test_state_survives_reopen(self, tmp_path):
        r = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")
        exp_id = r.register(_prereg())
        r.begin_run(exp_id)
        r.close()
        r2 = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                experiments_dir=tmp_path / "experiments")
        assert r2.show(exp_id)["status"] == STATE_RUNNING
        assert r2.trial_count() == 1
        r2.close()

    def test_audit_projection_matches_authoritative_chain(self, reg, tmp_path):
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)
        reg.transition(exp_id, STATE_PASSED, outputs=EMPTY_MANIFEST)
        proj = json.loads(
            (tmp_path / "experiments" / exp_id / "audit_projection.json").read_text()
        )
        assert "MATERIALIZED PROJECTION" in proj["note"]
        events = proj["events"]
        assert [a["event"] for a in events] == \
            ["REGISTERED", "TRANSITION", "TRANSITION"]
        assert [a["seq"] for a in events] == sorted(a["seq"] for a in events)
        assert all("record_hash" in a and "prev_hash" in a for a in events)

    def test_audit_chain_tamper_detected_and_blocks_everything(self, reg):
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)
        assert reg.verify_audit_chain() >= 2
        reg._con.execute(
            "UPDATE lifecycle_audit SET note='tampered' WHERE seq=1"
        )
        with pytest.raises(RegistryError, match="chain broken"):
            reg.verify_audit_chain()
        # A corrupted chain blocks show, registration, and transitions.
        with pytest.raises(RegistryError, match="chain broken"):
            reg.show(exp_id)
        with pytest.raises(RegistryError, match="chain broken"):
            reg.register(_prereg())
        with pytest.raises(RegistryError, match="chain broken"):
            reg.transition(exp_id, STATE_PASSED)
        with pytest.raises(RegistryError, match="chain broken"):
            reg.list()
        with pytest.raises(RegistryError, match="chain broken"):
            reg.trial_count()

    def test_corrupted_chain_blocks_reopen_and_recovery(self, tmp_path):
        r = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")
        r.register(_prereg())
        r._con.execute("UPDATE lifecycle_audit SET note='x' WHERE seq=1")
        r.close()
        with pytest.raises(RegistryError, match="chain broken"):
            ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")

    def test_single_writer_enforced(self, tmp_path):
        r = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")
        with pytest.raises(RegistryError, match="single-writer"):
            ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")
        r.close()

    def test_no_public_verification_bypass_on_show(self, reg):
        import inspect

        assert "verify" not in inspect.signature(reg.show).parameters


class TestFailClosedSpecRecords:
    """Independent-audit remediation: missing/invalid records fail closed."""

    def test_deleted_prereg_blocks_begin_run(self, reg, tmp_path):
        exp_id = reg.register(_prereg())
        (tmp_path / "experiments" / exp_id / "prereg.yaml").unlink()
        with pytest.raises(ImmutableSpecError, match="MISSING"):
            reg.begin_run(exp_id)
        assert reg._show_unverified(exp_id)["status"] == STATE_PLANNED

    def test_deleted_prereg_blocks_show(self, reg, tmp_path):
        exp_id = reg.register(_prereg())
        (tmp_path / "experiments" / exp_id / "prereg.yaml").unlink()
        with pytest.raises(ImmutableSpecError):
            reg.show(exp_id)

    def test_invalid_yaml_fails_closed(self, reg, tmp_path):
        exp_id = reg.register(_prereg())
        (tmp_path / "experiments" / exp_id / "prereg.yaml").write_text("a: [broken")
        with pytest.raises(ImmutableSpecError):
            reg.begin_run(exp_id)

    def test_changed_types_fail_closed(self, reg, tmp_path):
        exp_id = reg.register(_prereg())
        p = tmp_path / "experiments" / exp_id / "prereg.yaml"
        doc = yaml.safe_load(p.read_text())
        doc["latency_ms"] = "five hundred"
        p.write_text(yaml.safe_dump(doc))
        with pytest.raises(ImmutableSpecError):
            reg.begin_run(exp_id)

    def test_extra_fields_fail_closed(self, reg, tmp_path):
        exp_id = reg.register(_prereg())
        p = tmp_path / "experiments" / exp_id / "prereg.yaml"
        doc = yaml.safe_load(p.read_text())
        doc["smuggled"] = True
        p.write_text(yaml.safe_dump(doc))
        with pytest.raises(ImmutableSpecError):
            reg.begin_run(exp_id)

    def test_substituted_directory_fails_closed(self, reg, tmp_path):
        a = reg.register(_prereg())
        b = reg.register(_prereg(hypothesis="different synthetic hypothesis"))
        import shutil as _sh

        dir_a = tmp_path / "experiments" / a
        _sh.rmtree(dir_a)
        _sh.copytree(tmp_path / "experiments" / b, dir_a)
        with pytest.raises(ImmutableSpecError):
            reg.begin_run(a)


class TestCrashSafety:
    def test_file_write_failure_leaves_no_orphan_and_no_row(self, tmp_path,
                                                           monkeypatch):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        import nqresearch.experiments.registry as regmod

        def boom(*a, **k):
            raise OSError("injected fs failure")

        monkeypatch.setattr(regmod.yaml, "safe_dump", boom)
        with pytest.raises(OSError):
            reg.register(_prereg())
        monkeypatch.undo()
        assert reg.trial_count() == 0
        assert not (tmp_path / "experiments" / "EXP-0001").exists()
        # consumed sequence value is never reused: next id has a gap
        next_id = reg.register(_prereg())
        assert next_id == "EXP-0002"
        reg.close()

    def test_committed_pending_state_recovered_on_reopen(self, tmp_path):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        exp_dir = tmp_path / "experiments" / exp_id
        # Simulate crash between DB commit and finalize: durable PENDING state
        # in the DB, files incomplete on disk.
        reg._con.execute(
            "UPDATE experiments SET record_state='PENDING_PROJECTION' "
            "WHERE experiment_id=?", [exp_id],
        )
        (exp_dir / "prereg.yaml").unlink()
        reg.close()
        r2 = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                experiments_dir=tmp_path / "experiments")
        assert (exp_dir / "prereg.yaml").is_file()
        info = r2.show(exp_id)
        assert info["record_state"] == "FINALIZED"
        assert "RECOVERED_PROJECTION" in [a["event"] for a in info["audit"]]
        r2.begin_run(exp_id)  # spec verifies clean after recovery
        r2.close()

    def test_finalized_record_deleted_is_tampering_not_restored(self, tmp_path):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        import shutil as _sh

        _sh.rmtree(tmp_path / "experiments" / exp_id)  # delete FINALIZED record
        reg.close()
        r2 = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                experiments_dir=tmp_path / "experiments")
        # Never reconstructed; fails closed on use.
        assert not (tmp_path / "experiments" / exp_id).exists()
        with pytest.raises(ImmutableSpecError, match="MISSING"):
            r2.begin_run(exp_id)
        with pytest.raises(ImmutableSpecError):
            r2.show(exp_id)
        r2.close()

    def _assert_recovered_clean(self, tmp_path, exp_id):
        r2 = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                experiments_dir=tmp_path / "experiments")
        listing = r2.list()
        assert [e["experiment_id"] for e in listing] == [exp_id]
        exp_dir = tmp_path / "experiments" / exp_id
        assert (exp_dir / "audit_projection.json").is_file()
        assert not (exp_dir / ".pending").exists()
        info = r2.show(exp_id)
        assert info["record_state"] == "FINALIZED"
        assert r2.verify_audit_chain() >= 1
        r2.close()

    def test_failure_removing_pending_marker(self, tmp_path, monkeypatch):
        import nqresearch.experiments.registry as regmod

        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")

        def boom(exp_dir):
            raise OSError("injected: cannot remove marker")

        monkeypatch.setattr(regmod, "_clear_pending_marker", boom)
        with pytest.raises(Exception):
            reg.register(_prereg())
        monkeypatch.undo()
        # The row must NOT be FINALIZED after a reported failure.
        row = reg._con.execute(
            "SELECT record_state FROM experiments").fetchone()
        assert row[0] == "PENDING_PROJECTION"
        reg.close()
        self._assert_recovered_clean(tmp_path, "EXP-0001")

    def test_failure_writing_projection(self, tmp_path, monkeypatch):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")

        def boom(self_reg, exp_id):
            raise OSError("injected: projection write failed")

        monkeypatch.setattr(ExperimentRegistry, "_write_projection", boom)
        with pytest.raises(Exception):
            reg.register(_prereg())
        monkeypatch.undo()
        row = reg._con.execute(
            "SELECT record_state FROM experiments").fetchone()
        assert row[0] == "PENDING_PROJECTION"
        reg.close()
        self._assert_recovered_clean(tmp_path, "EXP-0001")

    def test_crash_after_projection_before_finalized(self, tmp_path):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        # Simulate the crash window: files complete, row rolled to PENDING.
        reg._con.execute(
            "UPDATE experiments SET record_state='PENDING_PROJECTION' "
            "WHERE experiment_id=?", [exp_id])
        reg.close()
        self._assert_recovered_clean(tmp_path, exp_id)

    def test_finalized_with_pending_marker_is_inconsistency(self, tmp_path):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        (tmp_path / "experiments" / exp_id / ".pending").write_text("stray")
        reg.close()
        with pytest.raises(RegistryError, match="inconsistent"):
            ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")

    def test_finalized_missing_projection_rebuilt_on_reopen(self, tmp_path):
        # Round-4 semantics: a missing/stale projection is a RECOVERABLE
        # materialized-view condition, rebuilt from the verified chain
        # (supersedes the round-3 open-blocking behavior for this case; the
        # pending-marker inconsistency remains open-blocking).
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        proj = tmp_path / "experiments" / exp_id / "audit_projection.json"
        proj.unlink()
        reg.close()
        r2 = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                experiments_dir=tmp_path / "experiments")
        assert proj.is_file()
        doc = json.loads(proj.read_text())
        assert doc["event_count"] == len(r2._audit_rows(exp_id))
        r2.close()

    def test_precommit_orphan_dir_quarantined(self, tmp_path):
        exp_dir = tmp_path / "experiments" / "EXP-0042"
        exp_dir.mkdir(parents=True)
        (exp_dir / ".pending").write_text("orphan from pre-commit crash")
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        assert not exp_dir.exists()
        assert (tmp_path / "experiments" / "EXP-0042.orphaned").is_dir()
        events = [r["event"] for r in reg._audit_rows("EXP-0042")]
        assert "ORPHAN_QUARANTINED" in events
        assert reg.trial_count() == 0  # never treated as a valid experiment
        reg.close()


class TestProjectionConsistency:
    def _chain_matches(self, tmp_path, exp_id):
        r = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")
        r.show(exp_id)  # verified inspection reconciles
        proj = json.loads(
            (tmp_path / "experiments" / exp_id / "audit_projection.json")
            .read_text()
        )
        rows = r._audit_rows(exp_id)
        assert proj["event_count"] == len(rows)
        assert proj["head_hash"] == rows[-1]["record_hash"]
        assert proj["events"] == rows
        r.close()
        return rows

    def test_projection_failure_after_committed_terminal(self, tmp_path,
                                                         monkeypatch):
        from nqresearch.experiments.registry import (
            ProjectionRecoveryRequiredError,
        )

        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)

        def boom(self_reg, eid):
            raise OSError("injected projection failure")

        monkeypatch.setattr(ExperimentRegistry, "_write_projection", boom)
        with pytest.raises(ProjectionRecoveryRequiredError, match="COMMITTED"):
            reg.transition(exp_id, STATE_FAILED, outputs=EMPTY_MANIFEST)
        monkeypatch.undo()
        # The transition IS committed despite the reported condition.
        assert reg._show_unverified(exp_id)["status"] == STATE_FAILED
        reg.close()
        rows = self._chain_matches(tmp_path, exp_id)
        terminal_events = [r for r in rows if r["event"] == "TRANSITION"
                           and r["to_status"] == STATE_FAILED]
        assert len(terminal_events) == 1  # exactly once

    def test_projection_failure_after_audited_refusal(self, tmp_path,
                                                      monkeypatch):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())

        def boom(self_reg, eid):
            raise OSError("injected projection failure")

        monkeypatch.setattr(ExperimentRegistry, "_write_projection", boom)
        # The ORIGINAL refusal surfaces, not the projection failure.
        with pytest.raises(InvalidTransitionError):
            reg.transition(exp_id, STATE_PASSED)
        monkeypatch.undo()
        reg.close()
        rows = self._chain_matches(tmp_path, exp_id)
        assert any(r["event"] == "TRANSITION_REFUSED" for r in rows)

    def test_reopen_with_stale_projection(self, tmp_path):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        proj = tmp_path / "experiments" / exp_id / "audit_projection.json"
        stale = json.loads(proj.read_text())
        reg.begin_run(exp_id)  # projection advances
        proj.write_text(json.dumps(stale))  # restore stale copy
        reg.close()
        self._chain_matches(tmp_path, exp_id)

    def test_truncated_projection_json(self, tmp_path):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        proj = tmp_path / "experiments" / exp_id / "audit_projection.json"
        proj.write_text('{"note": "trunca')
        reg.close()
        self._chain_matches(tmp_path, exp_id)

    def test_mismatched_head_or_count(self, tmp_path):
        reg = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                                 experiments_dir=tmp_path / "experiments")
        exp_id = reg.register(_prereg())
        proj = tmp_path / "experiments" / exp_id / "audit_projection.json"
        doc = json.loads(proj.read_text())
        doc["head_hash"] = "f" * 64
        doc["event_count"] = 99
        proj.write_text(json.dumps(doc))
        reg.close()
        self._chain_matches(tmp_path, exp_id)


class TestSection38:
    def test_source_dataset_hashes_required(self):
        bad = dict(SYNTHETIC)
        del bad["source_dataset_hashes"]
        with pytest.raises(ValidationError):
            PreRegistration(**bad)
        with pytest.raises(ValidationError):
            _prereg(source_dataset_hashes={})

    def test_outputs_manifest_recorded_at_terminal_only(self, reg):
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)
        manifest = {"outputs": [{
            "name": "metrics.json", "output_type": "metrics",
            "location": "experiments/EXP/metrics.json", "size_bytes": 12,
            "sha256": "e3b0c44298fc1c149afbf4c8996fb924"
                      "27ae41e4649b934ca495991b7852b855",
        }], "note": "synthetic"}
        with pytest.raises(RegistryError, match="terminal"):
            reg.transition(exp_id, STATE_RUNNING, outputs=manifest)
        reg.transition(exp_id, STATE_PASSED, outputs=manifest)
        out = reg.show(exp_id)["outputs"]
        assert out["outputs"][0]["output_type"] == "metrics"

    def test_arbitrary_outputs_dict_rejected(self, reg):
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)
        with pytest.raises(RegistryError, match="§38 structure"):
            reg.transition(exp_id, STATE_PASSED,
                           outputs={"whatever": {"free": "form"}})
        assert reg._show_unverified(exp_id)["status"] == STATE_RUNNING

    def test_explicitly_empty_manifest_allowed_for_synthetic(self, reg):
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)
        reg.transition(exp_id, STATE_FAILED,
                       outputs={"outputs": [], "note": "synthetic/null run"})
        assert reg.show(exp_id)["outputs"]["outputs"] == []

    def test_terminal_without_manifest_refused(self, reg):
        exp_id = reg.register(_prereg())
        reg.begin_run(exp_id)
        with pytest.raises(RegistryError, match="EXPLICIT OutputsManifest"):
            reg.transition(exp_id, STATE_FAILED)
        assert reg._show_unverified(exp_id)["status"] == STATE_RUNNING

    def test_outputs_null_until_terminal(self, reg):
        exp_id = reg.register(_prereg())
        assert reg.show(exp_id)["outputs"] is None
        reg.begin_run(exp_id)
        assert reg.show(exp_id)["outputs"] is None
        reg.transition(exp_id, STATE_PASSED, outputs=EMPTY_MANIFEST)
        assert reg.show(exp_id)["outputs"] == EMPTY_MANIFEST

    def test_dataset_identity_format_enforced(self):
        with pytest.raises(ValidationError):
            _prereg(source_dataset_hashes={"ds": "not-a-hash"})
        p = _prereg(source_dataset_hashes={"ds": "AB" * 32})
        assert p.source_dataset_hashes["ds"].startswith("sha256:")

    def test_parent_reference_validated(self, reg):
        with pytest.raises(RegistryError, match="not registered"):
            reg.register(_prereg(parent_experiment="EXP-9999"))
        a = reg.register(_prereg())
        b = reg.register(_prereg(parent_experiment=a))
        assert reg.show(b)["parent_experiment"] == a


class TestRawGuardOnRegistry:
    def test_registry_under_raw_refused_even_via_env_override(self, tmp_path,
                                                              monkeypatch):
        from nqresearch.config import clear_config_cache
        from nqresearch.rawguard import RawWriteError

        data_root = tmp_path / "dataroot"
        (data_root / "raw").mkdir(parents=True)
        monkeypatch.setenv("NQR_DATA_ROOT", str(data_root))
        monkeypatch.setenv("NQR_REGISTRY_DB", str(data_root / "raw" / "reg.duckdb"))
        monkeypatch.setenv("NQR_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
        clear_config_cache()
        with pytest.raises(RawWriteError):
            ExperimentRegistry()
        monkeypatch.setenv("NQR_REGISTRY_DB", str(tmp_path / "reg.duckdb"))
        monkeypatch.setenv("NQR_EXPERIMENTS_DIR",
                           str(data_root / "raw" / "experiments"))
        with pytest.raises(RawWriteError):
            ExperimentRegistry()
        clear_config_cache()


class TestCli:
    def test_register_show_transition_via_cli(self, tmp_path, monkeypatch):
        from nqresearch.cli import main

        monkeypatch.setenv("NQR_REGISTRY_DB", str(tmp_path / "reg.duckdb"))
        monkeypatch.setenv("NQR_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
        prereg = tmp_path / "prereg.yaml"
        prereg.write_text(yaml.safe_dump(SYNTHETIC))
        manifest = tmp_path / "outputs.yaml"
        manifest.write_text(yaml.safe_dump(EMPTY_MANIFEST))
        bad_manifest = tmp_path / "bad_outputs.yaml"
        bad_manifest.write_text(yaml.safe_dump({"free": "form"}))
        assert main(["exp", "register", str(prereg)]) == 0
        assert main(["exp", "show", "EXP-0001"]) == 0
        assert main(["exp", "transition", "EXP-0001", "RUNNING"]) == 0
        # terminal WITHOUT an explicit manifest: refused
        assert main(["exp", "transition", "EXP-0001", "FAILED"]) == 1
        # terminal with an INVALID manifest: refused
        assert main(["exp", "transition", "EXP-0001", "FAILED",
                     "--outputs", str(bad_manifest)]) == 1
        # terminal with an explicit (empty) manifest: accepted
        assert main(["exp", "transition", "EXP-0001", "FAILED",
                     "--outputs", str(manifest)]) == 0
        # terminal rewrite refused through the CLI too
        assert main(["exp", "transition", "EXP-0001", "PASSED",
                     "--outputs", str(manifest)]) == 1
        assert main(["exp", "list"]) == 0

    def test_cli_blocked_by_corrupted_chain(self, tmp_path, monkeypatch):
        from nqresearch.cli import main

        monkeypatch.setenv("NQR_REGISTRY_DB", str(tmp_path / "reg.duckdb"))
        monkeypatch.setenv("NQR_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
        prereg = tmp_path / "prereg.yaml"
        prereg.write_text(yaml.safe_dump(SYNTHETIC))
        assert main(["exp", "register", str(prereg)]) == 0
        r = ExperimentRegistry(db_path=tmp_path / "reg.duckdb",
                               experiments_dir=tmp_path / "experiments")
        r._con.execute("UPDATE lifecycle_audit SET note='x' WHERE seq=1")
        r.close()
        # Corrupted evidence blocks CLI list/show/transition (open fails).
        assert main(["exp", "list"]) == 1
        assert main(["exp", "show", "EXP-0001"]) == 1
        assert main(["exp", "transition", "EXP-0001", "RUNNING"]) == 1
