import hashlib
import json
import os

import pytest

from nqresearch.qa import cache as cache_mod
from nqresearch.qa.cache import cache_key, package_source_hash, run_cached


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    cache_mod._manifest_hashes.cache_clear()
    yield
    cache_mod._manifest_hashes.cache_clear()


def _worker_calls(tmp_path):
    calls = tmp_path / "calls.txt"
    calls.write_text("")
    return calls


def _make_file(tmp_path, name="f1.dbn.zst", content=b"data"):
    f = tmp_path / name
    f.write_bytes(content)
    return f


def _count_worker(path, calls_file):
    with open(calls_file, "a") as fh:
        fh.write(path.name + "\n")
    return {"decoded": path.name}


class TestCacheKey:
    def test_key_includes_all_components(self, tmp_path):
        f = _make_file(tmp_path)
        key = cache_key(f, {"chunk_rows": 5})
        assert key["params"] == {"chunk_rows": 5}
        assert key["audit_code_hash"] == package_source_hash()
        assert "size_bytes" in key and "mtime_ns" in key
        assert key["identity_source"] == "size_mtime_fallback"

    def test_key_uses_manifest_hash_when_available(self, tmp_path):
        content = b"vendor bytes"
        f = _make_file(tmp_path, content=content)
        manifest = {
            "files": [{"filename": f.name, "size": len(content),
                       "hash": "sha256:" + hashlib.sha256(content).hexdigest()}]
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        key = cache_key(f, {})
        assert key["identity_source"] == "manifest"
        assert key["vendor_hash"].endswith(hashlib.sha256(content).hexdigest())


class TestRunCached:
    def test_caches_and_reuses(self, tmp_path):
        f = _make_file(tmp_path)
        calls = _worker_calls(tmp_path)
        cache_dir = tmp_path / "cache"
        for _ in range(2):
            out = run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {"p": 1})
            assert out == [{"decoded": "f1.dbn.zst"}]
        assert calls.read_text().count("f1") == 1  # second run served from cache

    def test_params_change_invalidates(self, tmp_path):
        f = _make_file(tmp_path)
        calls = _worker_calls(tmp_path)
        cache_dir = tmp_path / "cache"
        run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {"p": 1})
        run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {"p": 2})
        assert calls.read_text().count("f1") == 2

    def test_file_modification_invalidates(self, tmp_path):
        f = _make_file(tmp_path, content=b"v1")
        calls = _worker_calls(tmp_path)
        cache_dir = tmp_path / "cache"
        run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {})
        f.write_bytes(b"v2")  # same size, new mtime
        os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 1_000_000))
        run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {})
        assert calls.read_text().count("f1") == 2

    def test_code_hash_change_invalidates(self, tmp_path, monkeypatch):
        f = _make_file(tmp_path)
        calls = _worker_calls(tmp_path)
        cache_dir = tmp_path / "cache"
        run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {})
        monkeypatch.setattr(cache_mod, "package_source_hash", lambda: "different")
        run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {})
        assert calls.read_text().count("f1") == 2

    def test_repaired_file_with_new_manifest_hash_invalidates(self, tmp_path):
        # Models a re-downloaded vendor file: content and manifest hash change.
        content_v1 = b"truncated download"
        f = _make_file(tmp_path, content=content_v1)
        manifest = tmp_path / "manifest.json"

        def write_manifest(content):
            manifest.write_text(json.dumps({
                "files": [{"filename": f.name, "size": len(content),
                           "hash": "sha256:" + hashlib.sha256(content).hexdigest()}]
            }))

        write_manifest(content_v1)
        calls = _worker_calls(tmp_path)
        cache_dir = tmp_path / "cache"
        run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {})
        # Repair: full file re-downloaded with a fresh manifest.
        content_v2 = b"complete re-downloaded vendor file"
        f.write_bytes(content_v2)
        write_manifest(content_v2)
        cache_mod._manifest_hashes.cache_clear()
        run_cached([f], _count_worker, (str(calls),), 1, cache_dir, {})
        assert calls.read_text().count("f1") == 2

    def test_no_cache_dir_always_recomputes(self, tmp_path):
        f = _make_file(tmp_path)
        calls = _worker_calls(tmp_path)
        run_cached([f], _count_worker, (str(calls),), 1, None, {})
        run_cached([f], _count_worker, (str(calls),), 1, None, {})
        assert calls.read_text().count("f1") == 2


class TestPackageSourceHash:
    def test_stable_within_run(self):
        assert package_source_hash() == package_source_hash()
        assert len(package_source_hash()) == 64
