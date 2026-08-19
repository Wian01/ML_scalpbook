"""Raw-data write protection (canonical §11, §61).

Raw vendor data under <data_root>/raw is immutable: read-only access only.
This module gives derived-output code a mandatory destination check that
refuses any path inside the raw tree, resisting relative paths, `..`
components, symlink/junction aliases (via strict resolution of the deepest
existing ancestor), and Windows case differences.
"""

from __future__ import annotations

import os
from pathlib import Path


class RawWriteError(RuntimeError):
    pass


def _resolve_existing_anchor(path: Path) -> Path:
    """Resolve the deepest EXISTING ancestor (following links/junctions), then
    re-append the non-existent tail — so aliases of the raw tree cannot hide a
    destination that would land inside it. os.path.abspath handles Windows
    drive-relative forms such as 'D:file' against the per-drive CWD."""
    p = Path(os.path.abspath(str(path)))
    tail: list[str] = []
    probe = p
    while not probe.exists():
        tail.append(probe.name)
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    resolved = probe.resolve()
    for name in reversed(tail):
        resolved = resolved / name
    return resolved


def _is_within(child: Path, parent: Path) -> bool:
    a = str(child)
    b = str(parent)
    if os.name == "nt":
        a, b = a.casefold(), b.casefold()
    a_parts = Path(a).parts
    b_parts = Path(b).parts
    return a_parts[: len(b_parts)] == b_parts


def assert_write_outside_raw(dest: Path, data_root: Path | None = None) -> Path:
    """Refuse any write destination inside <data_root>/raw. Returns the fully
    resolved destination for the caller to use."""
    from nqresearch import paths

    root = (data_root or paths.data_root())
    raw = _resolve_existing_anchor(Path(root) / "raw")
    resolved = _resolve_existing_anchor(Path(dest))
    if _is_within(resolved, raw):
        raise RawWriteError(
            f"destination {dest} resolves to {resolved}, inside the immutable "
            f"raw tree {raw}: writes are forbidden (canonical §11)"
        )
    return resolved
