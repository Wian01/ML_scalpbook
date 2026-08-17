"""Human-authored YAML configuration (canonical spec section 46).

Configuration lives under config/ in the repository. The data root is
configurable so raw/derived data can live on a dedicated volume (e.g. a
separate NVMe drive); the environment variable NQR_DATA_ROOT overrides the
config file. Session boundary and RTH windows are configuration, not code
(canonical spec sections 9/10).
"""

from __future__ import annotations

import os
from datetime import time
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError("Could not locate project root (pyproject.toml not found)")


class StorageGateConfig(BaseModel):
    """Free-space requirements on the data volume before the full MBP-1
    purchase (canonical spec sections 2.2 and 59)."""

    required_free_gb: float = 1000.0
    preferred_free_gb: float = 2000.0


class DataPathsConfig(BaseModel):
    """Where the data tree lives. Relative paths resolve against the repo root."""

    data_root: str = "data"
    storage_gate: StorageGateConfig = StorageGateConfig()

    def resolved_data_root(self, repo_root: Path) -> Path:
        env = os.environ.get("NQR_DATA_ROOT")
        raw = Path(env) if env else Path(self.data_root)
        return raw if raw.is_absolute() else repo_root / raw


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


class SessionWindowConfig(BaseModel):
    """CME trading-session boundary and V1 RTH window, exchange-local."""

    timezone: str = "America/Chicago"
    session_boundary: str = "17:00"
    rth_start: str = "08:30"
    rth_end: str = "15:00"

    @field_validator("session_boundary", "rth_start", "rth_end")
    @classmethod
    def _valid_hhmm(cls, v: str) -> str:
        _parse_hhmm(v)
        return v

    @property
    def session_boundary_time(self) -> time:
        return _parse_hhmm(self.session_boundary)

    @property
    def rth_start_time(self) -> time:
        return _parse_hhmm(self.rth_start)

    @property
    def rth_end_time(self) -> time:
        return _parse_hhmm(self.rth_end)


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=None)
def load_data_paths_config(repo_root: Path | None = None) -> DataPathsConfig:
    root = repo_root or _repo_root()
    return DataPathsConfig(**_load_yaml(root / "config" / "data" / "paths.yaml"))


@lru_cache(maxsize=None)
def load_session_config(repo_root: Path | None = None) -> SessionWindowConfig:
    root = repo_root or _repo_root()
    return SessionWindowConfig(**_load_yaml(root / "config" / "data" / "sessions.yaml"))


def effective_config_hash(repo_root: Path | None = None) -> str:
    """SHA-256 over the effective configuration: parsed values of
    config/data/*.yaml plus the resolved data root (so an NQR_DATA_ROOT
    override changes the hash). Any session-timezone/boundary/RTH or data-path
    change therefore invalidates config-keyed caches and is visible in QA
    artifact envelopes."""
    import hashlib
    import json

    root = repo_root or _repo_root()
    dp = load_data_paths_config(root)
    sc = load_session_config(root)
    payload = {
        "data_paths": dp.model_dump(),
        "sessions": sc.model_dump(),
        "resolved_data_root": str(dp.resolved_data_root(root)),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()


def clear_config_cache() -> None:
    """For tests: force configs (and env overrides) to be re-read.

    Tolerates monkeypatched (non-lru_cache) loader replacements.
    """
    for fn in (load_data_paths_config, load_session_config):
        cache_clear = getattr(fn, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()
