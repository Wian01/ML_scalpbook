"""Acquisition and source-provenance validation for the two-year MBP-1 corpus.

Read-only. Validates the vendor jobs (metadata, condition, manifest re-hash,
manifest.json identity vs the registry), the exact adjacency of the annual
query ranges, the identity of the Milestone 0 sample overlap, and the
registry-driven canonical source selection; assembles a cohesive acquisition
gate. Writes artifacts under <data_root>/qa/mbp1_full_history/ — the
historical <data_root>/qa/m0/ artifact set is never overwritten.

Cross-request identity semantics (observed 2026-08-18): each copy of a market
day independently matches its own vendor manifest, but cross-request file
hashes and sizes differ because every Databento batch file embeds per-request
container metadata. Decoded-record equality is therefore the authoritative
cross-request identity check; the file-level comparison is an explained WARN.

No decode of non-overlap days happens here.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from nqresearch import sources as src_mod
from nqresearch.config import (
    Mbp1Source,
    Mbp1SourceRegistry,
    effective_config_hash,
    load_mbp1_sources,
)
from nqresearch.qa import status as st
from nqresearch.qa.manifest import _check_entry, sha256_file

EXPECTED_CUSTOMIZATIONS = {
    "pretty_px": False,
    "pretty_ts": False,
    "map_symbols": False,
    "split_symbols": False,
    "split_duration": "day",
}
EXPECTED_QUERY = {
    "dataset": "GLBX.MDP3",
    "schema": "mbp-1",
    "stype_in": "parent",
    "stype_out": "instrument_id",
    "encoding": "dbn",
    "compression": "zstd",
}

GATE_ARTIFACT_NAME = "mbp1_acquisition_gate"
RECORD_LEVEL_ARTIFACT_NAME = "mbp1_sample_overlap_record_level"

# The nine named checks a valid acquisition gate must contain, all PASS.
# Consumers (require_provenance) verify these by name rather than trusting
# only the top-level status field.
EXPECTED_GATE_CHECKS = (
    "inventory_completed",
    "manifests_verified",
    "ranges_adjacent",
    "selection_valid",
    "overlap_file_level_explained",
    "record_level_identity",
    "record_evidence_bound_to_current_config",
    "record_evidence_bound_to_current_code",
    "record_evidence_bound_to_current_manifests",
)


def acquisition_code_hash() -> str:
    """SHA-256 over the modules that materially define acquisition/identity/
    gate semantics — source selection, DBN reading, filename parsing, config
    (registry models), manifest-verification, status semantics, and this
    module itself.

    Used to bind record-level identity evidence and the acquisition gate: a
    change to any of these modules invalidates previously generated evidence.
    """
    import nqresearch.config
    import nqresearch.dbnio
    import nqresearch.filenames
    import nqresearch.qa.manifest
    import nqresearch.qa.status
    import nqresearch.sources

    modules = [
        __file__,
        nqresearch.sources.__file__,
        nqresearch.dbnio.__file__,
        nqresearch.config.__file__,
        nqresearch.filenames.__file__,
        nqresearch.qa.manifest.__file__,
        nqresearch.qa.status.__file__,
    ]
    h = hashlib.sha256()
    for m in sorted(str(Path(p).resolve()) for p in modules):
        h.update(Path(m).name.encode())
        h.update(b"\0")
        h.update(Path(m).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def current_manifest_hashes(
    registry: Mbp1SourceRegistry, data_root: Path
) -> dict[str, str]:
    """request_id -> SHA-256 of the job's manifest.json as found on disk."""
    return {
        s.request_id: sha256_file(src_mod.source_dir(s, data_root) / s.manifest)
        for s in registry.sources
    }


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_dbn_entries(source: Mbp1Source, data_root: Path) -> dict[str, dict]:
    m = _read_json(src_mod.source_dir(source, data_root) / source.manifest)
    return {e["filename"]: e for e in m.get("files", [])
            if e["filename"].endswith(".dbn.zst")}


