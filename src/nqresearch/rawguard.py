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


class PathContainmentError(RuntimeError):
    """A declared relative path escapes (or is not safely relative to) its
    required root."""


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


def is_contained(child: Path, parent: Path) -> bool:
    """True iff `child` — after strict resolution of links/junctions via the
    deepest existing ancestor — lies inside the equally-resolved `parent`.
    Segment-wise and casefolded on Windows: immune to prefix collisions
    (…/root2 is never inside …/root)."""
    return _is_within(_resolve_existing_anchor(child),
                      _resolve_existing_anchor(parent))


def resolve_strictly_contained(root: Path, relpath: str) -> Path:
    """Windows-safe containment resolver for DECLARED relative paths.

    Rejects up front: empty values; absolute paths; drive-qualified and
    drive-relative forms ('C:\\x', 'D:file'); root-relative forms ('\\x',
    '/x') and UNC paths ('\\\\server\\share'); any '..' component. Then
    resolves root/relpath (following symlinks/junctions via the deepest
    existing ancestor) and requires the RESOLVED target to remain inside the
    resolved root — so alias/junction escapes and prefix-collision
    directories fail even when the target file exists with a matching hash.

    Returns the resolved path; callers MUST use it for the actual read so
    validation and reading can never operate on different paths.
    """
    import re

    if not isinstance(relpath, str) or not relpath.strip():
        raise PathContainmentError("empty or non-string path")
    s = relpath.strip()
    if re.match(r"^[A-Za-z]:", s):
        raise PathContainmentError(
            f"drive-qualified/drive-relative path {relpath!r} is not a "
            "relative path inside its root"
        )
    if s.startswith(("\\", "/")):
        raise PathContainmentError(
            f"root-relative/UNC/absolute path {relpath!r} is not a relative "
            "path inside its root"
        )
    if Path(s).is_absolute():
        raise PathContainmentError(f"absolute path {relpath!r} refused")
    parts = [p for p in re.split(r"[\\/]+", s) if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise PathContainmentError(
            f"path {relpath!r} contains '..' traversal (or is empty); refused"
        )
    root_resolved = _resolve_existing_anchor(Path(root))
    resolved = _resolve_existing_anchor(Path(root).joinpath(*parts))
    if not _is_within(resolved, root_resolved):
        raise PathContainmentError(
            f"path {relpath!r} resolves to {resolved}, outside its required "
            f"root {root_resolved}; refused"
        )
    return resolved


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
