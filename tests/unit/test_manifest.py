import hashlib
import json

from nqresearch.qa.manifest import sha256_file, validate_raw_tree
from nqresearch.qa.status import FAIL, PASS, WARN


def _make_job(tmp_path, name="JOB-1", content=b"hello market data"):
    job = tmp_path / name
    job.mkdir()
    data = job / "day1.dbn.zst"
    data.write_bytes(content)
    manifest = {
        "job_id": name,
        "files": [
            {
                "filename": "day1.dbn.zst",
                "size": len(content),
                "hash": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    (job / "manifest.json").write_text(json.dumps(manifest))
    return job, data


class TestManifestValidation:
    def test_valid_tree_passes(self, tmp_path):
        _make_job(tmp_path)
        r = validate_raw_tree(tmp_path, workers=1)
        assert r["status"] == PASS
        assert r["n_files_checked"] == 1
        assert r["failures"] == []

    def test_missing_file_fails(self, tmp_path):
        _, data = _make_job(tmp_path)
        data.unlink()
        r = validate_raw_tree(tmp_path, workers=1)
        assert r["status"] == FAIL
        assert r["failures"][0]["issue"] == "missing"

    def test_size_mismatch_fails(self, tmp_path):
        _, data = _make_job(tmp_path)
        data.write_bytes(b"tampered with different length")
        r = validate_raw_tree(tmp_path, workers=1)
        assert r["status"] == FAIL
        assert r["failures"][0]["issue"] == "size_mismatch"

    def test_content_tamper_same_size_fails_sha256(self, tmp_path):
        _, data = _make_job(tmp_path, content=b"AAAA")
        data.write_bytes(b"BBBB")  # same size, different content
        r = validate_raw_tree(tmp_path, workers=1)
        assert r["status"] == FAIL
        assert r["failures"][0]["issue"] == "sha256_mismatch"

    def test_unmanifested_file_warns(self, tmp_path):
        job, _ = _make_job(tmp_path)
        (job / "extra.dbn.zst").write_bytes(b"stray")
        r = validate_raw_tree(tmp_path, workers=1)
        assert r["status"] == WARN
        assert any("extra.dbn.zst" in f for f in r["unmanifested_files"])

    def test_sha256_file(self, tmp_path):
        f = tmp_path / "x.bin"
        f.write_bytes(b"abc")
        assert sha256_file(f) == hashlib.sha256(b"abc").hexdigest()

    def test_data_dir_without_manifest_warns(self, tmp_path):
        _make_job(tmp_path)
        orphan = tmp_path / "JOB-NO-MANIFEST"
        orphan.mkdir()
        (orphan / "day2.dbn.zst").write_bytes(b"unverifiable")
        r = validate_raw_tree(tmp_path, workers=1)
        assert r["status"] == WARN
        assert r["job_dirs_without_manifest"][0]["job_dir"] == "JOB-NO-MANIFEST"
        assert r["job_dirs_without_manifest"][0]["n_data_files"] == 1
