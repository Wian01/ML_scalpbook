"""Project path resolution.

The data root is configurable (config/data/paths.yaml, overridden by the
NQR_DATA_ROOT environment variable) so the data tree can live on a dedicated
volume. All raw vendor data under raw/ is immutable and must only ever be
opened read-only (canonical spec section 11).
"""

from __future__ import annotations

from pathlib import Path

from nqresearch.config import _repo_root, load_data_paths_config


def project_root(start: Path | None = None) -> Path:
    """Locate the repository root by walking up until pyproject.toml is found."""
    if start is None:
        return _repo_root()
    p = start.resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError("Could not locate project root (pyproject.toml not found)")


ROOT = project_root()


def data_root() -> Path:
    return load_data_paths_config().resolved_data_root(ROOT)


def raw() -> Path:
    return data_root() / "raw"


def raw_trades() -> Path:
    return raw() / "trades"


def raw_mbp1() -> Path:
    return raw() / "mbp1"


def raw_mbo() -> Path:
    return raw() / "mbo"


def qa() -> Path:
    return data_root() / "qa"


def qa_m0() -> Path:
    return qa() / "m0"


def registry_db() -> Path:
    """DuckDB experiment-registry database (queryable transactional store; the
    per-experiment directories under experiments_dir() are the committed
    lightweight records)."""
    import os

    override = os.environ.get("NQR_REGISTRY_DB")
    return Path(override) if override else data_root() / "registry" / "experiments.duckdb"


def experiments_dir() -> Path:
    """Per-experiment lightweight record directories (canonical §38), kept in
    the Git repository (large outputs are gitignored/redirected)."""
    import os

    override = os.environ.get("NQR_EXPERIMENTS_DIR")
    return Path(override) if override else ROOT / "experiments"
