"""PROVISIONAL machine-readable MBO session inventory and block assignment.

This inventory derives sessions from FILENAMES ONLY and is provisional. The
authoritative NQ session inventory comes from the deep audit
(nqresearch.qa.mbo_audit), which decodes records and computes coverage from
NQ outright instruments, excluding other products (e.g. the expected ES.FUT
data in the 2026-05 job) and NQ calendar spreads.

Contiguity rule: two session dates belong to the same block if no
Monday-Friday weekday lies strictly between them (weekends never break a
block; an intervening missing weekday does). CME holidays are not yet
classified and could over-split blocks; this is recorded as an open item.
Block IDs are frozen only after the deep audit and holiday calendar.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from nqresearch.filenames import file_utc_date as _file_date
from nqresearch.qa import status as st


def weekdays_between(a: date, b: date) -> int:
    """Count Mon-Fri days strictly between a and b (a < b)."""
    n = 0
    d = a + timedelta(days=1)
    while d < b:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def assign_blocks(dates: list[date]) -> list[dict]:
    """Group sorted unique dates into contiguous blocks with stable IDs."""
    blocks: list[dict] = []
    current: list[date] = []
    for d in sorted(set(dates)):
        if current and weekdays_between(current[-1], d) > 0:
            blocks.append(current)
            current = []
        current.append(d)
    if current:
        blocks.append(current)
    return [
        {
            "mbo_lab_block_id": f"MBO-BLK-{i + 1:03d}",
            "start": b[0].isoformat(),
            "end": b[-1].isoformat(),
            "n_sessions": len(b),
            "sessions": [d.isoformat() for d in b],
        }
        for i, b in enumerate(blocks)
    ]


def inventory(mbo_dir: Path) -> dict:
    jobs = []
    session_files: dict[str, list[dict]] = {}
    for job_dir in sorted(p for p in mbo_dir.iterdir() if p.is_dir()):
        meta_path = job_dir / "metadata.json"
        meta = json.loads(meta_path.read_text()) if meta_path.is_file() else None
        zst_files = sorted(job_dir.glob("*.dbn.zst"))
        job = {
            "job_dir": job_dir.name,
            "schema": (meta or {}).get("query", {}).get("schema"),
            "symbols": (meta or {}).get("query", {}).get("symbols"),
            "stype_in": (meta or {}).get("query", {}).get("stype_in"),
            "n_files": len(zst_files),
            "bytes": sum(f.stat().st_size for f in zst_files),
            "dates": [_file_date(f.name).isoformat() for f in zst_files],
        }
        jobs.append(job)
        for f in zst_files:
            d = _file_date(f.name).isoformat()
            session_files.setdefault(d, []).append(
                {"job_dir": job_dir.name, "file": f.name, "bytes": f.stat().st_size}
            )

    duplicate_sessions = {d: fs for d, fs in session_files.items() if len(fs) > 1}
    dates = sorted(date.fromisoformat(d) for d in session_files)
    blocks = assign_blocks(dates)

    non_mbo_jobs = [j["job_dir"] for j in jobs if j["schema"] not in (None, "mbo")]
    multi_product_jobs = [
        j["job_dir"] for j in jobs
        if j["symbols"] and set(j["symbols"]) != {"NQ.FUT"}
    ]
    checks = [
        st.check("all_jobs_schema_mbo", st.PASS if not non_mbo_jobs else st.FAIL,
                 f"non-mbo jobs: {non_mbo_jobs}"),
        st.check("multi_product_jobs_identified", st.PASS,
                 f"{len(multi_product_jobs)} jobs queried products beyond NQ.FUT "
                 f"(expected, preserved unchanged): {multi_product_jobs}"),
        st.check("no_duplicate_session_files",
                 st.PASS if not duplicate_sessions else st.WARN,
                 f"{len(duplicate_sessions)} session dates appear in multiple jobs"),
        st.check("holiday_calendar_applied", st.WARN,
                 "Block contiguity uses weekday rule only; CME holiday calendar not yet "
                 "integrated, blocks may be over-split at holidays."),
    ]

    return {
        "artifact": "mbo_inventory",
        "provisional": True,
        "note": (
            "Filename-derived inventory. The authoritative NQ session list and "
            "coverage come from the deep audit artifact (mbo_deep_audit), which "
            "decodes records and filters to NQ outrights."
        ),
        "multi_product_jobs": multi_product_jobs,
        "source_dir": str(mbo_dir),
        "n_jobs": len(jobs),
        "n_session_files": sum(j["n_files"] for j in jobs),
        "n_unique_sessions": len(dates),
        "total_bytes": sum(j["bytes"] for j in jobs),
        "date_first": dates[0].isoformat() if dates else None,
        "date_last": dates[-1].isoformat() if dates else None,
        "duplicate_sessions": duplicate_sessions,
        "jobs": jobs,
        "blocks": blocks,
        "n_blocks": len(blocks),
        "acquisition_reason": (
            "UNRESOLVED: reason each block was originally acquired is not documented "
            "in the data directory; must be supplied by the researcher (spec section 30)."
        ),
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }
