"""Effective configuration hash: covers config/data/*.yaml values and the
resolved data root; any session or data-path change must alter it and thereby
invalidate config-keyed caches."""

import pytest

import nqresearch.config as config_mod
from nqresearch.config import (
    SessionWindowConfig,
    clear_config_cache,
    effective_config_hash,
)
from nqresearch.qa import cache as cache_mod
from nqresearch.qa.cache import run_cached


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    clear_config_cache()
    cache_mod._manifest_hashes.cache_clear()
    yield
    clear_config_cache()
    cache_mod._manifest_hashes.cache_clear()


def _temp_repo(tmp_path, sessions_yaml: str):
    root = tmp_path / "repo"
    (root / "config" / "data").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    (root / "config" / "data" / "sessions.yaml").write_text(sessions_yaml)
    return root


class TestEffectiveConfigHash:
    def test_stable_for_same_configuration(self):
        assert effective_config_hash() == effective_config_hash()

    def test_session_yaml_change_changes_hash(self, tmp_path):
        r1 = _temp_repo(tmp_path, 'session_boundary: "17:00"\n')
        h1 = effective_config_hash(r1)
        (r1 / "config" / "data" / "sessions.yaml").write_text(
            'session_boundary: "16:00"\n'
        )
        clear_config_cache()
        assert effective_config_hash(r1) != h1

    def test_timezone_change_changes_hash(self, tmp_path):
        r = _temp_repo(tmp_path, "timezone: America/Chicago\n")
        h1 = effective_config_hash(r)
        (r / "config" / "data" / "sessions.yaml").write_text(
            "timezone: America/New_York\n"
        )
        clear_config_cache()
        assert effective_config_hash(r) != h1

    def test_rth_change_changes_hash(self, tmp_path):
        r = _temp_repo(tmp_path, 'rth_start: "08:30"\n')
        h1 = effective_config_hash(r)
        (r / "config" / "data" / "sessions.yaml").write_text('rth_start: "09:30"\n')
        clear_config_cache()
        assert effective_config_hash(r) != h1

    def test_data_root_override_changes_hash(self, monkeypatch):
        h1 = effective_config_hash()
        monkeypatch.setenv("NQR_DATA_ROOT", "E:/somewhere-else")
        clear_config_cache()
        assert effective_config_hash() != h1


class TestSessionConfigInvalidatesCaches:
    def _run(self, tmp_path, calls_name):
        f = tmp_path / "f1.dbn.zst"
        if not f.exists():
            f.write_bytes(b"data")
        calls = tmp_path / calls_name
        if not calls.exists():
            calls.write_text("")
        run_cached(
            [f], _count_worker, (str(calls),), 1, tmp_path / "cache", {"p": 1}
        )
        return calls

    def test_session_config_change_invalidates_cached_results(
        self, tmp_path, monkeypatch
    ):
        calls = self._run(tmp_path, "calls.txt")
        assert calls.read_text().count("f1") == 1
        # Same config -> cache hit.
        self._run(tmp_path, "calls.txt")
        assert calls.read_text().count("f1") == 1
        # Simulate an edited sessions.yaml (boundary change) -> recompute.
        monkeypatch.setattr(
            config_mod,
            "load_session_config",
            lambda repo_root=None: SessionWindowConfig(session_boundary="16:00"),
        )
        self._run(tmp_path, "calls.txt")
        assert calls.read_text().count("f1") == 2

    def test_data_root_change_invalidates_cached_results(
        self, tmp_path, monkeypatch
    ):
        calls = self._run(tmp_path, "calls2.txt")
        assert calls.read_text().count("f1") == 1
        monkeypatch.setenv("NQR_DATA_ROOT", "E:/moved")
        clear_config_cache()
        self._run(tmp_path, "calls2.txt")
        assert calls.read_text().count("f1") == 2


def _count_worker(path, calls_file):
    with open(calls_file, "a") as fh:
        fh.write(path.name + "\n")
    return {"decoded": path.name}
