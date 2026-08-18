"""Acquisition validation units: overlap comparisons, fail-safe record-level
identity gate, and Windows-safe sample-leak detection."""

import json

import pytest

from nqresearch.config import (
    ROLE_FULL_HISTORY,
    ROLE_M0_QA_SAMPLE,
    Mbp1Source,
    Mbp1SourceRegistry,
)
from nqresearch.qa.mbp1_acquisition import (
    record_level_overlap_comparison,
    sample_overlap_comparison,
    source_selection_result,
)
from nqresearch.qa.status import FAIL, PASS, WARN


def _src(request_id, role, path, start_ns=0, end_ns=10):
    return Mbp1Source(
        request_id=request_id, path=path, role=role,
        research_eligible=role == ROLE_FULL_HISTORY,
        dataset="GLBX.MDP3", schema="mbp-1", symbols=["NQ.FUT"],
        stype_in="parent", stype_out="instrument_id",
        start_ns=start_ns, end_ns=end_ns, manifest_sha256="0" * 64,
    )


def _job(data_root, rel, files: dict[str, tuple[int, str]], write_data=True):
    d = data_root / rel
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"files": [
        {"filename": name, "size": size, "hash": f"sha256:{h}"}
        for name, (size, h) in files.items()
    ]}
    (d / "manifest.json").write_text(json.dumps(manifest))
    if write_data:
        for name, (size, _) in files.items():
            (d / name).write_bytes(b"x" * size)
    return d


def _identical_pair(sample_path, canonical_path, chunk_rows):
    return {"identical": True, "n_records_compared": 100}


class TestSampleOverlapFileLevel:
    def _registry(self, tmp_path, sample_hash="aaa", canonical_hash="aaa",
                  sample_size=4, canonical_size=4):
        _job(tmp_path, "raw/mbp1/annual/J1",
             {"glbx-mdp3-20260803.mbp-1.dbn.zst": (canonical_size, canonical_hash)})
        _job(tmp_path, "raw/mbp1/sample/QA",
             {"glbx-mdp3-20260803.mbp-1.dbn.zst": (sample_size, sample_hash)})
        return Mbp1SourceRegistry(sources=[
            _src("J1", ROLE_FULL_HISTORY, "raw/mbp1/annual/J1"),
            _src("QA", ROLE_M0_QA_SAMPLE, "raw/mbp1/sample/QA"),
        ])

    def test_matching_hashes_pass(self, tmp_path):
        r = sample_overlap_comparison(self._registry(tmp_path), tmp_path)
        assert r["status"] == PASS and r["file_hash_identity"] is True

    def test_hash_mismatch_warns_and_defers_to_record_level(self, tmp_path):
        # Documented requirement change (AL-0020): cross-request file-hash
        # identity is unattainable; mismatch WARNs and defers to the
        # record-level gate.
        r = sample_overlap_comparison(
            self._registry(tmp_path, canonical_hash="bbb"), tmp_path
        )
        assert r["status"] == WARN
        assert "record-level" in r["resolution"]

    def test_size_mismatch_warns_pending_record_level(self, tmp_path):
        r = sample_overlap_comparison(
            self._registry(tmp_path, canonical_size=5), tmp_path
        )
        assert r["status"] == WARN

    def test_sample_file_missing_in_canonical_fails(self, tmp_path):
        _job(tmp_path, "raw/mbp1/annual/J1",
             {"glbx-mdp3-20260804.mbp-1.dbn.zst": (4, "aaa")})
        _job(tmp_path, "raw/mbp1/sample/QA",
             {"glbx-mdp3-20260803.mbp-1.dbn.zst": (4, "aaa")})
        reg = Mbp1SourceRegistry(sources=[
            _src("J1", ROLE_FULL_HISTORY, "raw/mbp1/annual/J1"),
            _src("QA", ROLE_M0_QA_SAMPLE, "raw/mbp1/sample/QA"),
        ])
        r = sample_overlap_comparison(reg, tmp_path)
        assert r["status"] == FAIL


