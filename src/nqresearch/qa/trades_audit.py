"""Milestone 0 audit of the standalone trades dataset (read-only).

Measures, per canonical spec section 2.1: side population overall / by day /
by RTH vs ETH / by instrument class, action=="T" and depth==0 expectations,
timestamp monotonicity, sequence behaviour, and coverage gaps.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from nqresearch import dbnio, symbols
from nqresearch.filenames import file_utc_date as _file_date
from nqresearch.qa import status as st
from nqresearch.sessions import session_exprs


def audit_file(path: Path) -> dict:
    meta = dbnio.read_metadata(path)
    iid_map = symbols.instrument_map_from_mappings(meta.mappings)
    arr = dbnio.read_ndarray(path)
    n = len(arr)

    ts = arr["ts_event"].astype(np.int64)
    sess_df = pl.DataFrame({"ts_event": ts}).with_columns(session_exprs("ts_event"))
    rth = sess_df["rth_flag"].to_numpy()

    side = arr["side"]
    action = arr["action"]
    depth = arr["depth"]
    size = arr["size"].astype(np.int64)
    iids = arr["instrument_id"]

    uniq_iids = np.unique(iids)
    outright_ids = np.array(
        [
            int(i)
            for i in uniq_iids
            if symbols.classify_symbol(iid_map.get(int(i), "")) == symbols.OUTRIGHT
        ],
        dtype=iids.dtype if n else np.uint32,
    )

    def side_breakdown(mask: np.ndarray) -> dict:
        m = int(mask.sum())
        if m == 0:
            return {"rows": 0}
        return {
            "rows": m,
            "side_A": int(((side == b"A") & mask).sum()),
            "side_B": int(((side == b"B") & mask).sum()),
            "side_N": int(((side == b"N") & mask).sum()),
            "side_N_pct": round(float(((side == b"N") & mask).sum()) / m * 100, 4),
        }

    all_mask = np.ones(n, dtype=bool)
    outright_mask = np.isin(iids, outright_ids) if n else np.array([], dtype=bool)

    nonmono = int((np.diff(ts) < 0).sum()) if n > 1 else 0
    seq = arr["sequence"].astype(np.int64)
    seq_backward = int((np.diff(seq) < 0).sum()) if n > 1 else 0

    non_t = int((action != b"T").sum())
    non_zero_depth = int((depth != 0).sum())

    return {
        "file": path.name,
        "utc_date": _file_date(path.name).isoformat(),
        "size_zst_bytes": path.stat().st_size,
        "n_rows": n,
        "total_volume": int(size.sum()),
        "n_instruments": int(len(uniq_iids)),
        "action_non_T": non_t,
        "depth_non_zero": non_zero_depth,
        "side_all": side_breakdown(all_mask),
        "side_rth": side_breakdown(rth & all_mask),
        "side_eth": side_breakdown(~rth & all_mask),
        "side_outrights": side_breakdown(outright_mask),
        "side_spreads_other": side_breakdown(~outright_mask if n else all_mask),
        "ts_first": int(ts[0]) if n else None,
        "ts_last": int(ts[-1]) if n else None,
        "ts_non_monotonic": nonmono,
        "sequence_backward": seq_backward,
    }


def audit_directory(
    trades_dir: Path, workers: int = 4, cache_dir: Path | None = None
) -> dict:
    """Audit every daily trades file under trades_dir (recursive, both batches)."""
    from nqresearch.qa.cache import run_cached

    files = sorted(trades_dir.rglob("*.trades.dbn.zst"), key=lambda p: p.name)
    reports = run_cached(
        files, audit_file, (), workers, cache_dir, params={"op": "trades_audit"}
    )

    dates = sorted({_file_date(r["file"]) for r in reports})
    missing_weekdays: list[str] = []
    if dates:
        d = dates[0]
        have = set(dates)
        while d <= dates[-1]:
            if d.weekday() < 5 and d not in have:
                missing_weekdays.append(d.isoformat())
            d += timedelta(days=1)

    total_rows = sum(r["n_rows"] for r in reports)
    total_n = sum(r["side_all"].get("side_N", 0) for r in reports)
    daily_n_pct = [
        r["side_all"].get("side_N_pct")
        for r in reports
        if r["side_all"].get("rows", 0) > 0
    ]

    checks = [
        st.check(
            "all_actions_are_T",
            st.PASS if all(r["action_non_T"] == 0 for r in reports) else st.WARN,
            f"files with non-T actions: {sum(1 for r in reports if r['action_non_T'])}",
        ),
        st.check(
            "all_depth_zero",
            st.PASS if all(r["depth_non_zero"] == 0 for r in reports) else st.WARN,
            f"files with non-zero depth: {sum(1 for r in reports if r['depth_non_zero'])}",
        ),
        st.check(
            "ts_event_monotonic",
            st.PASS if all(r["ts_non_monotonic"] == 0 for r in reports) else st.WARN,
            f"files with backward ts_event: {sum(1 for r in reports if r['ts_non_monotonic'])}",
        ),
        st.check(
            "coverage_no_missing_weekdays",
            st.PASS if not missing_weekdays else st.WARN,
            f"{len(missing_weekdays)} missing weekdays (holidays not yet classified): "
            f"{missing_weekdays[:15]}",
        ),
    ]

    return {
        "artifact": "trades_audit",
        "source_dir": str(trades_dir),
        "n_files": len(reports),
        "date_first": dates[0].isoformat() if dates else None,
        "date_last": dates[-1].isoformat() if dates else None,
        "missing_weekdays": missing_weekdays,
        "total_rows": total_rows,
        "total_side_N": total_n,
        "overall_side_N_pct": round(total_n / total_rows * 100, 4) if total_rows else None,
        "daily_side_N_pct_min": min(daily_n_pct) if daily_n_pct else None,
        "daily_side_N_pct_max": max(daily_n_pct) if daily_n_pct else None,
        "files": reports,
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }
