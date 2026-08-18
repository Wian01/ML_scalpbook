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
from pydantic import BaseModel, Field, field_validator, model_validator


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


ROLE_FULL_HISTORY = "FULL_HISTORY_CANONICAL"
ROLE_M0_QA_SAMPLE = "MILESTONE0_QA_SAMPLE"


# Expected acquisition parameters for MBP-1 sources (frozen specification).
MBP1_EXPECTED_DATASET = "GLBX.MDP3"
MBP1_EXPECTED_SCHEMA = "mbp-1"
MBP1_EXPECTED_SYMBOLS = ["NQ.FUT"]
MBP1_EXPECTED_STYPE_IN = "parent"
MBP1_EXPECTED_STYPE_OUT = "instrument_id"


class Mbp1Source(BaseModel):
    """One vendor batch job in the MBP-1 source-provenance registry."""

    request_id: str
    path: str  # relative to <data_root>; POSIX separators; no escapes
    role: str
    research_eligible: bool
    dataset: str
    schema_name: str = Field(alias="schema")
    symbols: list[str]
    stype_in: str
    stype_out: str
    start_ns: int
    end_ns: int
    manifest: str = "manifest.json"
    manifest_sha256: str
    notes: str = ""

    model_config = {"populate_by_name": True}

    @field_validator("role")
    @classmethod
    def _known_role(cls, v: str) -> str:
        if v not in (ROLE_FULL_HISTORY, ROLE_M0_QA_SAMPLE):
            raise ValueError(f"unknown source role: {v!r}")
        return v

    @field_validator("path")
    @classmethod
    def _safe_relative_path(cls, v: str) -> str:
        p = Path(v)
        if (
            p.is_absolute()
            or v.startswith(("/", "\\"))
            or (len(v) > 1 and v[1] == ":")
        ):
            raise ValueError(f"source path must be relative to <data_root>: {v!r}")
        if ".." in p.parts:
            raise ValueError(f"source path must not contain '..': {v!r}")
        return v

    @field_validator("manifest_sha256")
    @classmethod
    def _hex_sha256(cls, v: str) -> str:
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v.lower()):
            raise ValueError("manifest_sha256 must be a 64-hex-char SHA-256")
        return v.lower()

    @model_validator(mode="after")
    def _consistent(self):
        if self.role == ROLE_M0_QA_SAMPLE and self.research_eligible:
            raise ValueError(
                f"{self.request_id}: MILESTONE0_QA_SAMPLE sources must have "
                "research_eligible=false (the sample is never modelling input)"
            )
        if self.role == ROLE_FULL_HISTORY and not self.research_eligible:
            raise ValueError(
                f"{self.request_id}: FULL_HISTORY_CANONICAL sources must have "
                "research_eligible=true"
            )
        if self.start_ns >= self.end_ns:
            raise ValueError(f"{self.request_id}: start_ns must be < end_ns")
        expected = {
            "dataset": (self.dataset, MBP1_EXPECTED_DATASET),
            "schema": (self.schema_name, MBP1_EXPECTED_SCHEMA),
            "symbols": (self.symbols, MBP1_EXPECTED_SYMBOLS),
            "stype_in": (self.stype_in, MBP1_EXPECTED_STYPE_IN),
            "stype_out": (self.stype_out, MBP1_EXPECTED_STYPE_OUT),
        }
        for name, (actual, want) in expected.items():
            if actual != want:
                raise ValueError(
                    f"{self.request_id}: {name}={actual!r} conflicts with the "
                    f"expected specification value {want!r}"
                )
        return self


class Mbp1SourceRegistry(BaseModel):
    sources: list[Mbp1Source] = []
    overlap_policy: dict = {}

    @model_validator(mode="after")
    def _unique_ids_and_paths(self):
        ids = [s.request_id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate request_id in mbp1 source registry")
        paths_ = [s.path for s in self.sources]
        if len(paths_) != len(set(paths_)):
            raise ValueError("duplicate source path in mbp1 source registry")
        return self

    def by_role(self, role: str) -> list[Mbp1Source]:
        return [s for s in self.sources if s.role == role]

    def research_sources(self) -> list[Mbp1Source]:
        return [s for s in self.sources if s.research_eligible]


@lru_cache(maxsize=None)
def load_mbp1_sources(repo_root: Path | None = None) -> Mbp1SourceRegistry:
    root = repo_root or _repo_root()
    return Mbp1SourceRegistry(
        **_load_yaml(root / "config" / "data" / "mbp1_sources.yaml")
    )


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
    reg = load_mbp1_sources(root)
    cal_path = root / "config" / "data" / "cme_calendar.yaml"
    cal_sha = (
        hashlib.sha256(cal_path.read_bytes()).hexdigest()
        if cal_path.is_file() else None
    )
    ov_path = root / "config" / "data" / "cme_calendar_overrides.yaml"
    ov_sha = (
        hashlib.sha256(ov_path.read_bytes()).hexdigest()
        if ov_path.is_file() else None
    )
    payload = {
        "data_paths": dp.model_dump(),
        "sessions": sc.model_dump(),
        "resolved_data_root": str(dp.resolved_data_root(root)),
        "mbp1_sources": reg.model_dump(by_alias=True),
        "cme_calendar_sha256": cal_sha,
        "cme_calendar_overrides_sha256": ov_sha,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()


def clear_config_cache() -> None:
    """For tests: force configs (and env overrides) to be re-read.

    Tolerates monkeypatched (non-lru_cache) loader replacements.
    """
    for fn in (load_data_paths_config, load_session_config, load_mbp1_sources):
        cache_clear = getattr(fn, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()
