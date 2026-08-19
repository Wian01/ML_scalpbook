from collections import namedtuple
from pathlib import Path

from nqresearch.config import StorageGateConfig
from nqresearch.qa.status import FAIL, PASS, WARN
from nqresearch.qa.storage import GB, _existing_anchor, storage_gate

Usage = namedtuple("Usage", "total used free")
CFG = StorageGateConfig(required_free_gb=1000, preferred_free_gb=2000)


def _gate(free_gb: float) -> dict:
    return storage_gate(
        Path.cwd(), CFG,
        disk_usage=lambda p: Usage(total=4000 * GB, used=0, free=free_gb * GB),
    )


class TestStorageGate:
    def test_fail_below_required(self):
        r = _gate(272)
        assert r["status"] == FAIL
        assert r["free_gb"] == 272.0

    def test_warn_between_required_and_preferred(self):
        assert _gate(1500)["status"] == WARN

    def test_pass_at_preferred(self):
        assert _gate(2000)["status"] == PASS

    def test_boundary_exactly_required_is_warn(self):
        assert _gate(1000)["status"] == WARN

    def test_anchor_falls_back_to_existing_parent(self, tmp_path):
        missing = tmp_path / "not" / "yet" / "created"
        assert _existing_anchor(missing) == tmp_path

    def test_artifact_records_configuration(self):
        r = _gate(500)
        assert r["required_free_gb"] == 1000
        assert r["preferred_free_gb"] == 2000
        assert r["measured_data_root"] == str(Path.cwd())
