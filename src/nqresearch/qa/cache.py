"""Resumable per-file audit cache with versioned keys.

A cached result is reused only when ALL key components match:
- source file path relative to the data root;
- vendor content identity (SHA-256 from the vendor manifest when available,
  otherwise file size + mtime as a weaker fallback, recorded as such);
- audit code hash (SHA-256 over the nqresearch package source tree — any code
  change invalidates every cache);
- the audit parameters relevant to the computation.

Filename+size alone are never sufficient (a re-downloaded or edited file, or
changed audit code, must recompute).
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from nqresearch import paths

CACHE_SCHEMA_VERSION = 2


@lru_cache(maxsize=1)
def package_source_hash() -> str:
    """SHA-256 over the package's .py sources (sorted, path-tagged)."""
    pkg_dir = Path(__file__).resolve().parent.parent
    h = hashlib.sha256()
    for f in sorted(pkg_dir.rglob("*.py")):
        h.update(str(f.relative_to(pkg_dir)).encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


@lru_cache(maxsize=32)
def _manifest_hashes(job_dir: Path) -> dict[str, str]:
    """filename -> 'sha256:...' from a job directory's vendor manifest.json."""
    manifest = job_dir / "manifest.json"
    if not manifest.is_file():
        return {}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return {f["filename"]: f.get("hash", "") for f in data.get("files", [])}


def vendor_identity(file: Path) -> dict:
    """Vendor content identity for a raw file.

    Uses the vendor manifest SHA-256 when available, and always also includes
    size + mtime so an on-disk modification invalidates the cache even if the
    manifest was not regenerated.
    """
    vendor_hash = _manifest_hashes(file.parent).get(file.name)
    stat = file.stat()
    return {
        "vendor_hash": vendor_hash,
        "identity_source": "manifest" if vendor_hash else "size_mtime_fallback",
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def cache_key(file: Path, params: dict) -> dict:
    from nqresearch.config import effective_config_hash

    try:
        relpath = str(file.resolve().relative_to(paths.data_root().resolve()))
    except ValueError:
        relpath = str(file.resolve())
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "source_relpath": relpath,
        **vendor_identity(file),
        "audit_code_hash": package_source_hash(),
        "config_hash": effective_config_hash(),
        "params": params,
    }


def run_cached(
    files: list[Path],
    worker_fn,
    fn_args: tuple,
    workers: int,
    cache_dir: Path | None,
    params: dict,
) -> list[dict]:
    """Run worker_fn(file, *fn_args) per file with a resumable versioned cache.

    Results are written to the cache as soon as each file completes, so an
    interrupted run resumes without re-decoding finished files.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    reports: dict[str, dict] = {}
    todo: list[Path] = []
    for f in files:
        cpath = cache_dir / f"{f.name}.json" if cache_dir else None
        if cpath is not None and cpath.is_file():
            entry = json.loads(cpath.read_text(encoding="utf-8"))
            if entry.get("_cache_key") == cache_key(f, params):
                reports[f.name] = entry["result"]
                continue
        todo.append(f)

    def _store(f: Path, result: dict) -> None:
        reports[f.name] = result
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            entry = {"_cache_key": cache_key(f, params), "result": result}
            (cache_dir / f"{f.name}.json").write_text(
                json.dumps(entry, default=str), encoding="utf-8"
            )

    if todo and workers > 1 and len(todo) > 1:
        with ProcessPoolExecutor(max_workers=min(workers, len(todo))) as pool:
            futures = {pool.submit(worker_fn, f, *fn_args): f for f in todo}
            for fut in as_completed(futures):
                _store(futures[fut], fut.result())
    else:
        for f in todo:
            _store(f, worker_fn(f, *fn_args))

    return [reports[f.name] for f in files]
