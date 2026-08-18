"""require_provenance(): research preparation must refuse stale, failed,
missing, or malformed acquisition-gate evidence."""

import hashlib
import json

import pytest

from nqresearch.config import (
    ROLE_FULL_HISTORY,
    Mbp1Source,
    Mbp1SourceRegistry,
    effective_config_hash,
)
from nqresearch.qa.mbp1_acquisition import (
    EXPECTED_GATE_CHECKS,
    acquisition_code_hash,
)
from nqresearch.sources import ProvenanceError, require_provenance

MANIFEST_CONTENT = json.dumps({"files": []})
MANIFEST_SHA = hashlib.sha256(MANIFEST_CONTENT.encode()).hexdigest()


def _registry():
    return Mbp1SourceRegistry(sources=[
        Mbp1Source(
            request_id="J1", path="raw/mbp1/a/J1", role=ROLE_FULL_HISTORY,
            research_eligible=True, dataset="GLBX.MDP3", schema="mbp-1",
            symbols=["NQ.FUT"], stype_in="parent", stype_out="instrument_id",
            start_ns=0, end_ns=10, manifest_sha256=MANIFEST_SHA,
        )
    ])


def _env(tmp_path, **gate_overrides):
    job = tmp_path / "raw/mbp1/a/J1"
    job.mkdir(parents=True)
    (job / "manifest.json").write_text(MANIFEST_CONTENT)
    gate = {
        "status": "PASS",
        "config_hash": effective_config_hash(),
        "acquisition_code_hash": acquisition_code_hash(),
        "current_manifest_sha256": {"J1": MANIFEST_SHA},
        "checks": [{"check": n, "status": "PASS"} for n in EXPECTED_GATE_CHECKS],
    }
    gate.update(gate_overrides)
    gate_dir = tmp_path / "qa" / "mbp1_full_history"
    gate_dir.mkdir(parents=True)
    (gate_dir / "mbp1_acquisition_gate.json").write_text(json.dumps(gate))
    return tmp_path


class TestRequireProvenance:
    def test_valid_current_gate_accepted(self, tmp_path):
        root = _env(tmp_path)
        gate = require_provenance(root, _registry())
        assert gate["status"] == "PASS"

    def test_missing_gate_rejected(self, tmp_path):
        with pytest.raises(ProvenanceError, match="missing"):
            require_provenance(tmp_path, _registry())

    def test_failed_gate_rejected(self, tmp_path):
        root = _env(tmp_path, status="FAIL")
        with pytest.raises(ProvenanceError, match="not PASS"):
            require_provenance(root, _registry())

    def test_stale_config_hash_rejected(self, tmp_path):
        root = _env(tmp_path, config_hash="0" * 64)
        with pytest.raises(ProvenanceError, match="different effective"):
            require_provenance(root, _registry())

    def test_stale_code_hash_rejected(self, tmp_path):
        # The blocking review finding: a gate produced by older
        # acquisition/provenance code must never authorize research prep.
        root = _env(tmp_path, acquisition_code_hash="deadbeef" * 8)
        with pytest.raises(ProvenanceError, match="different acquisition"):
            require_provenance(root, _registry())

    def test_changed_manifest_identity_rejected(self, tmp_path):
        root = _env(tmp_path)
        # Vendor manifest replaced after the gate was generated.
        (root / "raw/mbp1/a/J1/manifest.json").write_text(
            json.dumps({"files": [{"filename": "new"}]})
        )
        with pytest.raises(ProvenanceError, match="manifest identity"):
            require_provenance(root, _registry())

    def test_gate_manifest_map_mismatch_rejected(self, tmp_path):
        root = _env(tmp_path, current_manifest_sha256={"J1": "1" * 64})
        with pytest.raises(ProvenanceError, match="manifest identity"):
            require_provenance(root, _registry())

    def test_missing_checks_list_rejected(self, tmp_path):
        root = _env(tmp_path, checks=None)
        with pytest.raises(ProvenanceError, match="malformed"):
            require_provenance(root, _registry())

    def test_missing_named_check_rejected(self, tmp_path):
        checks = [{"check": n, "status": "PASS"}
                  for n in EXPECTED_GATE_CHECKS if n != "record_level_identity"]
        root = _env(tmp_path, checks=checks)
        with pytest.raises(ProvenanceError, match="record_level_identity"):
            require_provenance(root, _registry())

    def test_non_pass_named_check_rejected_despite_top_level_pass(self, tmp_path):
        checks = [{"check": n, "status": "PASS"} for n in EXPECTED_GATE_CHECKS]
        checks[5]["status"] = "WARN"
        root = _env(tmp_path, checks=checks)
        with pytest.raises(ProvenanceError, match="not PASS"):
            require_provenance(root, _registry())

    def test_expected_checks_constant_has_nine_names(self):
        assert len(EXPECTED_GATE_CHECKS) == 9
        assert len(set(EXPECTED_GATE_CHECKS)) == 9
