"""Vendor manifest validation (read-only).

Every Databento batch job directory ships a manifest.json listing each file
with its size and SHA-256. This audit verifies presence, size, and hash of
every manifested file, and flags data files present on disk but absent from
the manifest. Raw files are opened read-only and never modified.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from nqresearch.qa import status as st

_HASH_CHUNK = 8 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _check_entry(job_dir_str: str, filename: str, size: int, hash_field: str) -> dict:
    path = Path(job_dir_str) / filename
    out = {"job_dir": Path(job_dir_str).name, "filename": filename}
    if not path.is_file():
        out.update(status=st.FAIL, issue="missing")
        return out
    actual_size = path.stat().st_size
    if actual_size != size:
        out.update(
            status=st.FAIL, issue="size_mismatch",
            expected_size=size, actual_size=actual_size,
        )
        return out
    expected = hash_field.removeprefix("sha256:")
    actual = sha256_file(path)
    if actual != expected:
        out.update(
            status=st.FAIL, issue="sha256_mismatch",
            expected_sha256=expected, actual_sha256=actual,
        )
        return out
    out.update(status=st.PASS)
    return out


def find_job_dirs(raw_dir: Path) -> tuple[list[Path], list[Path]]:
    """Job directories under the raw tree: (with manifest, WITHOUT manifest).

    A job directory is any directory directly containing .dbn.zst data files.
    Directories without a manifest.json cannot be hash-verified and must be
    surfaced, not silently skipped.
    """
    with_manifest = {p.parent for p in raw_dir.rglob("manifest.json")}
    data_dirs = {p.parent for p in raw_dir.rglob("*.dbn.zst")}
    missing = data_dirs - with_manifest
    return (
        sorted(with_manifest, key=str),
        sorted(missing, key=str),
    )


def validate_raw_tree(raw_dir: Path, workers: int = 4) -> dict:
    """Validate every job manifest under the raw data tree."""
    job_dirs, dirs_without_manifest = find_job_dirs(raw_dir)
    tasks: list[tuple[str, str, int, str]] = []
    unmanifested: list[str] = []
    jobs_meta = []
    for job_dir in job_dirs:
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        entries = manifest.get("files", [])
        listed = {e["filename"] for e in entries}
        jobs_meta.append({"job_dir": str(job_dir), "n_manifested_files": len(entries)})
        for e in entries:
            tasks.append((str(job_dir), e["filename"], e["size"], e.get("hash", "")))
        for f in job_dir.iterdir():
            if f.is_file() and f.name not in listed and f.name != "manifest.json":
                unmanifested.append(str(f.relative_to(raw_dir)))

    if workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_check_entry, *zip(*tasks), chunksize=4))
    else:
        results = [_check_entry(*t) for t in tasks]

    failures = [r for r in results if r["status"] != st.PASS]
    checks = [
        st.check(
            "all_manifested_files_valid",
            st.PASS if not failures else st.FAIL,
            f"{len(failures)} of {len(results)} files failed presence/size/sha256",
        ),
        st.check(
            "no_unmanifested_data_files",
            st.PASS if not unmanifested else st.WARN,
            f"{len(unmanifested)} files on disk not listed in any manifest: "
            f"{unmanifested[:10]}",
        ),
        st.check(
            "all_job_dirs_have_manifest",
            st.PASS if not dirs_without_manifest else st.WARN,
            f"{len(dirs_without_manifest)} data directories have no manifest.json; "
            f"their files cannot be hash-verified against the vendor: "
            f"{[d.name for d in dirs_without_manifest]}",
        ),
    ]
    return {
        "artifact": "manifest_validation",
        "raw_dir": str(raw_dir),
        "n_job_dirs": len(job_dirs),
        "n_files_checked": len(results),
        "jobs": jobs_meta,
        "failures": failures,
        "unmanifested_files": unmanifested,
        "job_dirs_without_manifest": [
            {
                "job_dir": str(d.relative_to(raw_dir)),
                "n_data_files": len(list(d.glob("*.dbn.zst"))),
            }
            for d in dirs_without_manifest
        ],
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }
