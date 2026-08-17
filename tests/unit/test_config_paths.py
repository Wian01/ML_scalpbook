from pathlib import Path

import pytest
from pydantic import ValidationError

from nqresearch import paths
from nqresearch.config import (
    DataPathsConfig,
    SessionWindowConfig,
    StorageGateConfig,
    clear_config_cache,
)


@pytest.fixture(autouse=True)
def _clean_config_cache(monkeypatch):
    clear_config_cache()
    yield
    clear_config_cache()


class TestDataRoot:
    def test_default_is_repo_relative_data(self, monkeypatch):
        monkeypatch.delenv("NQR_DATA_ROOT", raising=False)
        cfg = DataPathsConfig()
        assert cfg.resolved_data_root(Path("C:/repo")) == Path("C:/repo/data")

    def test_absolute_config_value(self):
        cfg = DataPathsConfig(data_root="D:/nq-data")
        assert cfg.resolved_data_root(Path("C:/repo")) == Path("D:/nq-data")

    def test_env_var_overrides_config(self, monkeypatch):
        monkeypatch.setenv("NQR_DATA_ROOT", "E:/override")
        cfg = DataPathsConfig(data_root="D:/nq-data")
        assert cfg.resolved_data_root(Path("C:/repo")) == Path("E:/override")

    def test_paths_module_honors_env_override(self, monkeypatch):
        monkeypatch.setenv("NQR_DATA_ROOT", "E:/override")
        clear_config_cache()
        assert paths.data_root() == Path("E:/override")
        assert paths.raw_mbp1() == Path("E:/override/raw/mbp1")

    def test_paths_module_default_under_repo(self, monkeypatch):
        monkeypatch.delenv("NQR_DATA_ROOT", raising=False)
        clear_config_cache()
        assert paths.data_root() == paths.ROOT / "data"


class TestSessionWindowConfig:
    def test_time_parsing(self):
        cfg = SessionWindowConfig()
        assert cfg.session_boundary_time.hour == 17
        assert cfg.rth_start_time.minute == 30

    def test_invalid_time_rejected(self):
        with pytest.raises(ValidationError):
            SessionWindowConfig(rth_start="8h30")


class TestStorageGateConfig:
    def test_defaults_match_spec(self):
        cfg = StorageGateConfig()
        assert cfg.required_free_gb == 1000.0
        assert cfg.preferred_free_gb == 2000.0
