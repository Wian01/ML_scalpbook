"""Storage gate for the full two-year MBP-1 purchase (canonical spec 2.2/59).

Checks free space on the volume holding the configured data root. Repeatable:
run again after pointing config/data/paths.yaml (or NQR_DATA_ROOT) at the new
data volume.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from nqresearch.config import StorageGateConfig
from nqresearch.qa import status as st

GB = 1_000_000_000


def _existing_anchor(path: Path) -> Path:
    """Deepest existing ancestor of path (disk_usage needs an existing path)."""
    p = path.resolve()
    while not p.exists():
        parent = p.parent
        if parent == p:
            break
        p = parent
    return p


def storage_gate(
    data_root: Path,
    cfg: StorageGateConfig,
    disk_usage=shutil.disk_usage,
) -> dict:
    anchor = _existing_anchor(data_root)
    usage = disk_usage(anchor)
    free_gb = usage.free / GB
    if free_gb >= cfg.preferred_free_gb:
        gate = st.PASS
        detail = "meets preferred headroom"
    elif free_gb >= cfg.required_free_gb:
        gate = st.WARN
        detail = "meets required minimum but not preferred headroom"
    else:
        gate = st.FAIL
        detail = "below required minimum free space for the full MBP-1 purchase"
    return {
        "artifact": "storage_gate",
        "data_root": str(data_root),
        "measured_volume_anchor": str(anchor),
        "total_gb": round(usage.total / GB, 1),
        "free_gb": round(free_gb, 1),
        "required_free_gb": cfg.required_free_gb,
        "preferred_free_gb": cfg.preferred_free_gb,
        "checks": [st.check("free_space_vs_requirement", gate, detail)],
        "status": gate,
    }
