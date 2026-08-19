"""Artifact-envelope provenance layer (qa.report): accurate Git-cleanliness
stamping from synthetic temporary repositories, reserved-key protection, and
absence of any dirty-tree override. Never touches live QA artifacts."""

import inspect
import json
import subprocess

import pytest

from nqresearch.qa.report import (
    RESERVED_ENVELOPE_KEYS,
    ReservedEnvelopeKeyError,
    write_artifact,
)


def _git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def _repo(tmp_path, commit=True):
    root = tmp_path / "synthrepo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "tracked.txt").write_text("v1\n")
    if commit:
        _git(root, "add", "tracked.txt")
        _git(root, "commit", "-q", "-m", "init")
    return root


def _write(tmp_path, root, payload=None):
    out = tmp_path / "outdir"
    p = write_artifact(payload or {"artifact": "synthetic", "status": "PASS"},
                       out, "synthetic_artifact", root)
    return json.loads(p.read_text(encoding="utf-8"))


class TestGenerationCleanliness:
    def test_clean_committed_repo_stamped_clean(self, tmp_path):
        root = _repo(tmp_path)
        doc = _write(tmp_path, root)
        assert doc["generation_git_clean"] is True
        assert doc["git_sha"] == _git(root, "rev-parse", "HEAD")
        assert "clean committed tree" in doc["restamp_note"]
        assert "NOT eligible" not in doc["restamp_note"]

    def test_unstaged_tracked_change_stamped_dirty(self, tmp_path):
        root = _repo(tmp_path)
        (root / "tracked.txt").write_text("modified\n")
        doc = _write(tmp_path, root)
        assert doc["generation_git_clean"] is False
        assert "NOT eligible for provenance acceptance" in doc["restamp_note"]

    def test_staged_change_stamped_dirty(self, tmp_path):
        root = _repo(tmp_path)
        (root / "tracked.txt").write_text("staged\n")
        _git(root, "add", "tracked.txt")
        doc = _write(tmp_path, root)
        assert doc["generation_git_clean"] is False

    def test_untracked_file_stamped_dirty(self, tmp_path):
        root = _repo(tmp_path)
        (root / "untracked.txt").write_text("new\n")
        doc = _write(tmp_path, root)
        assert doc["generation_git_clean"] is False
        assert "NOT eligible" in doc["restamp_note"]

    def test_unborn_repo_stamped_dirty_with_null_sha(self, tmp_path):
        root = _repo(tmp_path, commit=False)
        doc = _write(tmp_path, root)
        assert doc["git_sha"] is None
        assert doc["generation_git_clean"] is False

    def test_non_git_directory_stamped_dirty(self, tmp_path):
        root = tmp_path / "plaindir"
        root.mkdir()
        doc = _write(tmp_path, root)
        assert doc["git_sha"] is None
        assert doc["generation_git_clean"] is False

    def test_no_override_parameter_exists(self):
        params = set(inspect.signature(write_artifact).parameters)
        assert params == {"payload", "out_dir", "name", "root"}
        assert not any("override" in p or "allow" in p or "dirty" in p
                       for p in params)


class TestReservedEnvelopeKeys:
    @pytest.mark.parametrize("key", sorted(RESERVED_ENVELOPE_KEYS))
    def test_payload_cannot_supply_reserved_field(self, tmp_path, key):
        root = _repo(tmp_path)
        with pytest.raises(ReservedEnvelopeKeyError, match="reserved"):
            _write(tmp_path, root,
                   payload={"artifact": "synthetic", key: "forged"})

    def test_reserved_set_covers_all_identity_fields(self):
        assert {"generated_at_utc", "nqresearch_version", "git_sha",
                "generation_git_clean", "restamp_note", "audit_code_hash",
                "config_hash", "data_root"} <= RESERVED_ENVELOPE_KEYS

    def test_ordinary_payload_fields_pass_through(self, tmp_path):
        root = _repo(tmp_path)
        doc = _write(tmp_path, root,
                     payload={"artifact": "synthetic", "status": "PASS",
                              "custom_field": 42})
        assert doc["custom_field"] == 42
        assert doc["artifact"] == "synthetic"