def validate_source_metadata(source: Mbp1Source, data_root: Path) -> dict:
    """Verify a job's vendor metadata against the registry entry and the
    frozen-specification acquisition expectations.

    Status: FAIL on any metadata/identity problem; WARN when the vendor flags
    degraded condition entries (understood, non-blocking, pending Milestone 2
    session QA); PASS otherwise.
    """
    job_dir = src_mod.source_dir(source, data_root)
    meta = _read_json(job_dir / "metadata.json")
    query = meta.get("query", {})
    cust = meta.get("customizations", {})
    problems = []

    if meta.get("job_id") != source.request_id:
        problems.append(f"job_id {meta.get('job_id')!r} != registry {source.request_id!r}")
    if job_dir.name != source.request_id:
        problems.append(f"directory {job_dir.name!r} != request id {source.request_id!r}")
    for key, expected in EXPECTED_QUERY.items():
        if query.get(key) != expected:
            problems.append(f"query.{key}={query.get(key)!r}, expected {expected!r}")
    if query.get("symbols") != source.symbols:
        problems.append(f"symbols {query.get('symbols')!r} != {source.symbols!r}")
    if query.get("start") != source.start_ns:
        problems.append(f"start {query.get('start')} != registry {source.start_ns}")
    if query.get("end") != source.end_ns:
        problems.append(f"end {query.get('end')} != registry {source.end_ns}")
    for key, expected in EXPECTED_CUSTOMIZATIONS.items():
        if cust.get(key) != expected:
            problems.append(f"customizations.{key}={cust.get(key)!r}, expected {expected!r}")

    manifest_hash_actual = sha256_file(job_dir / source.manifest)
    if manifest_hash_actual != source.manifest_sha256:
        problems.append(
            f"manifest.json sha256 {manifest_hash_actual} != registry "
            f"{source.manifest_sha256}"
        )

    condition = _read_json(job_dir / "condition.json")
    cond_counts = Counter(e.get("condition") for e in condition)
    non_available = [
        {"date": e["date"], "condition": e["condition"],
         "file_present": any(job_dir.glob(f"*{e['date'].replace('-', '')}*.zst"))}
        for e in condition if e.get("condition") != "available"
    ]

    zst = sorted(job_dir.glob("*.dbn.zst"))
    json_files = sorted(job_dir.glob("*.json"))
    if problems:
        status = st.FAIL
    elif non_available:
        status = st.WARN  # vendor-degraded days: understood, pending session QA
    else:
        status = st.PASS
    return {
        "request_id": source.request_id,
        "role": source.role,
        "research_eligible": source.research_eligible,
        "path": source.path,
        "query_start_ns": query.get("start"),
        "query_end_ns": query.get("end"),
        "n_dbn_files": len(zst),
        "n_json_files": len(json_files),
        "bytes_on_disk": sum(f.stat().st_size for f in [*zst, *json_files]),
        "first_dbn": zst[0].name if zst else None,
        "last_dbn": zst[-1].name if zst else None,
        "manifest_sha256": manifest_hash_actual,
        "manifest_sha256_matches_registry": manifest_hash_actual == source.manifest_sha256,
        "condition_counts": dict(cond_counts),
        "condition_non_available": non_available,
        "metadata_problems": problems,
        "status": status,
    }


def validate_source_manifest(
    source: Mbp1Source, data_root: Path, workers: int = 4
) -> dict:
    """Re-hash every manifest-listed file of one job; detect unmanifested or
    partial-download stragglers."""
    job_dir = src_mod.source_dir(source, data_root)
    manifest = _read_json(job_dir / source.manifest)
    entries = manifest.get("files", [])
    listed = {e["filename"] for e in entries}
    tasks = [(str(job_dir), e["filename"], e["size"], e.get("hash", "")) for e in entries]

    if workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_check_entry, *zip(*tasks), chunksize=8))
    else:
        results = [_check_entry(*t) for t in tasks]

    failures = [r for r in results if r["status"] != st.PASS]
    unmanifested = [
        f.name for f in job_dir.iterdir()
        if f.is_file() and f.name not in listed and f.name != source.manifest
    ]
    zero_size = [f.name for f in job_dir.glob("*.dbn.zst") if f.stat().st_size == 0]
    return {
        "request_id": source.request_id,
        "n_manifested_files": len(entries),
        "n_checked": len(results),
        "failures": failures,
        "unmanifested_files": unmanifested,
        "zero_size_dbn_files": zero_size,
        "status": st.PASS if not (failures or unmanifested or zero_size) else st.FAIL,
    }


