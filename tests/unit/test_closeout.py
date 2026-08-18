import json
from datetime import date

from nqresearch.qa.closeout import freeze_mbo_blocks, propose_partitions
from nqresearch.qa.status import PASS


def _deep_artifact(tmp_path, full, partial):
    p = tmp_path / "mbo_deep_audit.json"
    p.write_text(json.dumps({
        "full_rth_sessions": full,
        "partial_rth_sessions": partial,
    }))
    return p


class TestFreezeBlocks:
    def test_shortened_session_reclassified_complete(self, tmp_path):
        # 2026-07-03 half-day: observed span 0.5385 * 6.5h = 3.5h == expected.
        p = _deep_artifact(
            tmp_path,
            ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-06"],
            [{"session_id": "2026-07-03", "nq_outright_rth_rows": 1_015_860,
              "rth_span_coverage": 0.5385}],
        )
        r = freeze_mbo_blocks(p)
        rec = r["reclassifications"][0]
        assert rec["classification"] == "COMPLETE_SHORTENED_SESSION"
        # With 07-03 complete, 06-29..07-06 is ONE block (07-04 Sat, 07-05 Sun).
        assert r["n_blocks"] == 1
        assert r["blocks"][0]["n_sessions"] == 6
        assert r["status"] == PASS

    def test_holiday_does_not_break_block(self, tmp_path):
        # 2025-12-25 is a full holiday: 12-24 and 12-26 are contiguous.
        p = _deep_artifact(tmp_path, ["2025-12-24", "2025-12-26"], [])
        r = freeze_mbo_blocks(p)
        assert r["n_blocks"] == 1

    def test_genuine_partial_stays_flagged(self, tmp_path):
        p = _deep_artifact(
            tmp_path, ["2025-10-10"],
            [{"session_id": "2025-10-09", "nq_outright_rth_rows": 7_784_649,
              "rth_span_coverage": 0.4513}],
        )
        r = freeze_mbo_blocks(p)
        assert r["reclassifications"][0]["classification"] == "PARTIAL_UNEXPLAINED"
        assert r["status"] == "WARN"

    def test_acquisition_reason_recorded_as_unknown(self, tmp_path):
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        assert "UNKNOWN_NOT_RECORDED" in freeze_mbo_blocks(p)["acquisition_reason"]


class TestPartitionGates:
    def test_spanning_block_fails_proposal(self, tmp_path):
        # Synthetic block spanning SELECTION/HOLDOUT (2026-03-31 + 2026-04-01).
        p = _deep_artifact(tmp_path, ["2026-03-31", "2026-04-01"], [])
        blocks = freeze_mbo_blocks(p)
        prop = propose_partitions(blocks)
        assert prop["status"] == "FAIL"
        gate = [c for c in prop["checks"]
                if c["check"] == "no_partition_spanning_mbo_blocks"][0]
        assert gate["status"] == "FAIL"
        assert prop["mbo_blocks_per_partition"]["SPANNING"]

    def test_partition_ranges_contiguous(self, tmp_path):
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        prop = propose_partitions(freeze_mbo_blocks(p))
        gate = [c for c in prop["checks"]
                if c["check"] == "partition_ranges_contiguous"][0]
        assert gate["status"] == "PASS"

    def test_real_corpus_counts_regression(self):
        # Real decoded MBO artifact + real effective calendar; skipped when
        # the data volume is unavailable.
        import pytest as _pytest
        from pathlib import Path

        from nqresearch import paths

        deep = paths.qa_m0() / "mbo_deep_audit.json"
        if not deep.is_file():
            _pytest.skip("mbo_deep_audit.json not available on this machine")
        blocks = freeze_mbo_blocks(deep)
        prop = propose_partitions(blocks)
        assert blocks["n_sessions_final"] == 77 and blocks["n_blocks"] == 30
        ms, mb = prop["mbo_sessions_per_partition"], prop["mbo_blocks_per_partition"]
        assert prop["proposal"]["DEV"]["trading_days"] == 318
        assert prop["proposal"]["SELECTION"]["trading_days"] == 100
        assert prop["proposal"]["HOLDOUT"]["trading_days"] == 98
        assert (ms["DEV"], len(mb["DEV"])) == (23, 8)
        assert (ms["SELECTION"], len(mb["SELECTION"])) == (23, 11)
        assert (ms["HOLDOUT"], len(mb["HOLDOUT"])) == (31, 11)
        assert mb["SPANNING"] == []
        assert prop["status"] == "PASS"

    def test_activation_ready_false_while_verification_pending(self, tmp_path):
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        blocks = freeze_mbo_blocks(p)
        assert blocks["state"] == "PROVISIONAL_DOCUMENT_VERIFICATION_PENDING"
        assert blocks["activation_ready"] is False
        prop = propose_partitions(blocks)
        assert prop["calendar_verification_state"] == \
            "PROVISIONAL_DOCUMENT_VERIFICATION_PENDING"
        assert prop["activation_ready"] is False
        assert len(prop["activation_ready_conditions"]) == 3

    def test_non_contiguous_configuration_fails_gate(self, tmp_path, monkeypatch):
        # Deliberately broken boundary: DEV ends 2025-11-06 (Thu), leaving
        # trading day 2025-11-07 unassigned before SELECTION starts 11-10.
        import nqresearch.qa.closeout as co

        monkeypatch.setattr(co, "PROPOSED_DEV_END", date(2025, 11, 6))
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        prop = propose_partitions(freeze_mbo_blocks(p))
        gate = [c for c in prop["checks"]
                if c["check"] == "partition_ranges_contiguous"][0]
        assert gate["status"] == "FAIL"
        assert prop["status"] == "FAIL"

    def test_blocks_bound_to_effective_calendar_identity(self, tmp_path):
        p = _deep_artifact(tmp_path, ["2026-08-04"], [])
        b = freeze_mbo_blocks(p)
        for key in ("baseline_file_sha256", "overrides_file_sha256",
                    "effective_calendar_sha256"):
            assert len(b["based_on"][key]) == 64


class TestPartitionProposal:
    def test_counts_and_state(self, tmp_path):
        p = _deep_artifact(
            tmp_path,
            ["2025-08-18", "2025-11-18", "2026-03-04", "2026-05-04", "2026-08-04"],
            [],
        )
        blocks = freeze_mbo_blocks(p)
        prop = propose_partitions(blocks)
        assert prop["state"] == "PROPOSED_NOT_ACTIVE"
        assert prop["boundaries_on_trading_days"] is True
        ms = prop["mbo_sessions_per_partition"]
        assert ms == {"DEV": 1, "SELECTION": 2, "HOLDOUT": 2}
        assert prop["proposal"]["HOLDOUT"]["tentative"] is True
