"""nqr command-line interface (Milestone 0 scope: data audit + storage gate)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nqresearch import paths
from nqresearch.qa import status as st
from nqresearch.qa.report import write_artifact

AUDIT_PARTS = ["storage", "manifests", "mbp1", "trades", "mbo", "mbo-deep",
               "reconcile", "mbp1-acquisition", "mbp1-overlap-records",
               "mbp1-coverage", "closeout-finalize",
               "finalize-activation-candidate", "all"]
# NOTE: "all" covers the Milestone 0 parts; "mbp1-acquisition" is explicit-only
# so acquisition artifacts under qa/mbp1_full_history/ are regenerated
# deliberately, never as a side effect.


def _run_storage_gate() -> str:
    from nqresearch.config import load_data_paths_config
    from nqresearch.qa.storage import storage_gate

    cfg = load_data_paths_config()
    result = storage_gate(paths.data_root(), cfg.storage_gate)
    p = write_artifact(result, paths.qa_m0(), "storage_gate", paths.ROOT)
    print(f"[m0] storage gate: {result['status']} "
          f"(free {result['free_gb']} GB / required {result['required_free_gb']} GB "
          f"/ preferred {result['preferred_free_gb']} GB) -> {p}", flush=True)
    return result["status"]


def _run_audit(part: str, chunk_rows: int) -> int:
    statuses = {}
    cache_root = paths.qa_m0() / "cache"

    if part in ("storage", "all"):
        statuses["storage"] = _run_storage_gate()

    if part in ("manifests", "all"):
        from nqresearch.qa.manifest import validate_raw_tree

        print("[m0] validating vendor manifests (sizes + sha256) ...", flush=True)
        result = validate_raw_tree(paths.raw())
        p = write_artifact(result, paths.qa_m0(), "manifest_validation", paths.ROOT)
        statuses["manifests"] = result["status"]
        print(f"[m0] manifests: {result['status']} -> {p}", flush=True)

    if part in ("mbp1", "all"):
        from nqresearch.qa.mbp1_audit import audit_directory
        from nqresearch.sources import m0_sample_dir

        # Registry-scoped: ONLY the MILESTONE0_QA_SAMPLE job. The raw/mbp1
        # tree also holds the canonical annual corpus, which this sample
        # audit must never decode.
        print("[m0] auditing MBP-1 sample (registry-scoped) ...", flush=True)
        result = audit_directory(
            m0_sample_dir(), chunk_rows, cache_dir=cache_root / "mbp1"
        )
        p = write_artifact(result, paths.qa_m0(), "mbp1_sample_audit", paths.ROOT)
        statuses["mbp1"] = result["status"]
        print(f"[m0] mbp1: {result['status']} -> {p}", flush=True)

    if part in ("trades", "all"):
        from nqresearch.qa.trades_audit import audit_directory as trades_audit

        print("[m0] auditing trades dataset ...", flush=True)
        result = trades_audit(paths.raw_trades(), cache_dir=cache_root / "trades")
        p = write_artifact(result, paths.qa_m0(), "trades_audit", paths.ROOT)
        statuses["trades"] = result["status"]
        print(f"[m0] trades: {result['status']} -> {p}", flush=True)

    if part in ("mbo", "all"):
        from nqresearch.qa.mbo_inventory import inventory

        print("[m0] building MBO inventory (provisional, filename-based) ...", flush=True)
        result = inventory(paths.raw_mbo())
        p = write_artifact(result, paths.qa_m0(), "mbo_inventory", paths.ROOT)
        statuses["mbo"] = result["status"]
        print(f"[m0] mbo: {result['status']} -> {p}", flush=True)

    if part in ("mbo-deep", "all"):
        from nqresearch.qa.mbo_audit import audit_directory as mbo_deep

        print("[m0] deep-auditing MBO files (decoded NQ coverage) ...", flush=True)
        result = mbo_deep(paths.raw_mbo(), chunk_rows, cache_dir=cache_root / "mbo_deep")
        p = write_artifact(result, paths.qa_m0(), "mbo_deep_audit", paths.ROOT)
        statuses["mbo-deep"] = result["status"]
        print(f"[m0] mbo-deep: {result['status']} -> {p}", flush=True)

    if part in ("reconcile", "all"):
        from nqresearch.qa.reconcile import reconcile_overlap
        from nqresearch.sources import m0_sample_dir

        print("[m0] reconciling MBP-1 sample trades vs standalone trades ...", flush=True)
        result = reconcile_overlap(
            m0_sample_dir(), paths.raw_trades(), chunk_rows,
            cache_dir=cache_root / "reconcile",
        )
        p = write_artifact(result, paths.qa_m0(), "mbp1_trades_reconciliation", paths.ROOT)
        statuses["reconcile"] = result["status"]
        print(f"[m0] reconcile: {result['status']} -> {p}", flush=True)

    if part == "mbp1-acquisition":
        from nqresearch.config import load_data_paths_config
        from nqresearch.qa.mbp1_acquisition import (
            acquisition_gate,
            run_acquisition_validation,
        )
        from nqresearch.qa.storage import storage_gate

        out_dir = paths.qa() / "mbp1_full_history"
        print("[acq] validating MBP-1 acquisition + provenance ...", flush=True)
        payloads = run_acquisition_validation(paths.data_root())
        payloads["storage_gate"] = storage_gate(
            paths.data_root(), load_data_paths_config().storage_gate
        )
        # generation cleanliness + restamp_note are stamped centrally by the
        # envelope layer (qa.report); payloads may not supply them.
        for name, payload in payloads.items():
            p = write_artifact(payload, out_dir, name, paths.ROOT)
            statuses[name] = payload["status"]
            print(f"[acq] {name}: {payload['status']} -> {p}", flush=True)
        gate = acquisition_gate(paths.data_root(), out_dir)
        p = write_artifact(gate, out_dir, gate["artifact"], paths.ROOT)
        statuses["acquisition-gate"] = gate["status"]
        print(f"[acq] gate: {gate['status']} -> {p}", flush=True)

    if part == "mbp1-overlap-records":
        from nqresearch.config import load_mbp1_sources
        from nqresearch.qa.mbp1_acquisition import (
            RECORD_LEVEL_ARTIFACT_NAME,
            acquisition_gate,
            record_level_overlap_comparison,
        )

        out_dir = paths.qa() / "mbp1_full_history"
        print("[acq] record-level overlap comparison (decodes both copies) ...",
              flush=True)
        payload = record_level_overlap_comparison(
            load_mbp1_sources(), paths.data_root(), chunk_rows
        )
        p = write_artifact(payload, out_dir, RECORD_LEVEL_ARTIFACT_NAME, paths.ROOT)
        statuses["mbp1-overlap-records"] = payload["status"]
        print(f"[acq] overlap-records: {payload['status']} -> {p}", flush=True)
        gate = acquisition_gate(paths.data_root(), out_dir)
        p = write_artifact(gate, out_dir, gate["artifact"], paths.ROOT)
        statuses["acquisition-gate"] = gate["status"]
        print(f"[acq] gate: {gate['status']} -> {p}", flush=True)

    if part == "mbp1-coverage":
        from nqresearch.qa.full_history_audit import run_coverage
        from nqresearch.rolls import compute_front_series

        out_dir = paths.qa() / "m0_closeout"
        print("[closeout] full-history coverage audit (625 canonical files) ...",
              flush=True)
        result = run_coverage(paths.data_root(), chunk_rows,
                              cache_dir=out_dir / "cache" / "coverage")
        front_vols = result.pop("front_volumes")
        p = write_artifact(result, out_dir, "mbp1_full_history_coverage", paths.ROOT)
        statuses["coverage"] = result["status"]
        print(f"[closeout] coverage: {result['status']} -> {p}", flush=True)
        front = compute_front_series(front_vols)
        front_payload = {
            "artifact": "mbp1_front_contract_series",
            "rule": "STRICTLY CAUSAL previous-session volume-leading outright, "
                    "session-boundary switches, monotone expiry, "
                    "tie-retains-incumbent (see nqresearch/rolls.py; "
                    "PROPOSED pending review)",
            "eligibility_note": (
                "Out-of-range sessions (e.g. the 2026-08-17 partial edge) are "
                "EXCLUDED from this series; downstream consumers must not "
                "extend it past the coverage evaluation range."
            ),
            "out_of_range_excluded": [
                r["session_id"] for r in result.get("out_of_range_sessions", [])
            ],
            **front,
            "n_switches": len(front["switches"]),
            "status": st.PASS,
        }
        p = write_artifact(front_payload, out_dir, "mbp1_front_contract_series",
                           paths.ROOT)
        statuses["front-series"] = front_payload["status"]
        print(f"[closeout] front-series: {len(front['switches'])} switches -> {p}",
              flush=True)

    if part == "closeout-finalize":
        from nqresearch.qa.closeout import freeze_mbo_blocks, propose_partitions

        out_dir = paths.qa() / "m0_closeout"
        blocks = freeze_mbo_blocks(paths.qa_m0() / "mbo_deep_audit.json")
        p = write_artifact(blocks, out_dir, "mbo_blocks_frozen", paths.ROOT)
        statuses["mbo-blocks"] = blocks["status"]
        print(f"[closeout] mbo-blocks: {blocks['status']} "
              f"({blocks['n_sessions_final']} sessions, {blocks['n_blocks']} blocks) "
              f"-> {p}", flush=True)
        # Bind the EXACT bytes of the MBO-block artifact just written, so the
        # proposal's structural binding cannot refer to a stale artifact.
        import hashlib as _hashlib

        blocks_sha = _hashlib.sha256(p.read_bytes()).hexdigest()
        prop = propose_partitions(blocks, mbo_blocks_artifact_sha256=blocks_sha)
        p = write_artifact(prop, out_dir, "partition_proposal", paths.ROOT)
        statuses["partition-proposal"] = prop["status"]
        print(f"[closeout] partition-proposal: {prop['status']} -> {p}", flush=True)

    if part == "finalize-activation-candidate":
        # FAIL-CLOSED: refuses unless the research-eligibility policy is
        # exactly APPROVED_FOR_ACTIVATION. Produces a structurally-ready
        # CANDIDATE only — it never activates anything, and activation still
        # requires a separate human-approval audit entry plus
        # config/data/partitions_active.yaml.
        from nqresearch.activation import (
            ActivationError,
            finalize_activation_candidate,
        )

        out_dir = paths.qa() / "m0_closeout"
        try:
            candidate = finalize_activation_candidate()
        except ActivationError as e:
            print(f"[activation] REFUSED: {e}", flush=True)
            return 1
        p = write_artifact(candidate, out_dir,
                           "partition_activation_candidate", paths.ROOT)
        statuses["activation-candidate"] = candidate["status"]
        print(f"[activation] candidate: {candidate['state']} "
              f"(structural_ready={candidate['structural_ready']}, "
              f"activation_ready={candidate['activation_ready']}) -> {p}",
              flush=True)

    overall = st.worst(statuses.values()) if statuses else st.FAIL
    print(f"[m0] overall: {overall} ({statuses})", flush=True)
    return 0 if overall != st.FAIL else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nqr", description="NQ research platform CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    data = sub.add_parser("data", help="data operations")
    data_sub = data.add_subparsers(dest="data_command", required=True)

    audit = data_sub.add_parser("audit", help="run Milestone 0 data audit (read-only)")
    audit.add_argument("--part", choices=AUDIT_PARTS, default="all")
    audit.add_argument("--chunk-rows", type=int, default=2_000_000)

    data_sub.add_parser(
        "storage-gate",
        help="check free space on the configured data volume (spec 2.2/59)",
    )

    exp = sub.add_parser("exp", help="experiment registry (canonical §37/§38)")
    exp_sub = exp.add_subparsers(dest="exp_command", required=True)
    reg = exp_sub.add_parser("register", help="register a pre-registration YAML")
    reg.add_argument("prereg_yaml", help="path to a §37 pre-registration YAML")
    show = exp_sub.add_parser("show", help="show a registered experiment")
    show.add_argument("experiment_id")
    exp_sub.add_parser("list", help="list all experiments (incl. failed)")
    trans = exp_sub.add_parser("transition", help="lifecycle transition")
    trans.add_argument("experiment_id")
    trans.add_argument("new_status")
    trans.add_argument("--note", default="")
    trans.add_argument(
        "--outputs", default=None, metavar="MANIFEST_YAML",
        help="OutputsManifest file — REQUIRED for terminal transitions "
             "(explicitly empty manifests allowed for synthetic runs)",
    )

    args = parser.parse_args(argv)
    if args.command == "data" and args.data_command == "audit":
        return _run_audit(args.part, args.chunk_rows)
    if args.command == "data" and args.data_command == "storage-gate":
        return 0 if _run_storage_gate() != st.FAIL else 1
    if args.command == "exp":
        return _run_exp(args)
    parser.error("unknown command")
    return 2


def _run_exp(args) -> int:
    import json

    import yaml

    from nqresearch.experiments.models import PreRegistration
    from nqresearch.experiments.registry import ExperimentRegistry, RegistryError

    try:
        with ExperimentRegistry() as reg:
            if args.exp_command == "register":
                prereg = PreRegistration(
                    **yaml.safe_load(Path(args.prereg_yaml).read_text(encoding="utf-8"))
                )
                exp_id = reg.register(prereg)
                print(f"registered {exp_id} (status PLANNED)")
            elif args.exp_command == "show":
                print(json.dumps(reg.show(args.experiment_id), indent=1))
            elif args.exp_command == "list":
                for row in reg.list():
                    print(f"{row['experiment_id']}  trial={row['trial_number']}  "
                          f"{row['status']}")
            elif args.exp_command == "transition":
                outputs = None
                if args.outputs is not None:
                    outputs = yaml.safe_load(
                        Path(args.outputs).read_text(encoding="utf-8")
                    )
                rec = reg.transition(args.experiment_id, args.new_status,
                                     args.note, outputs=outputs)
                print(f"{args.experiment_id}: {rec['from_status']} -> "
                      f"{rec['to_status']}")
        return 0
    except RegistryError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