def sample_overlap_comparison(
    registry: Mbp1SourceRegistry, data_root: Path
) -> dict:
    """FILE-LEVEL comparison of every sample DBN file against the same-named
    file in the canonical corpus (vendor-manifest size and SHA-256).

    Cross-request file hashes are expected to differ (per-request container
    metadata), so mismatches produce an explained WARN; the authoritative
    identity check is record_level_overlap_comparison. A sample file missing
    from the canonical corpus is a structural FAIL.
    """
    sample = src_mod.qa_sample_source(registry)
    canonical = registry.research_sources()

    sample_files = _manifest_dbn_entries(sample, data_root)
    canonical_files: dict[str, tuple[str, dict]] = {}
    for src in canonical:
        for name, entry in _manifest_dbn_entries(src, data_root).items():
            canonical_files[name] = (src.request_id, entry)

    rows = []
    all_match = True
    for name in sorted(sample_files):
        s = sample_files[name]
        c = canonical_files.get(name)
        if c is None:
            rows.append({"filename": name, "match": False,
                         "issue": "missing_in_canonical_corpus"})
            all_match = False
            continue
        c_req, c_entry = c
        size_match = s["size"] == c_entry["size"]
        hash_match = s.get("hash") == c_entry.get("hash")
        rows.append({
            "filename": name,
            "canonical_request_id": c_req,
            "sample_size": s["size"], "canonical_size": c_entry["size"],
            "sample_sha256": s.get("hash"), "canonical_sha256": c_entry.get("hash"),
            "match": size_match and hash_match,
        })
        all_match = all_match and size_match and hash_match

    missing = [r for r in rows if r.get("issue") == "missing_in_canonical_corpus"]
    if missing:
        status = st.FAIL
        resolution = "DISCREPANCY - sample file absent from canonical corpus"
    elif all_match:
        status = st.PASS
        resolution = (
            "file-level vendor hashes identical; recent annual job is "
            "canonical for the overlapping dates"
        )
    else:
        status = st.WARN
        resolution = (
            "file hashes differ (expected: per-request DBN container "
            "metadata); record-level comparison is the authoritative "
            "identity check and must PASS before the annual job is "
            "designated canonical for the overlapping dates"
        )
    return {
        "sample_request_id": sample.request_id,
        "n_overlapping_files": len(sample_files),
        "files": rows,
        "all_match": all_match,
        "file_hash_identity": all_match,
        "resolution": resolution,
        "status": status,
    }


def _compare_pair_dbn(sample_path: Path, canonical_path: Path, chunk_rows: int) -> dict:
    """Decode both copies chunk-by-chunk and byte-compare the record streams."""
    import numpy as np
    from databento import DBNStore

    it_s = DBNStore.from_file(str(sample_path)).to_ndarray(count=chunk_rows)
    it_c = DBNStore.from_file(str(canonical_path)).to_ndarray(count=chunk_rows)
    n_records = 0
    while True:
        cs = next(it_s, None)
        cc = next(it_c, None)
        if cs is None and cc is None:
            return {"identical": True, "n_records_compared": n_records}
        if cs is None or cc is None or len(cs) != len(cc):
            return {"identical": False, "n_records_compared": n_records,
                    "issue": "record_count_mismatch"}
        if cs.dtype != cc.dtype:
            return {"identical": False, "n_records_compared": n_records,
                    "issue": "dtype_schema_mismatch"}
        if not np.array_equal(cs.view(np.uint8), cc.view(np.uint8)):
            return {"identical": False, "n_records_compared": n_records,
                    "issue": "record_bytes_differ"}
        n_records += len(cs)


