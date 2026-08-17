"""Cross-source reconciliation: trades extracted from MBP-1 vs standalone trades.

Canonical spec section 13. Both sources come from the same vendor/feed, so this
validates download completeness, parsing, filtering, and event interpretation —
it is not independent market evidence.

Two granularities from one decode pass per file:
- UTC-day (matches the vendor file split);
- CME trading session (sessions reassembled across UTC file boundaries),
  compared only for sessions whose full window is covered by files present in
  BOTH sources.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from nqresearch import dbnio
from nqresearch.filenames import file_date_key
from nqresearch.qa import status as st
from nqresearch.sessions import session_exprs, session_utc_dates

# Relative tolerance above which reconciliation FAILs (spec: discrepancies above
# tolerance stop the pipeline). Identical-feed sources are expected to match exactly.
REL_TOLERANCE = 0.001

_AGG_FIELDS = ["count", "volume", "side_A", "side_B", "side_N",
               "px_min", "px_max", "ts_first", "ts_last"]


def _new_agg() -> dict:
    return {"count": 0, "volume": 0, "side_A": 0, "side_B": 0, "side_N": 0,
            "px_min": None, "px_max": None, "ts_first": None, "ts_last": None}


def _update_agg(a: dict, count, volume, s_a, s_b, s_n, px_min, px_max, ts_first, ts_last):
    a["count"] += count
    a["volume"] += volume
    a["side_A"] += s_a
    a["side_B"] += s_b
    a["side_N"] += s_n
    a["px_min"] = px_min if a["px_min"] is None else min(a["px_min"], px_min)
    a["px_max"] = px_max if a["px_max"] is None else max(a["px_max"], px_max)
    if a["ts_first"] is None:
        a["ts_first"] = ts_first
    a["ts_last"] = ts_last


def file_trade_aggregates(path: Path, chunk_rows: int = dbnio.DEFAULT_CHUNK_ROWS) -> dict:
    """Per-instrument and per-(session, instrument) trade aggregates for one
    daily file (trades schema or MBP-1 with action=='T' filter)."""
    by_iid: dict[int, dict] = defaultdict(_new_agg)
    by_sess_iid: dict[str, dict] = defaultdict(_new_agg)

    for chunk in dbnio.iter_ndarray_chunks(path, chunk_rows):
        mask = chunk["action"] == b"T"
        if not mask.any():
            continue
        iids = chunk["instrument_id"][mask]
        size = chunk["size"][mask].astype(np.int64)
        side = chunk["side"][mask]
        px = chunk["price"][mask].astype(np.int64)
        ts = chunk["ts_event"][mask].astype(np.int64)
        sess = (
            pl.DataFrame({"ts_event": ts})
            .with_columns(session_exprs("ts_event"))["session_id"]
            .cast(pl.Utf8)
            .to_numpy()
        )
        for iid in np.unique(iids):
            mi = iids == iid
            for sk in np.unique(sess[mi]):
                m = mi & (sess == sk)
                args = (
                    int(m.sum()), int(size[m].sum()),
                    int((side[m] == b"A").sum()), int((side[m] == b"B").sum()),
                    int((side[m] == b"N").sum()),
                    int(px[m].min()), int(px[m].max()),
                    int(ts[m][0]), int(ts[m][-1]),
                )
                _update_agg(by_iid[int(iid)], *args)
                _update_agg(by_sess_iid[f"{sk}|{int(iid)}"], *args)

    return {
        "by_instrument": {str(k): v for k, v in by_iid.items()},
        "by_session_instrument": dict(by_sess_iid),
    }


def _merge_maps(maps: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(_new_agg)
    for m in maps:
        for k, v in m.items():
            _update_agg(
                out[k], v["count"], v["volume"], v["side_A"], v["side_B"],
                v["side_N"], v["px_min"], v["px_max"], v["ts_first"], v["ts_last"],
            )
    return dict(out)


def _compare(a: dict[str, dict], b: dict[str, dict], label_a: str, label_b: str):
    mismatches = []
    exact = 0
    for key in sorted(set(a) | set(b)):
        va, vb = a.get(key), b.get(key)
        if va is None or vb is None:
            mismatches.append({"key": key, "issue": "missing_in_" + (label_a if va is None else label_b),
                               label_a: va, label_b: vb})
            continue
        diffs = {f: {label_a: va[f], label_b: vb[f]} for f in _AGG_FIELDS if va[f] != vb[f]}
        if diffs:
            mismatches.append({"key": key, "issue": "field_mismatch", "diffs": diffs})
        else:
            exact += 1
    return exact, mismatches


def _status_from(total_a: int, total_b: int, mismatches: list) -> str:
    rel = abs(total_a - total_b) / max(total_b, 1)
    if not mismatches:
        return st.PASS
    return st.WARN if rel <= REL_TOLERANCE else st.FAIL


def reconcile_overlap(
    mbp1_dir: Path,
    trades_dir: Path,
    chunk_rows: int = dbnio.DEFAULT_CHUNK_ROWS,
    workers: int = 2,
    cache_dir: Path | None = None,
) -> dict:
    """Reconcile every UTC date present in both sources, at UTC-day and
    CME-session granularity."""
    from nqresearch.qa.cache import run_cached

    mbp1_files = {file_date_key(f.name): f for f in sorted(mbp1_dir.rglob("*.mbp-1.dbn.zst"))}
    trades_files = {file_date_key(f.name): f for f in sorted(trades_dir.rglob("*.trades.dbn.zst"))}
    overlap = sorted(set(mbp1_files) & set(trades_files))
    params = {"chunk_rows": chunk_rows, "op": "trade_aggregates"}

    mbp1_aggs = run_cached(
        [mbp1_files[d] for d in overlap], file_trade_aggregates, (chunk_rows,),
        workers, cache_dir / "mbp1" if cache_dir else None, params,
    )
    trades_aggs = run_cached(
        [trades_files[d] for d in overlap], file_trade_aggregates, (chunk_rows,),
        workers, cache_dir / "trades" if cache_dir else None, params,
    )

    # --- UTC-day comparisons (vendor file granularity) ---
    days = []
    for d, ma, ta in zip(overlap, mbp1_aggs, trades_aggs):
        exact, mismatches = _compare(ma["by_instrument"], ta["by_instrument"],
                                     "mbp1", "trades")
        total_m = sum(v["count"] for v in ma["by_instrument"].values())
        total_t = sum(v["count"] for v in ta["by_instrument"].values())
        days.append({
            "utc_date": d,
            "mbp1_file": mbp1_files[d].name,
            "trades_file": trades_files[d].name,
            "instruments_exact_match": exact,
            "total_trades_mbp1": total_m,
            "total_trades_standalone": total_t,
            "relative_count_diff": abs(total_m - total_t) / max(total_t, 1),
            "mismatches": mismatches,
            "status": _status_from(total_m, total_t, mismatches),
        })

    # --- CME-session comparisons (sessions reassembled across UTC files) ---
    overlap_dates = {date(int(d[:4]), int(d[4:6]), int(d[6:8])) for d in overlap}
    m_sess = _merge_maps([a["by_session_instrument"] for a in mbp1_aggs])
    t_sess = _merge_maps([a["by_session_instrument"] for a in trades_aggs])
    observed_sessions = {k.split("|")[0] for k in set(m_sess) | set(t_sess)}
    complete_sessions = sorted(
        s for s in observed_sessions
        if all(d in overlap_dates for d in session_utc_dates(date.fromisoformat(s)))
    )
    m_c = {k: v for k, v in m_sess.items() if k.split("|")[0] in complete_sessions}
    t_c = {k: v for k, v in t_sess.items() if k.split("|")[0] in complete_sessions}
    s_exact, s_mismatches = _compare(m_c, t_c, "mbp1", "trades")
    s_total_m = sum(v["count"] for v in m_c.values())
    s_total_t = sum(v["count"] for v in t_c.values())
    sessions = {
        "complete_sessions_compared": complete_sessions,
        "sessions_excluded_incomplete": sorted(observed_sessions - set(complete_sessions)),
        "pairs_exact_match": s_exact,
        "total_trades_mbp1": s_total_m,
        "total_trades_standalone": s_total_t,
        "mismatches": s_mismatches,
        "status": _status_from(s_total_m, s_total_t, s_mismatches),
    }

    all_statuses = [d["status"] for d in days] + [sessions["status"]]
    return {
        "artifact": "mbp1_trades_reconciliation",
        "overlap_utc_dates": overlap,
        "n_overlap_days": len(overlap),
        "days": days,
        "sessions": sessions,
        "status": st.worst(all_statuses) if all_statuses else st.FAIL,
        "note": (
            "Same-vendor reconciliation validates completeness/parsing only; "
            "it is not statistically independent market evidence (spec section 2.2/13). "
            "Session-level comparison covers only sessions whose full window is "
            "inside the common file set of both sources."
        ),
    }
