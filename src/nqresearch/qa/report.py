"""Persistence of machine-readable QA artifacts under data/qa/.

The envelope layer is the single authority for generation provenance:
- it determines the committed HEAD SHA and whether the working tree is
  COMPLETELY clean (tracked, staged AND untracked) at generation time, and
  stamps the machine-readable `generation_git_clean` boolean plus a
  dynamically accurate `restamp_note`;
- reserved envelope keys can never be supplied (or forged) through an
  ordinary artifact payload — collisions fail loudly;
- there is NO override or allow-dirty escape: dirty-tree generation stays
  available for pre-commit inspection but is stamped ineligible for
  provenance acceptance, and require_provenance() refuses such artifacts.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import nqresearch

# Envelope fields owned exclusively by this layer. A payload supplying any
# of them is a caller bug and fails loudly — silent overwrites of identity
# fields (git_sha, config_hash, ...) must be impossible.
RESERVED_ENVELOPE_KEYS = frozenset({
    "generated_at_utc",
    "nqresearch_version",
    "git_sha",
    "generation_git_clean",
    "restamp_note",
    "audit_code_hash",
    "config_hash",
    "data_root",
})

_CLEAN_NOTE = (
    "Generated from a clean committed tree at the recorded git_sha."
)
_DIRTY_NOTE = (
    "Generated from an uncommitted or unverifiable working tree "
    "(generation_git_clean=false): NOT eligible for provenance acceptance. "
    "Regenerate from a clean committed tree."
)


class ReservedEnvelopeKeyError(ValueError):
    """An artifact payload tried to supply a reserved envelope field."""


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


def _git_clean(root: Path, sha: str | None) -> bool:
    """True ONLY when HEAD exists and the repository is completely clean:
    no unstaged tracked changes, no staged changes, no untracked files
    (`git status --porcelain` default listing covers all three). Any git
    failure or unverifiable state is False — never a silent pass."""
    if sha is None:
        return False
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
    except OSError:
        return False
    if out.returncode != 0:
        return False
    return out.stdout.strip() == ""


def write_artifact(payload: dict, out_dir: Path, name: str, root: Path) -> Path:
    from nqresearch.rawguard import assert_write_outside_raw

    clash = RESERVED_ENVELOPE_KEYS & set(payload)
    if clash:
        raise ReservedEnvelopeKeyError(
            f"artifact payload for {name!r} supplies reserved envelope "
            f"field(s) {sorted(clash)}: the envelope layer is the single "
            "authority for generation provenance; refusing"
        )
    # Validate the COMPLETED final path (a path-containing artifact name must
    # not escape the checked directory) and write to the resolved result.
    final = assert_write_outside_raw(Path(out_dir) / f"{name}.json")
    final.parent.mkdir(parents=True, exist_ok=True)
    from nqresearch import paths
    from nqresearch.config import effective_config_hash
    from nqresearch.qa.cache import package_source_hash

    sha = _git_sha(root)
    clean = _git_clean(root, sha)
    envelope = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "nqresearch_version": nqresearch.__version__,
        "git_sha": sha,
        "generation_git_clean": clean,
        "restamp_note": _CLEAN_NOTE if clean else _DIRTY_NOTE,
        "audit_code_hash": package_source_hash(),
        "config_hash": effective_config_hash(),
        "data_root": str(paths.data_root()),
        **payload,
    }
    final.write_text(json.dumps(envelope, indent=2, default=str), encoding="utf-8")
    return final