def record_level_overlap_comparison(
    registry: Mbp1SourceRegistry,
    data_root: Path,
    chunk_rows: int = 2_000_000,
    compare_pair=None,
) -> dict:
    """Authoritative cross-request identity check: byte-compare the DECODED
    RECORDS of every expected sample/canonical file pair.

    Fail-safe construction:
    - expected filenames come from the independently validated SAMPLE MANIFEST
      (never a disk glob);
    - zero expected pairs is FAIL;
    - every manifest-listed sample DBN must exist on disk;
    - every expected file must have exactly ONE canonical counterpart (by the
      canonical jobs' manifests) that exists on disk — missing or multiple
      counterparts FAIL;
    - the compared-pair count must equal the expected count;
    - record count, dtype/schema, and record bytes must match;
    - any incomplete comparison cannot PASS.

    The result embeds binding identities (current manifest hashes, effective
    config hash, acquisition code hash) so stale evidence cannot authorize a
    changed source set.
    """
    compare = compare_pair or _compare_pair_dbn
    sample = src_mod.qa_sample_source(registry)
    sample_dir = src_mod.source_dir(sample, data_root)
    expected = sorted(_manifest_dbn_entries(sample, data_root))

    canonical_lookup: dict[str, list[tuple[str, Path]]] = {}
    for src in registry.research_sources():
        d = src_mod.source_dir(src, data_root)
        for name in _manifest_dbn_entries(src, data_root):
            canonical_lookup.setdefault(name, []).append((src.request_id, d))

    rows = []
    problems = 0
    for name in expected:
        spath = sample_dir / name
        if not spath.is_file():
            rows.append({"filename": name, "identical": False,
                         "issue": "sample_file_missing_on_disk"})
            problems += 1
            continue
        matches = canonical_lookup.get(name, [])
        if len(matches) == 0:
            rows.append({"filename": name, "identical": False,
                         "issue": "missing_in_canonical_corpus"})
            problems += 1
            continue
        if len(matches) > 1:
            rows.append({"filename": name, "identical": False,
                         "issue": "multiple_canonical_counterparts",
                         "counterparts": [req for req, _ in matches]})
            problems += 1
            continue
        req, cdir = matches[0]
        cpath = cdir / name
        if not cpath.is_file():
            rows.append({"filename": name, "identical": False,
                         "issue": "canonical_file_missing_on_disk",
                         "canonical_request_id": req})
            problems += 1
            continue
        result = compare(spath, cpath, chunk_rows)
        rows.append({"filename": name, "canonical_request_id": req, **result})
        if not result.get("identical"):
            problems += 1

    n_compared = sum(1 for r in rows if "n_records_compared" in r)
    complete = (
        len(expected) > 0
        and len(rows) == len(expected)
        and n_compared == len(expected)
    )
    all_identical = complete and problems == 0 and all(r.get("identical") for r in rows)

    if not expected:
        interpretation = "FAIL - sample manifest lists no DBN files to compare"
    elif all_identical:
        interpretation = (
            "Decoded record streams are byte-identical for every expected "
            "overlapping day; the vendor file-hash differences are confined "
            "to per-request container metadata."
        )
    else:
        interpretation = (
            "Identity NOT established - incomplete comparison or genuine "
            "difference; do not designate a canonical source."
        )
    return {
        "artifact": RECORD_LEVEL_ARTIFACT_NAME,
        "n_expected_pairs": len(expected),
        "n_pairs_compared": n_compared,
        "total_records_compared": sum(r.get("n_records_compared", 0) for r in rows),
        "files": rows,
        "all_records_identical": bool(all_identical),
        "binding": {
            "config_hash": effective_config_hash(),
            "acquisition_code_hash": acquisition_code_hash(),
            "source_manifest_sha256": current_manifest_hashes(registry, data_root),
        },
        "interpretation": interpretation,
        "status": st.PASS if all_identical else st.FAIL,
    }


def source_selection_result(
    registry: Mbp1SourceRegistry, data_root: Path
) -> dict:
    """Materialize the canonical research input set via the selection layer,
    with ownership tracking and a resolved-path leak check for the QA sample."""
    entries = src_mod.research_input_entries(registry, data_root)
    keys = sorted(entries)
    sample = src_mod.qa_sample_source(registry)
    sample_dir = src_mod.source_dir(sample, data_root).resolve()

    eligible_ids = {s.request_id for s in registry.research_sources()}
    bad_owner = sorted(
        k for k, (_, owner) in entries.items() if owner not in eligible_ids
    )
    # Path-level leak check on resolved, normalized paths (Windows-safe).
    leaked_paths = sorted(
        k for k, (p, _) in entries.items()
        if p.resolve() == (sample_dir / p.name) or p.resolve().is_relative_to(sample_dir)
    )
    sample_dates = sorted(
        {file_key for file_key in (
            src_mod.file_date_key_safe(f.name)
            for f in src_mod.source_dir(sample, data_root).glob("*.dbn.zst")
        ) if file_key}
    )
    ok = not bad_owner and not leaked_paths
    return {
        "n_research_files": len(entries),
        "date_first": keys[0] if keys else None,
        "date_last": keys[-1] if keys else None,
        "owners": sorted({owner for _, owner in entries.values()}),
        "sample_dates_in_overlap": sample_dates,
        "partitions_owned_by_non_eligible_sources": bad_owner,
        "sample_files_leaked_into_research_input": leaked_paths,
        "unique_partitions": True,  # research_input_entries raises otherwise
        "status": st.PASS if ok else st.FAIL,
    }


def acquisition_gate(data_root: Path, artifacts_dir: Path) -> dict:
    """Cohesive machine-readable acquisition/provenance gate.

    PASSes only when, for the SAME source identities and current
    configuration/code, all of these hold: inventory completed (PASS/WARN),
    manifests verified, annual ranges adjacent, canonical partitions unique
    with the sample excluded, file-level overlap is the explained WARN (or
    PASS), and the record-level comparison PASSes for every expected pair
    with valid binding. Stale or mismatched evidence cannot authorize a
    changed source set.
    """
    registry = load_mbp1_sources()

    def load(name: str) -> dict | None:
        p = artifacts_dir / f"{name}.json"
        return _read_json(p) if p.is_file() else None

    inventory = load("mbp1_source_inventory")
    manifests = load("mbp1_manifest_validation")
    adjacency = load("mbp1_range_adjacency")
    overlap = load("mbp1_sample_overlap")
    selection = load("mbp1_source_selection")
    record = load(RECORD_LEVEL_ARTIFACT_NAME)

    cfg_hash = effective_config_hash()
    code_hash = acquisition_code_hash()
    manifest_now = current_manifest_hashes(registry, data_root)
    registry_ids = sorted(s.request_id for s in registry.sources)

    checks = []

    def check(name, ok, detail=""):
        checks.append(st.check(name, st.PASS if ok else st.FAIL, detail))
        return ok

    check("inventory_completed",
          inventory is not None
          and inventory.get("status") in (st.PASS, st.WARN)
          and sorted(s["request_id"] for s in inventory.get("sources", []))
          == registry_ids,
          "source inventory present, PASS/WARN, covering the registry sources")
    check("manifests_verified",
          manifests is not None and manifests.get("status") == st.PASS,
          "all vendor manifests re-hash verified")
    check("ranges_adjacent",
          adjacency is not None and adjacency.get("status") == st.PASS,
          "annual query ranges exactly adjacent")
    check("selection_valid",
          selection is not None and selection.get("status") == st.PASS,
          "canonical partitions unique; sample excluded from research input")
    check("overlap_file_level_explained",
          overlap is not None and (
              overlap.get("status") == st.PASS
              or (overlap.get("status") == st.WARN
                  and overlap.get("file_hash_identity") is False)
          ),
          "file-level overlap identical or the explained container-metadata WARN")

    record_ok = (
        record is not None
        and record.get("status") == st.PASS
        and record.get("n_expected_pairs", 0) > 0
        and record.get("n_pairs_compared") == record.get("n_expected_pairs")
        and (overlap is None or record.get("n_expected_pairs")
             == overlap.get("n_overlapping_files"))
    )
    check("record_level_identity",
          record_ok,
          "record-level comparison PASS for every expected pair")

    binding = (record or {}).get("binding", {})
    check("record_evidence_bound_to_current_config",
          binding.get("config_hash") == cfg_hash,
          "record-level evidence generated under the current effective config")
    check("record_evidence_bound_to_current_code",
          binding.get("acquisition_code_hash") == code_hash,
          "record-level evidence generated by the current acquisition code")
    check("record_evidence_bound_to_current_manifests",
          binding.get("source_manifest_sha256") == manifest_now,
          "record-level evidence bound to the current vendor manifest identities")

    ok = all(c["status"] == st.PASS for c in checks)
    return {
        "artifact": GATE_ARTIFACT_NAME,
        "registry_request_ids": registry_ids,
        "current_manifest_sha256": manifest_now,
        "acquisition_code_hash": code_hash,
        "checks": checks,
        "status": st.PASS if ok else st.FAIL,
        "note": (
            "Research preparation must refuse to proceed unless this gate is "
            "PASS and bound to the current configuration "
            "(nqresearch.sources.require_provenance)."
        ),
    }


def run_acquisition_validation(data_root: Path, workers: int = 4) -> dict[str, dict]:
    """All acquisition artifacts (except the record-level comparison and the
    gate, which the CLI assembles separately) as {artifact_name: payload}."""
    registry = load_mbp1_sources()

    inventory = [validate_source_metadata(s, data_root) for s in registry.sources]
    manifests = [validate_source_manifest(s, data_root, workers) for s in registry.sources]
    adjacency = src_mod.validate_adjacent_ranges(registry.research_sources())
    overlap = sample_overlap_comparison(registry, data_root)
    selection = source_selection_result(registry, data_root)

    return {
        "mbp1_source_inventory": {
            "artifact": "mbp1_source_inventory",
            "sources": inventory,
            "status": st.worst(s["status"] for s in inventory),
        },
        "mbp1_manifest_validation": {
            "artifact": "mbp1_manifest_validation",
            "jobs": manifests,
            "n_files_checked": sum(m["n_checked"] for m in manifests),
            "status": st.worst(m["status"] for m in manifests),
        },
        "mbp1_range_adjacency": {
            "artifact": "mbp1_range_adjacency",
            **adjacency,
            "status": st.PASS if adjacency["adjacent"] else st.FAIL,
        },
        "mbp1_sample_overlap": {
            "artifact": "mbp1_sample_overlap",
            **overlap,
        },
        "mbp1_source_selection": {
            "artifact": "mbp1_source_selection",
            **selection,
        },
    }