class TestRecordLevelGate:
    def _registry(self, tmp_path, sample_files=None, canonical_files=None,
                  extra_sources=(), write_sample_data=True,
                  write_canonical_data=True):
        sample_files = sample_files if sample_files is not None else {
            "glbx-mdp3-20260803.mbp-1.dbn.zst": (4, "aaa")
        }
        canonical_files = canonical_files if canonical_files is not None else {
            "glbx-mdp3-20260803.mbp-1.dbn.zst": (4, "bbb")
        }
        _job(tmp_path, "raw/mbp1/annual/J1", canonical_files,
             write_data=write_canonical_data)
        _job(tmp_path, "raw/mbp1/sample/QA", sample_files,
             write_data=write_sample_data)
        return Mbp1SourceRegistry(sources=[
            _src("J1", ROLE_FULL_HISTORY, "raw/mbp1/annual/J1"),
            _src("QA", ROLE_M0_QA_SAMPLE, "raw/mbp1/sample/QA"),
            *extra_sources,
        ])

    def test_success_path(self, tmp_path):
        reg = self._registry(tmp_path)
        r = record_level_overlap_comparison(
            reg, tmp_path, compare_pair=_identical_pair
        )
        assert r["status"] == PASS
        assert r["n_expected_pairs"] == r["n_pairs_compared"] == 1
        assert set(r["binding"]) == {
            "config_hash", "acquisition_code_hash", "source_manifest_sha256"
        }

    def test_zero_expected_pairs_fails(self, tmp_path):
        reg = self._registry(tmp_path, sample_files={})
        r = record_level_overlap_comparison(
            reg, tmp_path, compare_pair=_identical_pair
        )
        assert r["status"] == FAIL
        assert r["n_expected_pairs"] == 0

    def test_sample_file_missing_on_disk_fails(self, tmp_path):
        reg = self._registry(tmp_path, write_sample_data=False)
        r = record_level_overlap_comparison(
            reg, tmp_path, compare_pair=_identical_pair
        )
        assert r["status"] == FAIL
        assert r["files"][0]["issue"] == "sample_file_missing_on_disk"

    def test_canonical_file_missing_on_disk_fails(self, tmp_path):
        reg = self._registry(tmp_path, write_canonical_data=False)
        r = record_level_overlap_comparison(
            reg, tmp_path, compare_pair=_identical_pair
        )
        assert r["status"] == FAIL
        assert r["files"][0]["issue"] == "canonical_file_missing_on_disk"

    def test_missing_canonical_counterpart_fails(self, tmp_path):
        reg = self._registry(
            tmp_path,
            canonical_files={"glbx-mdp3-20260899.mbp-1.dbn.zst": (4, "bbb")},
        )
        r = record_level_overlap_comparison(
            reg, tmp_path, compare_pair=_identical_pair
        )
        assert r["status"] == FAIL
        assert r["files"][0]["issue"] == "missing_in_canonical_corpus"

    def test_multiple_canonical_counterparts_fail(self, tmp_path):
        extra = _src("J2", ROLE_FULL_HISTORY, "raw/mbp1/annual/J2",
                     start_ns=10, end_ns=20)
        _job(tmp_path, "raw/mbp1/annual/J2",
             {"glbx-mdp3-20260803.mbp-1.dbn.zst": (4, "ccc")})
        reg = self._registry(tmp_path, extra_sources=(extra,))
        r = record_level_overlap_comparison(
            reg, tmp_path, compare_pair=_identical_pair
        )
        assert r["status"] == FAIL
        assert r["files"][0]["issue"] == "multiple_canonical_counterparts"

    @pytest.mark.parametrize(
        "issue", ["record_count_mismatch", "dtype_schema_mismatch",
                  "record_bytes_differ"]
    )
    def test_comparison_issues_fail(self, tmp_path, issue):
        def bad_pair(sample_path, canonical_path, chunk_rows):
            return {"identical": False, "n_records_compared": 5, "issue": issue}

        reg = self._registry(tmp_path)
        r = record_level_overlap_comparison(reg, tmp_path, compare_pair=bad_pair)
        assert r["status"] == FAIL
        assert r["files"][0]["issue"] == issue


class TestSampleLeakDetection:
    def test_case_insensitive_windows_path_leak_detected(self, tmp_path):
        # Misconfiguration: an eligible source path differs only by case from
        # the QA sample path. On Windows both resolve to the same directory,
        # so the sample's files WOULD enter research input; the resolved-path
        # check must catch it even though the registry strings differ.
        _job(tmp_path, "raw/mbp1/s/QA",
             {"glbx-mdp3-20260803.mbp-1.dbn.zst": (4, "aaa")})
        reg = Mbp1SourceRegistry(sources=[
            _src("EVIL", ROLE_FULL_HISTORY, "raw/mbp1/s/qa"),
            _src("QA", ROLE_M0_QA_SAMPLE, "raw/mbp1/s/QA"),
        ])
        resolved_evil = (tmp_path / "raw/mbp1/s/qa").resolve()
        resolved_sample = (tmp_path / "raw/mbp1/s/QA").resolve()
        if resolved_evil != resolved_sample:
            pytest.skip("filesystem is case-sensitive; scenario not reproducible")
        r = source_selection_result(reg, tmp_path)
        assert r["status"] == FAIL
        assert r["sample_files_leaked_into_research_input"]

    def test_clean_selection_passes(self, tmp_path):
        _job(tmp_path, "raw/mbp1/annual/J1",
             {"glbx-mdp3-20260803.mbp-1.dbn.zst": (4, "aaa")})
        _job(tmp_path, "raw/mbp1/sample/QA",
             {"glbx-mdp3-20260803.mbp-1.dbn.zst": (4, "aaa")})
        reg = Mbp1SourceRegistry(sources=[
            _src("J1", ROLE_FULL_HISTORY, "raw/mbp1/annual/J1"),
            _src("QA", ROLE_M0_QA_SAMPLE, "raw/mbp1/sample/QA"),
        ])
        r = source_selection_result(reg, tmp_path)
        assert r["status"] == PASS
        assert r["sample_files_leaked_into_research_input"] == []
        assert r["owners"] == ["J1"]