"""require_provenance(): research preparation must refuse stale, failed,
missing, or malformed acquisition-gate evidence."""

import hashlib
import json
import subprocess

import pytest

from nqresearch.config import (
    ROLE_FULL_HISTORY,
    Mbp1Source,
    Mbp1SourceRegistry,
    effective_config_hash,
)
from nqresearch.qa.mbp1_acquisition import (
    EXPECTED_GATE_CHECKS,
    acquisition_code_hash,
)
from nqresearch.sources import ProvenanceError, require_provenance

MANIFEST_CONTENT = json.dumps({"files": []})
MANIFEST_SHA = hashlib.sha256(MANIFEST_CONTENT.encode()).hexdigest()


def _project_git(*args) -> str:
    from nqresearch import paths

    r = subprocess.run(["git", "-C", str(paths.ROOT), *args],
                       capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


# A REAL ancestral commit of the actual project repository: the default gate
# fixture must satisfy the commit-existence + ancestry binding genuinely,
# never via a fabricated 40-hex value.
REAL_HEAD = _project_git("rev-parse", "HEAD")


def _registry():
    return Mbp1SourceRegistry(sources=[
        Mbp1Source(
            request_id="J1", path="raw/mbp1/a/J1", role=ROLE_FULL_HISTORY,
            research_eligible=True, dataset="GLBX.MDP3", schema="mbp-1",
            symbols=["NQ.FUT"], stype_in="parent", stype_out="instrument_id",
            start_ns=0, end_ns=10, manifest_sha256=MANIFEST_SHA,
        )
    ])


def _env(tmp_path, drop_keys=(), **gate_overrides):
    job = tmp_path / "raw/mbp1/a/J1"
    job.mkdir(parents=True)
    (job / "manifest.json").write_text(MANIFEST_CONTENT)
    gate = {
        "status": "PASS",
        "generation_git_clean": True,
        "git_sha": REAL_HEAD,
        "config_hash": effective_config_hash(),
        "acquisition_code_hash": acquisition_code_hash(),
        "current_manifest_sha256": {"J1": MANIFEST_SHA},
        "checks": [{"check": n, "status": "PASS"} for n in EXPECTED_GATE_CHECKS],
    }
    gate.update(gate_overrides)
    for k in drop_keys:
        gate.pop(k, None)
    gate_dir = tmp_path / "qa" / "mbp1_full_history"
    gate_dir.mkdir(parents=True)
    (gate_dir / "mbp1_acquisition_gate.json").write_text(json.dumps(gate))
    return tmp_path


class TestRequireProvenance:
    def test_valid_current_gate_accepted(self, tmp_path):
        root = _env(tmp_path)
        gate = require_provenance(root, _registry())
        assert gate["status"] == "PASS"

    def test_missing_gate_rejected(self, tmp_path):
        with pytest.raises(ProvenanceError, match="missing"):
            require_provenance(tmp_path, _registry())

    def test_failed_gate_rejected(self, tmp_path):
        root = _env(tmp_path, status="FAIL")
        with pytest.raises(ProvenanceError, match="not PASS"):
            require_provenance(root, _registry())

    def test_stale_config_hash_rejected(self, tmp_path):
        root = _env(tmp_path, config_hash="0" * 64)
        with pytest.raises(ProvenanceError, match="different effective"):
            require_provenance(root, _registry())

    def test_stale_code_hash_rejected(self, tmp_path):
        # The blocking review finding: a gate produced by older
        # acquisition/provenance code must never authorize research prep.
        root = _env(tmp_path, acquisition_code_hash="deadbeef" * 8)
        with pytest.raises(ProvenanceError, match="different acquisition"):
            require_provenance(root, _registry())

    def test_changed_manifest_identity_rejected(self, tmp_path):
        root = _env(tmp_path)
        # Vendor manifest replaced after the gate was generated.
        (root / "raw/mbp1/a/J1/manifest.json").write_text(
            json.dumps({"files": [{"filename": "new"}]})
        )
        with pytest.raises(ProvenanceError, match="manifest identity"):
            require_provenance(root, _registry())

    def test_gate_manifest_map_mismatch_rejected(self, tmp_path):
        root = _env(tmp_path, current_manifest_sha256={"J1": "1" * 64})
        with pytest.raises(ProvenanceError, match="manifest identity"):
            require_provenance(root, _registry())

    def test_missing_checks_list_rejected(self, tmp_path):
        root = _env(tmp_path, checks=None)
        with pytest.raises(ProvenanceError, match="malformed"):
            require_provenance(root, _registry())

    def test_missing_named_check_rejected(self, tmp_path):
        checks = [{"check": n, "status": "PASS"}
                  for n in EXPECTED_GATE_CHECKS if n != "record_level_identity"]
        root = _env(tmp_path, checks=checks)
        with pytest.raises(ProvenanceError, match="record_level_identity"):
            require_provenance(root, _registry())

    def test_non_pass_named_check_rejected_despite_top_level_pass(self, tmp_path):
        checks = [{"check": n, "status": "PASS"} for n in EXPECTED_GATE_CHECKS]
        checks[5]["status"] = "WARN"
        root = _env(tmp_path, checks=checks)
        with pytest.raises(ProvenanceError, match="not PASS"):
            require_provenance(root, _registry())

    def test_expected_checks_constant_has_nine_names(self):
        assert len(EXPECTED_GATE_CHECKS) == 9
        assert len(set(EXPECTED_GATE_CHECKS)) == 9


class TestCleanGenerationBinding:
    """The gate must have been generated from a clean committed tree
    (envelope-stamped generation_git_clean + a real committed git_sha)."""

    def test_missing_cleanliness_field_rejected(self, tmp_path):
        root = _env(tmp_path, drop_keys=("generation_git_clean",))
        with pytest.raises(ProvenanceError, match="clean committed tree"):
            require_provenance(root, _registry())

    @pytest.mark.parametrize("bad", [False, "true", "True", 1, 0, None, []])
    def test_non_boolean_true_cleanliness_rejected(self, tmp_path, bad):
        root = _env(tmp_path, generation_git_clean=bad)
        with pytest.raises(ProvenanceError, match="clean committed tree"):
            require_provenance(root, _registry())

    @pytest.mark.parametrize("bad", [None, "", "HEAD", "abc", "g" * 40,
                                     "A" * 40, 123])
    def test_invalid_git_sha_rejected(self, tmp_path, bad):
        root = _env(tmp_path, git_sha=bad)
        with pytest.raises(ProvenanceError, match="git_sha"):
            require_provenance(root, _registry())

    def test_fabricated_wellformed_sha_rejected(self, tmp_path):
        # THE review finding: 40 lowercase hex characters alone prove
        # nothing — a fabricated value that is no real commit must refuse.
        root = _env(tmp_path, git_sha="b" * 40)
        with pytest.raises(ProvenanceError, match="commit object"):
            require_provenance(root, _registry())

    def test_clean_gate_accepted_after_audit_only_commit_real_history(
            self, tmp_path):
        # REAL-history proof of the audit-only-commit pattern at the
        # require_provenance level: the gate records the project's HEAD~1
        # (an actual ancestor commit, e.g. an implementation commit that an
        # audit-log-only commit then followed) and must remain accepted
        # while code/config/manifests are unchanged.
        parent = _project_git("rev-parse", "HEAD~1")
        root = _env(tmp_path, git_sha=parent)
        gate = require_provenance(root, _registry())
        assert gate["git_sha"] == parent != REAL_HEAD

    def test_no_override_parameter_exists(self):
        import inspect

        # The exact signature is the proof: data_root (the DATA tree) and
        # registry only — no repo-root override, no allow/dirty escape.
        params = set(inspect.signature(require_provenance).parameters)
        assert params == {"data_root", "registry"}
        assert not any("override" in p or "allow" in p or "dirty" in p
                       or "repo" in p for p in params)


def _git(root, *args, check=True):
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True)
    if check:
        assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def _synth_repo(tmp_path, commit=True):
    root = tmp_path / "synthrepo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "f.txt").write_text("v1\n")
    if commit:
        _git(root, "add", "f.txt")
        _git(root, "commit", "-q", "-m", "A")
    return root


class TestCommittedAncestorBinding:
    """The private Git-binding helper, against REAL synthetic Git history:
    fabricated, non-ancestor, and non-commit SHAs all refuse; a generation
    commit followed by an audit-log-only commit stays accepted."""

    def test_generation_commit_accepted_after_audit_only_commit(
            self, tmp_path):
        from nqresearch.sources import _verify_committed_ancestor

        root = _synth_repo(tmp_path)
        sha_a = _git(root, "rev-parse", "HEAD")        # implementation A
        (root / "auditlog.md").write_text("AL entry\n")
        _git(root, "add", "auditlog.md")
        _git(root, "commit", "-q", "-m", "B: audit-log only")
        sha_b = _git(root, "rev-parse", "HEAD")
        assert sha_a != sha_b
        # A exists and is an ancestor of B...
        _git(root, "cat-file", "-e", f"{sha_a}^{{commit}}")
        _git(root, "merge-base", "--is-ancestor", sha_a, "HEAD")
        # ...and the binding helper accepts A while HEAD is B.
        _verify_committed_ancestor(sha_a, root)  # must not raise

    def test_fabricated_sha_rejected(self, tmp_path):
        from nqresearch.sources import _verify_committed_ancestor

        root = _synth_repo(tmp_path)
        with pytest.raises(ProvenanceError, match="commit object"):
            _verify_committed_ancestor("b" * 40, root)

    def test_non_ancestor_branch_commit_rejected(self, tmp_path):
        from nqresearch.sources import _verify_committed_ancestor

        root = _synth_repo(tmp_path)
        base_branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        _git(root, "checkout", "-q", "-b", "feature")
        (root / "feat.txt").write_text("x\n")
        _git(root, "add", "feat.txt")
        _git(root, "commit", "-q", "-m", "C on feature")
        sha_c = _git(root, "rev-parse", "HEAD")
        _git(root, "checkout", "-q", base_branch)
        (root / "f.txt").write_text("v2\n")
        _git(root, "add", "f.txt")
        _git(root, "commit", "-q", "-m", "B on base")
        with pytest.raises(ProvenanceError, match="ancestor"):
            _verify_committed_ancestor(sha_c, root)

    def test_annotated_tag_object_sha_rejected(self, tmp_path):
        # Reproduced review finding: an ANNOTATED TAG object has its own
        # SHA, and `cat-file -e <sha>^{commit}` peels it to the tagged
        # commit while `merge-base --is-ancestor` also succeeds — so a
        # peeling type check would accept a non-commit object as git_sha.
        # The exact-type proof (`cat-file -t` == "commit") must refuse it,
        # while the underlying commit stays acceptable.
        from nqresearch.sources import _verify_committed_ancestor

        root = _synth_repo(tmp_path)
        sha_a = _git(root, "rev-parse", "HEAD")
        _git(root, "tag", "-a", "v1", "-m", "annotated")
        tag_sha = _git(root, "rev-parse", "v1")
        assert tag_sha != sha_a
        assert _git(root, "cat-file", "-t", tag_sha) == "tag"
        # The peeling form would have passed — proving the defect is real:
        assert subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{tag_sha}^{{commit}}"],
            capture_output=True).returncode == 0
        with pytest.raises(ProvenanceError, match="commit object"):
            _verify_committed_ancestor(tag_sha, root)
        _verify_committed_ancestor(sha_a, root)  # the commit itself is fine

    def test_lightweight_tag_sha_is_the_commit_and_accepted(self, tmp_path):
        # A lightweight tag resolves directly to the commit object, so the
        # supplied SHA genuinely IS a commit: it must remain acceptable.
        from nqresearch.sources import _verify_committed_ancestor

        root = _synth_repo(tmp_path)
        sha_a = _git(root, "rev-parse", "HEAD")
        _git(root, "tag", "light")
        assert _git(root, "rev-parse", "light") == sha_a
        _verify_committed_ancestor(_git(root, "rev-parse", "light"), root)

    def test_blob_and_tree_sha_rejected(self, tmp_path):
        from nqresearch.sources import _verify_committed_ancestor

        root = _synth_repo(tmp_path)
        blob = _git(root, "rev-parse", "HEAD:f.txt")
        tree = _git(root, "rev-parse", "HEAD^{tree}")
        for sha in (blob, tree):
            with pytest.raises(ProvenanceError, match="commit object"):
                _verify_committed_ancestor(sha, root)

    def test_non_git_directory_rejected(self, tmp_path):
        from nqresearch.sources import _verify_committed_ancestor

        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(ProvenanceError, match="commit object"):
            _verify_committed_ancestor("b" * 40, plain)

    def test_unborn_repo_rejected(self, tmp_path):
        from nqresearch.sources import _verify_committed_ancestor

        root = _synth_repo(tmp_path, commit=False)
        with pytest.raises(ProvenanceError, match="commit object"):
            _verify_committed_ancestor("b" * 40, root)

    def test_git_command_failure_rejected(self, tmp_path, monkeypatch):
        import subprocess as sp

        import nqresearch.sources as sources_mod
        from nqresearch.sources import _verify_committed_ancestor

        root = _synth_repo(tmp_path)
        sha = _git(root, "rev-parse", "HEAD")

        def _boom(*a, **k):
            raise OSError("git exploded")

        monkeypatch.setattr(sp, "run", _boom)
        with pytest.raises(ProvenanceError, match="unavailable or failed"):
            _verify_committed_ancestor(sha, root)
