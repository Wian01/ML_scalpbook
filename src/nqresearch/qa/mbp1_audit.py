"""Milestone 0 audit of the purchased MBP-1 sample (read-only).

Covers, per canonical spec sections 2.2, 12 and Milestone 0: schema/metadata,
symbols and instrument mappings, outright/spread composition, timestamps and
monotonicity, sequence behaviour, action/depth/side values, flags (F_LAST),
book sanity (crossed/locked/spread), daily and session coverage, record counts,
and storage estimates.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import polars as pl

from nqresearch import dbnio, symbols
from nqresearch.flags import FLAG_BITS, UNDEF_PRICE, flag_counts
from nqresearch.qa import status as st
from nqresearch.sessions import session_exprs

TICK_INT = 250_000_000  # NQ 0.25 tick in Databento 1e-9 price scale
PX_SCALE = 1e-9
MAX_SPREAD_TICK_BIN = 400


def _counts_from_unique(values: np.ndarray) -> dict[str, int]:
    uniq, counts = np.unique(values, return_counts=True)
    out = {}
    for u, c in zip(uniq, counts):
        key = u.decode() if isinstance(u, bytes) else str(u)
        out[key] = int(c)
    return out


def _merge_counts(target: dict, extra: dict) -> None:
    for k, v in extra.items():
        target[k] = target.get(k, 0) + v


def _percentile_from_hist(hist: np.ndarray, q: float) -> int | None:
    total = hist.sum()
    if total == 0:
        return None
    cdf = np.cumsum(hist)
    return int(np.searchsorted(cdf, q * total, side="left"))


def audit_file(path: Path, chunk_rows: int = dbnio.DEFAULT_CHUNK_ROWS) -> dict:
    """Audit one daily MBP-1 DBN file; returns a JSON-serializable report."""
    meta = dbnio.read_metadata(path)
    iid_map = symbols.instrument_map_from_mappings(meta.mappings)
    iid_class = {iid: symbols.classify_symbol(sym) for iid, sym in iid_map.items()}
    outright_ids = np.array(
        sorted(i for i, c in iid_class.items() if c == symbols.OUTRIGHT), dtype=np.uint32
    )

    n_rows = 0
    sum_length_units = 0
    rtype_counts: dict[str, int] = {}
    publisher_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    side_counts: dict[str, int] = {}
    trade_side_counts: dict[str, int] = {}
    depth_counts: dict[str, int] = {}
    flags_total: dict[str, int] = {k: 0 for k in [*FLAG_BITS, "UNKNOWN_BITS"]}

    first_ts = None
    last_ts = None
    prev_ts = None
    nonmono_count = 0
    max_backward_ns = 0
    recv_before_event = 0
    ts_in_delta_negative = 0

    seq_min = None
    seq_max = None
    seq_backward = 0
    prev_seq = None

    inst_rows: dict[int, int] = defaultdict(int)
    inst_trades: dict[int, int] = defaultdict(int)
    inst_volume: dict[int, int] = defaultdict(int)
    unmapped_iids: set[int] = set()

    crossed_rows = 0
    locked_rows = 0
    crossed_rows_f_last = 0
    locked_rows_f_last = 0
    backward_examples: list[dict] = []
    spread_hist: dict[int, np.ndarray] = defaultdict(
        lambda: np.zeros(MAX_SPREAD_TICK_BIN + 2, dtype=np.int64)
    )
    spread_non_tick_aligned = 0
    mid_min: dict[int, float] = {}
    mid_max: dict[int, float] = {}

    session_rows: dict[str, int] = defaultdict(int)
    session_rth_rows: dict[str, int] = defaultdict(int)
    session_first: dict[str, int] = {}
    session_last: dict[str, int] = {}

    # (iid, session) -> last RTH ts seen, and max intra-RTH gap
    rth_last_ts: dict[tuple[int, str], int] = {}
    rth_max_gap: dict[tuple[int, str], int] = defaultdict(int)

    for chunk in dbnio.iter_ndarray_chunks(path, chunk_rows):
        n = len(chunk)
        n_rows += n
        sum_length_units += int(chunk["length"].astype(np.int64).sum())

        _merge_counts(rtype_counts, _counts_from_unique(chunk["rtype"]))
        _merge_counts(publisher_counts, _counts_from_unique(chunk["publisher_id"]))
        _merge_counts(action_counts, _counts_from_unique(chunk["action"]))
        _merge_counts(side_counts, _counts_from_unique(chunk["side"]))
        _merge_counts(depth_counts, _counts_from_unique(chunk["depth"]))
        _merge_counts(flags_total, flag_counts(chunk["flags"]))

        ts = chunk["ts_event"].astype(np.int64)
        if first_ts is None:
            first_ts = int(ts[0])
        last_ts = int(ts[-1])
        full_prev = np.empty_like(ts)
        full_prev[0] = prev_ts if prev_ts is not None else ts[0]
        full_prev[1:] = ts[:-1]
        back = full_prev - ts
        back_idx = np.nonzero(back > 0)[0]
        nonmono_count += int(len(back_idx))
        for bi in back_idx[: max(0, 10 - len(backward_examples))]:
            backward_examples.append(
                {
                    "row_index_in_file": n_rows - n + int(bi),
                    "prev_ts_event": int(full_prev[bi]),
                    "ts_event": int(ts[bi]),
                    "backward_ns": int(back[bi]),
                }
            )
        if len(back):
            max_backward_ns = max(max_backward_ns, int(back.max()))
        prev_ts = int(ts[-1])

        recv_before_event += int((chunk["ts_recv"].astype(np.int64) < ts).sum())
        ts_in_delta_negative += int((chunk["ts_in_delta"] < 0).sum())

        seq = chunk["sequence"].astype(np.int64)
        seq_min = int(seq.min()) if seq_min is None else min(seq_min, int(seq.min()))
        seq_max = int(seq.max()) if seq_max is None else max(seq_max, int(seq.max()))
        sprev = np.empty_like(seq)
        sprev[0] = prev_seq if prev_seq is not None else seq[0]
        sprev[1:] = seq[:-1]
        seq_backward += int((seq < sprev).sum())
        prev_seq = int(seq[-1])

        iids = chunk["instrument_id"]
        uniq_iid, iid_counts = np.unique(iids, return_counts=True)
        for i, c in zip(uniq_iid, iid_counts):
            inst_rows[int(i)] += int(c)
            if int(i) not in iid_map:
                unmapped_iids.add(int(i))

        is_trade = chunk["action"] == b"T"
        if is_trade.any():
            t_iid = iids[is_trade]
            t_size = chunk["size"][is_trade].astype(np.int64)
            _merge_counts(trade_side_counts, _counts_from_unique(chunk["side"][is_trade]))
            uniq_t, idx = np.unique(t_iid, return_inverse=True)
            vol = np.bincount(idx, weights=t_size).astype(np.int64)
            cnt = np.bincount(idx)
            for i, v, c in zip(uniq_t, vol, cnt):
                inst_trades[int(i)] += int(c)
                inst_volume[int(i)] += int(v)

        # Book sanity on outright instruments with both sides defined.
        bid = chunk["bid_px_00"]
        ask = chunk["ask_px_00"]
        defined = (bid != UNDEF_PRICE) & (ask != UNDEF_PRICE)
        outright_mask = np.isin(iids, outright_ids)
        ok = defined & outright_mask
        if ok.any():
            b = bid[ok]
            a = ask[ok]
            crossed_rows += int((a < b).sum())
            locked_rows += int((a == b).sum())
            # Only F_LAST-complete states are valid observations (spec section 16);
            # transiently crossed partial-packet states are expected mechanics.
            f_last_ok = (chunk["flags"][ok] & FLAG_BITS["F_LAST"]) != 0
            crossed_rows_f_last += int(((a < b) & f_last_ok).sum())
            locked_rows_f_last += int(((a == b) & f_last_ok).sum())
            spread = a - b
            ticks = spread // TICK_INT
            spread_non_tick_aligned += int((spread % TICK_INT != 0).sum())
            ok_iids = iids[ok]
            mids = (b.astype(np.float64) + a.astype(np.float64)) * 0.5 * PX_SCALE
            for i in np.unique(ok_iids):
                m = ok_iids == i
                key = int(i)
                clipped = np.clip(ticks[m], 0, MAX_SPREAD_TICK_BIN + 1).astype(np.int64)
                spread_hist[key] += np.bincount(clipped, minlength=MAX_SPREAD_TICK_BIN + 2)
                lo, hi = float(mids[m].min()), float(mids[m].max())
                mid_min[key] = min(mid_min.get(key, lo), lo)
                mid_max[key] = max(mid_max.get(key, hi), hi)

        # Session / RTH coverage.
        sess_df = pl.DataFrame({"ts_event": ts}).with_columns(session_exprs("ts_event"))
        sess = sess_df["session_id"].cast(pl.Utf8).to_numpy()
        rth = sess_df["rth_flag"].to_numpy()
        for s in np.unique(sess):
            m = sess == s
            key = str(s)
            session_rows[key] += int(m.sum())
            session_rth_rows[key] += int((m & rth).sum())
            s_ts = ts[m]
            session_first.setdefault(key, int(s_ts[0]))
            session_last[key] = int(s_ts[-1])

        # Max intra-RTH quote gap per (outright instrument, session).
        rth_out = rth & outright_mask
        if rth_out.any():
            r_iids = iids[rth_out]
            r_sess = sess[rth_out]
            r_ts = ts[rth_out]
            for i in np.unique(r_iids):
                mi = r_iids == i
                for s in np.unique(r_sess[mi]):
                    m2 = mi & (r_sess == s)
                    t2 = r_ts[m2]
                    key2 = (int(i), str(s))
                    gaps = np.diff(t2)
                    gap = int(gaps.max()) if len(gaps) else 0
                    if key2 in rth_last_ts:
                        gap = max(gap, int(t2[0]) - rth_last_ts[key2])
                    rth_max_gap[key2] = max(rth_max_gap[key2], gap)
                    rth_last_ts[key2] = int(t2[-1])

    # --- assemble ---
    instruments = []
    for iid in sorted(inst_rows):
        sym = iid_map.get(iid, "<unmapped>")
        instruments.append(
            {
                "instrument_id": iid,
                "symbol": sym,
                "class": iid_class.get(iid, "unmapped"),
                "rows": inst_rows[iid],
                "trades": inst_trades.get(iid, 0),
                "volume": inst_volume.get(iid, 0),
            }
        )
    outright_volume = {
        i["instrument_id"]: i["volume"] for i in instruments if i["class"] == symbols.OUTRIGHT
    }
    front_iid = max(outright_volume, key=outright_volume.get) if outright_volume else None

    front = None
    if front_iid is not None:
        hist = spread_hist.get(front_iid, np.zeros(1, dtype=np.int64))
        front = {
            "instrument_id": front_iid,
            "symbol": iid_map.get(front_iid),
            "mid_min": mid_min.get(front_iid),
            "mid_max": mid_max.get(front_iid),
            "spread_ticks_p50": _percentile_from_hist(hist, 0.50),
            "spread_ticks_p99": _percentile_from_hist(hist, 0.99),
            "spread_ticks_max_observed_bin": int(np.nonzero(hist)[0].max()) if hist.sum() else None,
            "rth_max_quote_gap_ms_by_session": {
                s: gap / 1e6
                for (i, s), gap in sorted(rth_max_gap.items())
                if i == front_iid
            },
        }

    f_last = flags_total.get("F_LAST", 0)
    n_trades = sum(inst_trades.values())

    checks = [
        st.check("schema_is_mbp1", st.PASS if str(meta.schema) == "mbp-1" else st.FAIL,
                 f"schema={meta.schema}"),
        st.check("stype_out_is_instrument_id",
                 st.PASS if str(meta.stype_out) == "instrument_id" else st.FAIL,
                 f"stype_in={meta.stype_in}, stype_out={meta.stype_out}"),
        st.check("all_instruments_mapped",
                 st.PASS if not unmapped_iids else st.FAIL,
                 f"unmapped instrument_ids: {sorted(unmapped_iids)[:10]}"),
        st.check("ts_event_monotonic_nondecreasing",
                 st.PASS if nonmono_count == 0 else st.WARN,
                 f"{nonmono_count} backward steps, max {max_backward_ns} ns"),
        st.check("ts_recv_not_before_ts_event",
                 st.PASS if recv_before_event == 0 else st.WARN,
                 f"{recv_before_event} rows with ts_recv < ts_event"),
        st.check("sequence_no_backward_moves",
                 st.PASS if seq_backward == 0 else st.WARN,
                 f"{seq_backward} backward sequence moves (channel-level semantics)"),
        st.check("actions_expected",
                 st.PASS if set(action_counts) <= {"A", "C", "M", "R", "T", "F"} else st.WARN,
                 f"observed actions: {sorted(action_counts)}"),
        st.check("depth_all_zero",
                 st.PASS if set(depth_counts) <= {"0"} else st.WARN,
                 f"observed depth values: {sorted(depth_counts)}"),
        st.check("sides_expected",
                 st.PASS if set(side_counts) <= {"A", "B", "N"} else st.FAIL,
                 f"observed sides: {sorted(side_counts)}"),
        st.check("no_crossed_book_outrights_f_last",
                 st.PASS if crossed_rows_f_last == 0 else st.WARN,
                 f"{crossed_rows_f_last} crossed / {locked_rows_f_last} locked on "
                 f"F_LAST-complete states ({crossed_rows} / {locked_rows} incl. "
                 f"partial-packet states, which are not valid observations)"),
        st.check("spreads_tick_aligned",
                 st.PASS if spread_non_tick_aligned == 0 else st.FAIL,
                 f"{spread_non_tick_aligned} outright spreads not multiple of 0.25"),
        st.check("f_last_present",
                 st.PASS if 0 < f_last <= n_rows else st.FAIL,
                 f"F_LAST on {f_last}/{n_rows} rows"),
    ]

    return {
        "file": path.name,
        "size_zst_bytes": path.stat().st_size,
        "est_uncompressed_bytes": sum_length_units * 4,
        "metadata": {
            "dataset": str(meta.dataset),
            "schema": str(meta.schema),
            "stype_in": str(meta.stype_in),
            "stype_out": str(meta.stype_out),
            "symbols": list(meta.symbols),
            "start": int(meta.start),
            "end": int(meta.end),
            "n_symbol_mappings": len(meta.mappings),
        },
        "n_rows": n_rows,
        "n_trades": n_trades,
        "total_traded_volume": sum(inst_volume.values()),
        "rtype_counts": rtype_counts,
        "publisher_counts": publisher_counts,
        "action_counts": action_counts,
        "side_counts": side_counts,
        "trade_side_counts": trade_side_counts,
        "depth_counts": depth_counts,
        "flag_counts": flags_total,
        "f_last_fraction": (f_last / n_rows) if n_rows else None,
        "mean_records_per_packet": (n_rows / f_last) if f_last else None,
        "ts": {
            "first_event": first_ts,
            "last_event": last_ts,
            "non_monotonic_count": nonmono_count,
            "max_backward_ns": max_backward_ns,
            "backward_examples": backward_examples,
            "ts_recv_before_ts_event": recv_before_event,
            "ts_in_delta_negative": ts_in_delta_negative,
        },
        "sequence": {"min": seq_min, "max": seq_max, "backward_moves": seq_backward},
        "instruments": instruments,
        "n_outrights": sum(1 for i in instruments if i["class"] == symbols.OUTRIGHT),
        "n_calendar_spreads": sum(1 for i in instruments if i["class"] == symbols.CALENDAR_SPREAD),
        "n_other_symbols": sum(1 for i in instruments if i["class"] == symbols.OTHER),
        "outright_book": {
            "crossed_rows": crossed_rows,
            "locked_rows": locked_rows,
            "crossed_rows_f_last": crossed_rows_f_last,
            "locked_rows_f_last": locked_rows_f_last,
        },
        "front_outright": front,
        "sessions": [
            {
                "session_id": s,
                "rows": session_rows[s],
                "rth_rows": session_rth_rows[s],
                "first_ts_event": session_first[s],
                "last_ts_event": session_last[s],
            }
            for s in sorted(session_rows)
        ],
        "checks": checks,
        "status": st.worst(c["status"] for c in checks),
    }


def audit_directory(
    mbp1_dir: Path,
    chunk_rows: int = dbnio.DEFAULT_CHUNK_ROWS,
    workers: int = 2,
    cache_dir: Path | None = None,
) -> dict:
    """Audit every daily MBP-1 file found under mbp1_dir (recursive)."""
    from nqresearch.qa.cache import run_cached

    files = sorted(mbp1_dir.rglob("*.mbp-1.dbn.zst"))
    reports = run_cached(
        files, audit_file, (chunk_rows,), workers, cache_dir,
        params={"chunk_rows": chunk_rows, "op": "mbp1_audit"},
    )

    weekday_reports = [
        r for r in reports if len(r["file"]) >= 4 and _is_weekday_file(r["file"])
    ]
    mean_zst = (
        sum(r["size_zst_bytes"] for r in weekday_reports) / len(weekday_reports)
        if weekday_reports
        else None
    )
    mean_raw = (
        sum(r["est_uncompressed_bytes"] for r in weekday_reports) / len(weekday_reports)
        if weekday_reports
        else None
    )
    trading_days_two_years = 2 * 252
    storage = {
        "n_files": len(reports),
        "sample_compressed_bytes": sum(r["size_zst_bytes"] for r in reports),
        "sample_est_uncompressed_bytes": sum(r["est_uncompressed_bytes"] for r in reports),
        "mean_weekday_compressed_bytes": mean_zst,
        "mean_weekday_est_uncompressed_bytes": mean_raw,
        "two_year_est_compressed_bytes": mean_zst * trading_days_two_years if mean_zst else None,
        "two_year_est_uncompressed_bytes": mean_raw * trading_days_two_years if mean_raw else None,
        "note": (
            "Extrapolation from an August sample; activity (and file size) varies "
            "seasonally and with volatility regime, so treat as a lower-bound-ish "
            "estimate with wide uncertainty."
        ),
    }
    return {
        "artifact": "mbp1_sample_audit",
        "source_dir": str(mbp1_dir),
        "files": reports,
        "storage": storage,
        "status": st.worst(r["status"] for r in reports) if reports else st.FAIL,
    }


def _is_weekday_file(filename: str) -> bool:
    from nqresearch.filenames import file_utc_date

    try:
        return file_utc_date(filename).weekday() < 5
    except ValueError:
        return False
