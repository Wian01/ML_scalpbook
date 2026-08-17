"""Deep MBO audit: decode records to establish actual NQ coverage (read-only).

The file-listing inventory (mbo_inventory) is PROVISIONAL: it derives sessions
from filenames only. This audit decodes every MBO file and establishes, from
NQ **outright** records only (per instrument mappings):

- actual first/last ts_event and per-CME-session row counts;
- RTH coverage (row counts and covered RTH span) per session;
- products present per file (e.g. ES children in the mixed 2026-05 job) and
  excluded record counts (other products, NQ calendar spreads), recorded in QA
  metadata — mixed raw files are expected and preserved unchanged.

The NQ MBO session inventory is then computed from filtered NQ outright RTH
coverage, not from filenames.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import polars as pl

from nqresearch import dbnio, symbols
from nqresearch.filenames import file_utc_date
from nqresearch.qa import status as st
from nqresearch.qa.mbo_inventory import assign_blocks
from nqresearch.sessions import session_exprs

RTH_SPAN_NS = int(6.5 * 3600 * 1e9)  # 08:30-15:00
MIN_RTH_COVERAGE_FRACTION = 0.95
# Session-classification thresholds (QA parameters, not trading parameters):
# ordinary NQ RTH sessions decode to millions of outright rows, while
# file-start initialization records with stale historical timestamps produce
# "ghost" sessions of a few dozen to a few thousand rows that can span the
# RTH window of an unrelated earlier date. Sessions below MIN_TRACE_RTH_ROWS
# are classified as initialization artifacts, not sessions.
MIN_TRACE_RTH_ROWS = 10_000
MIN_FULL_RTH_ROWS = 100_000


def audit_file(path: Path, chunk_rows: int = dbnio.DEFAULT_CHUNK_ROWS) -> dict:
    meta = dbnio.read_metadata(path)
    iid_map = symbols.instrument_map_from_mappings(meta.mappings)
    iid_class = {
        iid: symbols.classify_for_nq_research(sym) for iid, sym in iid_map.items()
    }
    nq_outright_ids = np.array(
        sorted(i for i, c in iid_class.items() if c == symbols.NQ_OUTRIGHT),
        dtype=np.uint32,
    )
    roots_present: dict[str, int] = defaultdict(int)  # product root -> mapped instruments
    for sym in iid_map.values():
        roots_present[symbols.product_root(sym) or "UNPARSED"] += 1

    n_rows = 0
    class_rows = {symbols.NQ_OUTRIGHT: 0, symbols.NQ_CALENDAR_SPREAD: 0,
                  symbols.OTHER_PRODUCT: 0}
    root_rows: dict[str, int] = defaultdict(int)
    unmapped_rows = 0

    nq_first_ts: int | None = None
    nq_last_ts: int | None = None
    sess_rows: dict[str, int] = defaultdict(int)
    sess_rth_rows: dict[str, int] = defaultdict(int)
    sess_rth_first: dict[str, int] = {}
    sess_rth_last: dict[str, int] = {}

    # instrument -> class lookup arrays for vectorized row classification
    all_iids = np.array(sorted(iid_map), dtype=np.uint32)
    all_classes = np.array([iid_class[int(i)] for i in all_iids])
    all_roots = np.array([symbols.product_root(iid_map[int(i)]) or "UNPARSED"
                          for i in all_iids])

    for chunk in dbnio.iter_ndarray_chunks(path, chunk_rows):
        n_rows += len(chunk)
        iids = chunk["instrument_id"]
        idx = np.searchsorted(all_iids, iids)
        idx_valid = (idx < len(all_iids)) & (all_iids[np.minimum(idx, len(all_iids) - 1)] == iids)
        unmapped_rows += int((~idx_valid).sum())
        safe_idx = np.where(idx_valid, np.minimum(idx, len(all_iids) - 1), 0)

        row_class = all_classes[safe_idx]
        for cls in class_rows:
            class_rows[cls] += int(((row_class == cls) & idx_valid).sum())
        row_root = all_roots[safe_idx]
        for r in np.unique(row_root[idx_valid]):
            root_rows[str(r)] += int(((row_root == r) & idx_valid).sum())

        nq_mask = np.isin(iids, nq_outright_ids)
        if not nq_mask.any():
            continue
        ts = chunk["ts_event"][nq_mask].astype(np.int64)
        if nq_first_ts is None:
            nq_first_ts = int(ts[0])
        nq_last_ts = int(ts[-1])

        sess_df = pl.DataFrame({"ts_event": ts}).with_columns(session_exprs("ts_event"))
        sess = sess_df["session_id"].cast(pl.Utf8).to_numpy()
        rth = sess_df["rth_flag"].to_numpy()
        for s in np.unique(sess):
            m = sess == s
            key = str(s)
            sess_rows[key] += int(m.sum())
            mr = m & rth
            if mr.any():
                sess_rth_rows[key] += int(mr.sum())
                ts_r = ts[mr]
                sess_rth_first.setdefault(key, int(ts_r[0]))
                sess_rth_last[key] = int(ts_r[-1])

    sessions = []
    for s in sorted(sess_rows):
        rth_first = sess_rth_first.get(s)
        rth_last = sess_rth_last.get(s)
        span = (rth_last - rth_first) if rth_first is not None else 0
        sessions.append(
            {
                "session_id": s,
                "nq_outright_rows": sess_rows[s],
                "nq_outright_rth_rows": sess_rth_rows.get(s, 0),
                "rth_first_ts": rth_first,
                "rth_last_ts": rth_last,
                "rth_span_coverage": round(span / RTH_SPAN_NS, 4),
            }
        )

    checks = [
        st.check("has_nq_outright_rows",
                 st.PASS if class_rows[symbols.NQ_OUTRIGHT] > 0 else st.FAIL,
                 f"{class_rows[symbols.NQ_OUTRIGHT]} NQ outright rows"),
        st.check("all_instruments_mapped",
                 st.PASS if unmapped_rows == 0 else st.FAIL,
                 f"{unmapped_rows} rows with unmapped instrument_id"),
    ]
    return {
        "file": path.name,
        "job_dir": path.parent.name,
        "utc_date": file_utc_date(path.name).isoformat(),
        "size_zst_bytes": path.stat().st_size,
        "n_rows": n_rows,
        "products_mapped_instruments": dict(sorted(roots_present.items())),
        "rows_by_product_root": dict(sorted(root_rows.items())),
        "excluded_from_nq_research": {
            "other_product_rows": class_rows[symbols.OTHER_PRODUCT],
            "nq_calendar_spread_rows": class_rows[symbols.NQ_CALENDAR_SPREAD],
        },
        "nq_outright": {
            "rows": class_rows[symbols.NQ_OUTRIGHT],
            "ts_first": nq_first_ts,
            "ts_last": nq_last_ts,
            "sessions": sessions,
        },
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }


def audit_directory(
    mbo_dir: Path,
    chunk_rows: int = dbnio.DEFAULT_CHUNK_ROWS,
    workers: int = 3,
    cache_dir: Path | None = None,
) -> dict:
    """Deep-audit every MBO file; derive the NQ session inventory from decoded
    NQ outright RTH coverage."""
    from nqresearch.qa.cache import run_cached

    files = sorted(mbo_dir.rglob("*.mbo.dbn.zst"), key=lambda p: p.name)
    reports = run_cached(
        files, audit_file, (chunk_rows,), workers, cache_dir,
        params={"chunk_rows": chunk_rows, "op": "mbo_deep_audit"},
    )

    # NQ research session inventory: sessions with substantial RTH coverage.
    session_cov: dict[str, dict] = {}
    for r in reports:
        for s in r["nq_outright"]["sessions"]:
            prev = session_cov.get(s["session_id"])
            if prev is None:
                session_cov[s["session_id"]] = {**s, "files": [r["file"]]}
            else:
                prev["nq_outright_rows"] += s["nq_outright_rows"]
                prev["nq_outright_rth_rows"] += s["nq_outright_rth_rows"]
                prev["rth_span_coverage"] = round(
                    prev["rth_span_coverage"] + s["rth_span_coverage"], 4
                )
                prev["files"].append(r["file"])

    trace_sessions = sorted(
        s for s, cov in session_cov.items()
        if cov["nq_outright_rth_rows"] < MIN_TRACE_RTH_ROWS
    )
    full_sessions = sorted(
        s for s, cov in session_cov.items()
        if cov["rth_span_coverage"] >= MIN_RTH_COVERAGE_FRACTION
        and cov["nq_outright_rth_rows"] >= MIN_FULL_RTH_ROWS
    )
    partial_sessions = sorted(
        set(session_cov) - set(trace_sessions) - set(full_sessions)
    )
    from datetime import date

    blocks = assign_blocks([date.fromisoformat(s) for s in full_sessions])

    mixed_files = [r["file"] for r in reports
                   if r["excluded_from_nq_research"]["other_product_rows"] > 0]
    checks = [
        st.check("all_files_have_nq_outright_data",
                 st.worst(r["status"] for r in reports) if reports else st.FAIL,
                 f"{sum(1 for r in reports if r['status'] != st.PASS)} files flagged"),
        st.check("mixed_product_files_identified", st.PASS,
                 f"{len(mixed_files)} files contain non-NQ products (expected, "
                 f"e.g. ES.FUT job); records excluded from NQ research and "
                 f"recorded per file"),
        st.check("holiday_calendar_applied", st.WARN,
                 "Blocks remain provisional: CME holiday calendar not yet "
                 "integrated; contiguity uses the weekday rule."),
    ]
    return {
        "artifact": "mbo_deep_audit",
        "source_dir": str(mbo_dir),
        "n_files": len(reports),
        "session_classification_thresholds": {
            "min_rth_span_coverage": MIN_RTH_COVERAGE_FRACTION,
            "min_full_rth_rows": MIN_FULL_RTH_ROWS,
            "min_trace_rth_rows": MIN_TRACE_RTH_ROWS,
        },
        "n_sessions_full_rth": len(full_sessions),
        "n_sessions_partial_rth": len(partial_sessions),
        "n_initialization_artifact_dates": len(trace_sessions),
        "full_rth_sessions": full_sessions,
        "partial_rth_sessions": [
            {"session_id": s, **{k: session_cov[s][k] for k in
             ("nq_outright_rth_rows", "rth_span_coverage")}}
            for s in partial_sessions
        ],
        "initialization_artifact_dates": [
            {"session_id": s, "nq_outright_rth_rows":
             session_cov[s]["nq_outright_rth_rows"]}
            for s in trace_sessions
        ],
        "session_coverage": {s: session_cov[s] for s in sorted(session_cov)},
        "blocks_provisional": blocks,
        "n_blocks_provisional": len(blocks),
        "mixed_product_files": mixed_files,
        "files": reports,
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }
