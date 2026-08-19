"""Persistence of machine-readable QA artifacts under data/qa/."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import nqresearch


def _git_sha(root: Path) -> str | None:
    """Current commit SHA, or None when unavailable.

    Must check the return code: on an unborn repository (no commits yet)
    `git rev-parse HEAD` fails but still prints "HEAD" to stdout, which would
    otherwise be recorded as a bogus SHA.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    sha = out.stdout.strip()
    return sha or None


def write_artifact(payload: dict, out_dir: Path, name: str, root: Path) -> Path:
    from nqresearch.rawguard import assert_write_outside_raw

    # Validate the COMPLETED final path (a path-containing artifact name must
    # not escape the checked directory) and write to the resolved result.
    final = assert_write_outside_raw(Path(out_dir) / f"{name}.json")
    final.parent.mkdir(parents=True, exist_ok=True)
    from nqresearch import paths
    from nqresearch.config import effective_config_hash
    from nqresearch.qa.cache import package_source_hash

    envelope = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "nqresearch_version": nqresearch.__version__,
        "git_sha": _git_sha(root),
        "audit_code_hash": package_source_hash(),
        "config_hash": effective_config_hash(),
        "data_root": str(paths.data_root()),
        **payload,
    }
    final.write_text(json.dumps(envelope, indent=2, default=str), encoding="utf-8")
    return final
