"""Milestone 0 closeout: full-history MBP-1 session-coverage audit.

Read-only, streamed/chunked, resumable (versioned caches), disk-guarded.
Input files come ONLY from registry-selected FULL_HISTORY_CANONICAL sources
(the QA-only sample can never enter). Artifacts go to
<data_root>/qa/m0_closeout/ — historical qa/m0 and acquisition artifacts are
never overwritten. Produces the per-session QA fields of canonical §12.
"""

from __future__ import annotations

import shutil
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from nqresearch import dbnio, symbols
from nqresearch.calendar import (
    STATUS_SHORTENED,
    load_calendar,
)
from nqresearch.flags import FLAG_BITS, UNDEF_PRICE
from nqresearch.qa import status as st
from nqresearch.sessions import session_exprs

MIN_FREE_BYTES = 100 * 1_000_000_000  # disk guard for cache/artifact writes
MBP1_RECORD_BYTES = 80


def _disk_guard(data_root: Path) -> None:
    free = shutil.disk_usage(data_root).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(
            f"disk guard: only {free / 1e9:.1f} GB free on the data volume "
            f"(< {MIN_FREE_BYTES / 1e9:.0f} GB) — refusing to run the "
            "coverage audit"
        )


def _session_close_ns(session_iso: str) -> int | None:
    """UTC-ns epoch of the session's calendar close (early or normal)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    cal = load_calendar()
    d = date.fromisoformat(session_iso)
    close = cal.close_time_ct(d)
    if close is None:
        return None
    dt = datetime(d.year, d.month, d.day, close.hour, close.minute,
                  tzinfo=ZoneInfo("America/Chicago"))
    return int(dt.timestamp()) * 1_000_000_000


def audit_file(path: Path, chunk_rows: int = dbnio.DEFAULT_CHUNK_ROWS) -> dict:
    """Lean single-pass coverage stats for one canonical daily file.

    File-leading initialization records (stale ts_event < the file's query
    start; vendor packetization semantics, audit-log AL-0004) are excluded
    from session statistics and counted separately — otherwise their stale
    RTH-window timestamps fabricate feed gaps in neighboring sessions.
    RTH statistics are bounded at each session's calendar close so expected
    post-early-close halts are not measured as gaps.
    """
    meta = dbnio.read_metadata(path)
    file_start_ns = int(meta.start)
    iid_map = symbols.instrument_map_from_mappings(meta.mappings)
    outright_ids = np.array(
        sorted(i for i, s in iid_map.items()
               if symbols.classify_symbol(s) == symbols.OUTRIGHT),
        dtype=np.uint32,
    )
    close_ns_cache: dict[str, int | None] = {}
    init_records_excluded = 0

    n_rows = 0
    f_last = 0
    nonmono = 0
    prev_ts = None
    crossed_f_last = 0
    zero_size_trades = 0
    action_counts: dict[str, int] = defaultdict(int)
    unknown_flag_rows = 0
    known_mask = np.uint8(sum(FLAG_BITS.values()))

    # (session, iid) -> [rows, trades, volume, sideA, sideB, sideN, rth_rows]
    si: dict[tuple[str, int], np.ndarray] = defaultdict(
        lambda: np.zeros(7, dtype=np.int64)
    )
    sess_ts: dict[str, list[int]] = {}
    rth_ts: dict[str, list[int]] = {}
    rth_gap: dict[str, int] = defaultdict(int)
    rth_last: dict[str, int] = {}

    for chunk in dbnio.iter_ndarray_chunks(path, chunk_rows):
        ts_all = chunk["ts_event"].astype(np.int64)
        fresh = ts_all >= file_start_ns
        if not fresh.all():
            init_records_excluded += int((~fresh).sum())
            chunk = chunk[fresh]
        n = len(chunk)
        n_rows += n
        if n == 0:
            continue
        ts = chunk["ts_event"].astype(np.int64)
        flags = chunk["flags"]
        f_last_mask = (flags & FLAG_BITS["F_LAST"]) != 0
        f_last += int(f_last_mask.sum())
        unknown_flag_rows += int((flags & ~known_mask != 0).sum())
        if prev_ts is not None and n and int(ts[0]) < prev_ts:
            nonmono += 1
        if n > 1:
            nonmono += int((np.diff(ts) < 0).sum())
        if n:
            prev_ts = int(ts[-1])

        for a, c in zip(*np.unique(chunk["action"], return_counts=True)):
            action_counts[a.decode()] += int(c)

        iids = chunk["instrument_id"]
        outright_mask = np.isin(iids, outright_ids)
        bid, ask = chunk["bid_px_00"], chunk["ask_px_00"]
        ok = (bid != UNDEF_PRICE) & (ask != UNDEF_PRICE) & outright_mask & f_last_mask
        crossed_f_last += int((ask[ok] < bid[ok]).sum())

        is_trade = chunk["action"] == b"T"
        size = chunk["size"].astype(np.int64)
        zero_size_trades += int((is_trade & (size == 0)).sum())

        sess_df = pl.DataFrame({"ts_event": ts}).with_columns(session_exprs("ts_event"))
        sess = sess_df["session_id"].cast(pl.Utf8).to_numpy()
        rth = sess_df["rth_flag"].to_numpy()

        for s in np.unique(sess):
            m = sess == s
            ts_s = ts[m]
            sess_ts.setdefault(s, [int(ts_s[0]), int(ts_s[-1])])
            sess_ts[s][1] = int(ts_s[-1])
            mr = m & rth
            if s not in close_ns_cache:
                close_ns_cache[s] = _session_close_ns(str(s))
            close_ns = close_ns_cache[s]
            if close_ns is not None:
                mr = mr & (ts < close_ns)
            if mr.any():
                ts_r = ts[mr]
                rth_ts.setdefault(s, [int(ts_r[0]), int(ts_r[-1])])
                rth_ts[s][1] = int(ts_r[-1])
                gaps = np.diff(ts_r)
                g = int(gaps.max()) if len(gaps) else 0
                if s in rth_last:
                    g = max(g, int(ts_r[0]) - rth_last[s])
                rth_gap[s] = max(rth_gap[s], g)
                rth_last[s] = int(ts_r[-1])
            for i in np.unique(iids[m]):
                mi = m & (iids == i)
                acc = si[(s, int(i))]
                acc[0] += int(mi.sum())
                mt = mi & is_trade
                if mt.any():
                    acc[1] += int(mt.sum())
                    acc[2] += int(size[mt].sum())
                    sd = chunk["side"][mt]
                    acc[3] += int((sd == b"A").sum())
                    acc[4] += int((sd == b"B").sum())
                    acc[5] += int((sd == b"N").sum())
                acc[6] += int((mi & mr).sum())

    sessions_out = {}
    for (s, iid), acc in si.items():
        entry = sessions_out.setdefault(
            s, {"instruments": {}, "ts_first": sess_ts[s][0],
                "ts_last": sess_ts[s][1],
                "rth_first": rth_ts.get(s, [None, None])[0],
                "rth_last": rth_ts.get(s, [None, None])[1],
                "rth_max_gap_ns": rth_gap.get(s, 0)}
        )
        entry["instruments"][str(iid)] = {
            "symbol": iid_map.get(iid, "<unmapped>"),
            "rows": int(acc[0]), "trades": int(acc[1]), "volume": int(acc[2]),
            "side_A": int(acc[3]), "side_B": int(acc[4]), "side_N": int(acc[5]),
            "rth_rows": int(acc[6]),
        }
    first_fresh = min((v[0] for v in sess_ts.values()), default=None)
    last_fresh = max((v[1] for v in sess_ts.values()), default=None)
    return {
        "file": path.name,
        "n_rows": n_rows,
        "ts_first_fresh": first_fresh,
        "ts_last_fresh": last_fresh,
        "init_records_excluded": init_records_excluded,
        "f_last_rows": f_last,
        "ts_non_monotonic": nonmono,
        "crossed_f_last_outright": crossed_f_last,
        "zero_size_trades": zero_size_trades,
        "unknown_flag_rows": unknown_flag_rows,
        "action_counts": dict(action_counts),
        "est_decoded_bytes": n_rows * MBP1_RECORD_BYTES,
        "sessions": sessions_out,
    }


DEGRADED_DATES = [
    "2024-09-18", "2025-09-17", "2025-09-24", "2025-11-28", "2026-01-31",
    "2026-03-15", "2026-03-16", "2026-03-21", "2026-04-10", "2026-05-24",
    "2026-07-30",
]
FIRST_COMPLETE_SESSION = date(2024, 8, 19)
LAST_COMPLETE_SESSION = date(2026, 8, 14)
RTH_GAP_WARN_NS = int(120e9)
RTH_GAP_FAIL_NS = int(600e9)


def aggregate(file_reports: list[dict]) -> dict:
    """Merge per-file stats into per-session QA rows + summary (§12)."""
    cal = load_calendar()
    sessions: dict[str, dict] = {}
    for fr in file_reports:
        for s, data in fr["sessions"].items():
            cur = sessions.get(s)
            if cur is None:
                sessions[s] = {
                    "instruments": dict(data["instruments"]),
                    "ts_first": data["ts_first"], "ts_last": data["ts_last"],
                    "rth_first": data["rth_first"], "rth_last": data["rth_last"],
                    "rth_max_gap_ns": data["rth_max_gap_ns"],
                    "files": [fr["file"]],
                }
                continue
            cur["files"].append(fr["file"])
            cur["ts_first"] = min(cur["ts_first"], data["ts_first"])
            cur["ts_last"] = max(cur["ts_last"], data["ts_last"])
            for k in ("rth_first", "rth_last"):
                if data[k] is not None:
                    cur[k] = (data[k] if cur[k] is None else
                              (min if k == "rth_first" else max)(cur[k], data[k]))
            cur["rth_max_gap_ns"] = max(cur["rth_max_gap_ns"], data["rth_max_gap_ns"])
            for iid, rec in data["instruments"].items():
                tgt = cur["instruments"].get(iid)
                if tgt is None:
                    cur["instruments"][iid] = dict(rec)
                else:
                    for k in ("rows", "trades", "volume", "side_A", "side_B",
                              "side_N", "rth_rows"):
                        tgt[k] += rec[k]

    session_rows = []
    expected, missing, missing_pre_rth_short = [], [], []
    d = FIRST_COMPLETE_SESSION
    while d <= LAST_COMPLETE_SESSION:
        if cal.is_trading_day(d):
            expected.append(d.isoformat())
            if d.isoformat() not in sessions:
                exp = cal.expected_rth_span_seconds(d)
                if exp == 0:
                    # e.g. Good Friday 2025-04-18: session closes 08:15 CT
                    # (before RTH); observed vendor file is initialization-only
                    # — no fresh events at all. WARN, not FAIL.
                    missing_pre_rth_short.append(d.isoformat())
                else:
                    missing.append(d.isoformat())
        d += timedelta(days=1)

    front_volumes: dict[str, dict[str, int]] = {}
    preopen_remnant_dates = 0
    for s in sorted(sessions):
        data = sessions[s]
        sd = date.fromisoformat(s)
        status_cal = cal.session_status(sd)
        rows_total = sum(r["rows"] for r in data["instruments"].values())
        if sd.weekday() >= 5 or (
            status_cal == "holiday" and rows_total < 100_000
        ):
            # Pre-open records (16:00-17:00 CT before the next session's open)
            # date to the weekend/holiday itself under the boundary rule; they
            # are session-open mechanics of the FOLLOWING session, not
            # sessions (e.g. the Globex reopen on Christmas evening).
            # Counted, not QA-scored.
            preopen_remnant_dates += 1
            continue
        in_range = FIRST_COMPLETE_SESSION <= sd <= LAST_COMPLETE_SESSION
        reasons: list[str] = []
        is_override = cal.is_override(sd)
        outr = {
            rec["symbol"]: rec for rec in data["instruments"].values()
            if symbols.classify_symbol(rec["symbol"]) == symbols.OUTRIGHT
        }
        front_volumes[s] = {sym: rec["volume"] for sym, rec in outr.items()}
        exp_span = cal.expected_rth_span_seconds(sd)
        obs_span = (
            (data["rth_last"] - data["rth_first"]) / 1e9
            if data["rth_first"] is not None else 0.0
        )
        # Shortened sessions' generic-RTH span is capped by the early close.
        span_frac = (obs_span / exp_span) if exp_span else None
        if not in_range:
            reasons.append("EDGE_PARTIAL_QUERY_BOUNDARY")
            qa = st.WARN
        elif not cal.is_trading_day(sd):
            reasons.append("UNEXPECTED_NON_TRADING_DAY_DATA")
            qa = st.WARN
        else:
            qa = st.PASS
            if exp_span and exp_span > 0:
                if data["rth_first"] is None or (
                    span_frac is not None and span_frac < 0.05
                ):
                    # ETH data exists but (essentially) zero RTH on a calendar
                    # trading day: calendar/observation mismatch (e.g. the
                    # 2025-01-09 special closure not encoded by the snapshot
                    # source). Flag for review; never hand-patch the snapshot
                    # from memory.
                    qa = st.WARN
                    reasons.append("NO_RTH_DATA_CALENDAR_MISMATCH")
                elif span_frac is not None and span_frac < 0.95:
                    qa = st.FAIL
                    reasons.append("RTH_COVERAGE_INCOMPLETE")
            elif exp_span == 0:
                if is_override:
                    # Official special closure (e.g. 2025-01-09 National Day
                    # of Mourning, 08:30 CT halt): zero expected RTH observed
                    # as zero actual RTH. WARN so eligibility stays a
                    # deliberate decision.
                    qa = st.WARN
                    reasons.append("OFFICIAL_SPECIAL_CLOSURE_NO_RTH")
                else:
                    reasons.append("SESSION_ENDS_BEFORE_RTH")  # Good Friday
            if data["rth_max_gap_ns"] > RTH_GAP_FAIL_NS:
                qa = st.FAIL
                reasons.append("RTH_FEED_GAP_OVER_10MIN")
            elif data["rth_max_gap_ns"] > RTH_GAP_WARN_NS:
                qa = st.WARN if qa == st.PASS else qa
                reasons.append("RTH_FEED_GAP_OVER_2MIN")
            if status_cal == STATUS_SHORTENED:
                reasons.append("SHORTENED_SESSION_PER_CALENDAR")
            if s in DEGRADED_DATES:
                qa = st.WARN if qa == st.PASS else qa
                reasons.append("VENDOR_CONDITION_DEGRADED")
        total_vol = sum(front_volumes[s].values())
        session_rows.append({
            "session_id": s,
            "calendar_status": status_cal,
            "qa_status": qa,
            "reason_codes": reasons,
            "n_instruments": len(data["instruments"]),
            "outright_symbols": sorted(outr),
            "ts_first": data["ts_first"], "ts_last": data["ts_last"],
            "rth_span_seconds": round(obs_span, 1),
            "expected_rth_span_seconds": exp_span,
            "rth_max_gap_ms": round(data["rth_max_gap_ns"] / 1e6, 1),
            "rows": sum(r["rows"] for r in data["instruments"].values()),
            "trades": sum(r["trades"] for r in data["instruments"].values()),
            "volume": total_vol,
            "side_N_trades": sum(r["side_N"] for r in data["instruments"].values()),
            "instruments": data["instruments"],
        })

    # Headline counters cover ONLY the declared evaluation range; anything
    # outside it (the 2026-08-17 query-boundary edge) is reported separately.
    in_range_rows = [r for r in session_rows
                     if FIRST_COMPLETE_SESSION
                     <= date.fromisoformat(r["session_id"])
                     <= LAST_COMPLETE_SESSION]
    out_of_range_rows = [r for r in session_rows if r not in in_range_rows]
    session_rows = in_range_rows

    # The front-contract series input covers ONLY in-range sessions: the
    # 2026-08-17 partial edge (and any other out-of-range date) is excluded
    # so it can never seed downstream research through the front artifact.
    out_of_range_ids = {r["session_id"] for r in out_of_range_rows}
    front_volumes = {k: v for k, v in front_volumes.items()
                     if k not in out_of_range_ids}

    ordered_files = sorted(file_reports, key=lambda fr: fr["file"])
    cross_file_violations = 0
    prev_last = None
    for fr in ordered_files:
        if fr["ts_first_fresh"] is None:
            continue
        if prev_last is not None and fr["ts_first_fresh"] < prev_last:
            cross_file_violations += 1
        prev_last = fr["ts_last_fresh"]

    total_rows = sum(fr["n_rows"] for fr in file_reports)
    checks = [
        st.check("no_missing_expected_sessions",
                 st.PASS if not missing else st.FAIL,
                 f"{len(missing)} missing of {len(expected)} expected: {missing[:10]}"),
        st.check("pre_rth_short_sessions_without_data",
                 st.PASS if not missing_pre_rth_short else st.WARN,
                 f"{len(missing_pre_rth_short)} pre-RTH-close short sessions have "
                 f"no fresh events (init-only files): {missing_pre_rth_short}"),
        st.check("no_session_fails",
                 st.PASS if not any(r["qa_status"] == st.FAIL for r in session_rows)
                 else st.FAIL,
                 f"{sum(1 for r in session_rows if r['qa_status'] == st.FAIL)} FAIL sessions"),
        st.check("degraded_dates_assessed", st.PASS,
                 f"{len(DEGRADED_DATES)} vendor-degraded dates explicitly assessed"),
        st.check("cross_file_monotonic_order",
                 st.PASS if cross_file_violations == 0 else st.FAIL,
                 f"{cross_file_violations} cross-file fresh-timestamp order "
                 "violations (in addition to zero within-file disorder)"),
    ]
    return {
        "artifact": "mbp1_full_history_coverage",
        "scope_note": (
            "Full-history COVERAGE audit — not the complete canonical §12 "
            "session QA layer. The fields below remain a MANDATORY gate "
            "before any session becomes research-eligible in Milestone 2."
        ),
        "section12_fields_not_covered": [
            "sequence min/max per session", "duplicate detection",
            "non-negative quantity validation", "missing-value report",
            "spread/tick sanity distributions", "crossed/locked classification "
            "by session phase", "roll-proximity flags joined into QA rows",
            "per-session cross-source reconciliation (§13)",
        ],
        "n_files": len(file_reports),
        "total_rows": total_rows,
        "total_est_decoded_bytes": sum(fr["est_decoded_bytes"] for fr in file_reports),
        "n_expected_complete_sessions": len(expected),
        "n_observed_sessions": len(sessions),
        "n_weekend_preopen_remnant_dates": preopen_remnant_dates,
        "missing_sessions": missing,
        "missing_pre_rth_short_sessions": missing_pre_rth_short,
        "init_records_excluded_total":
            sum(fr.get("init_records_excluded", 0) for fr in file_reports),
        "n_pass": sum(1 for r in session_rows if r["qa_status"] == st.PASS),
        "n_warn": sum(1 for r in session_rows if r["qa_status"] == st.WARN),
        "n_fail": sum(1 for r in session_rows if r["qa_status"] == st.FAIL),
        "file_level": {
            "ts_non_monotonic_total": sum(fr["ts_non_monotonic"] for fr in file_reports),
            "crossed_f_last_outright_total":
                sum(fr["crossed_f_last_outright"] for fr in file_reports),
            "zero_size_trades_total": sum(fr["zero_size_trades"] for fr in file_reports),
            "unknown_flag_rows_total": sum(fr["unknown_flag_rows"] for fr in file_reports),
        },
        "sessions": session_rows,
        "out_of_range_sessions": out_of_range_rows,
        "cross_file_order_violations": cross_file_violations,
        "front_volumes": front_volumes,
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }


def run_coverage(data_root: Path, chunk_rows: int = dbnio.DEFAULT_CHUNK_ROWS,
                 workers: int = 3, cache_dir: Path | None = None) -> dict:
    from nqresearch.qa.cache import run_cached
    from nqresearch.sources import require_provenance, research_input_entries

    _disk_guard(data_root)
    require_provenance(data_root)  # refuse without valid provenance evidence
    entries = research_input_entries(data_root=data_root)
    files = [p for _, (p, _) in sorted(entries.items())]
    reports = run_cached(
        files, audit_file, (chunk_rows,), workers, cache_dir,
        params={"chunk_rows": chunk_rows, "op": "full_history_coverage_v1"},
    )
    return aggregate(reports)
