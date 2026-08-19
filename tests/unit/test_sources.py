"""Source-provenance registry and safe source selection."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from nqresearch import paths
from nqresearch.config import (
    ROLE_FULL_HISTORY,
    ROLE_M0_QA_SAMPLE,
    Mbp1Source,
    Mbp1SourceRegistry,
    clear_config_cache,
    effective_config_hash,
    load_mbp1_sources,
)
from nqresearch.qa_corpus import qa_corpus_files
from nqresearch.sources import (
    ResearchOverlapError,
    SourceRegistryError,
    m0_sample_dir,
    qa_sample_source,
    source_dir,
    validate_adjacent_ranges,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_config_cache()
    yield
    clear_config_cache()


def _src(request_id, role, start_ns, end_ns, path=None, eligible=None, **overrides):
    kwargs = dict(
        request_id=request_id,
        path=path or f"raw/mbp1/x/{request_id}",
        role=role,
        research_eligible=(role == ROLE_FULL_HISTORY) if eligible is None else eligible,
        dataset="GLBX.MDP3",
        symbols=["NQ.FUT"],
        stype_in="parent",
        stype_out="instrument_id",
        start_ns=start_ns,
        end_ns=end_ns,
        manifest_sha256="0" * 64,
    )
    kwargs.update(overrides)
    return Mbp1Source(schema="mbp-1", **kwargs)


class TestRegistryModel:
    def test_committed_registry_loads(self):
        reg = load_mbp1_sources()
        assert len(reg.sources) == 3
        assert len(reg.research_sources()) == 2
        sample = qa_sample_source(reg)
        assert sample.request_id == "GLBX-20260817-N8HD86YKNS"
        assert sample.research_eligible is False

    def test_sample_must_not_be_research_eligible(self):
        with pytest.raises(ValidationError):
            _src("J1", ROLE_M0_QA_SAMPLE, 0, 1, eligible=True)

    def test_unknown_role_rejected(self):
        with pytest.raises(ValidationError):
            _src("J1", "SOME_OTHER_ROLE", 0, 1)

    def test_full_history_must_be_research_eligible(self):
        with pytest.raises(ValidationError):
            _src("J1", ROLE_FULL_HISTORY, 0, 1, eligible=False)

    def test_start_must_precede_end(self):
        with pytest.raises(ValidationError):
            _src("J1", ROLE_FULL_HISTORY, 10, 10)

    @pytest.mark.parametrize("bad", ["../escape/J1", "C:/abs/J1", "/abs/J1"])
    def test_unsafe_paths_rejected(self, bad):
        with pytest.raises(ValidationError):
            _src("J1", ROLE_FULL_HISTORY, 0, 1, path=bad)

    def test_manifest_sha256_format_enforced(self):
        with pytest.raises(ValidationError):
            _src("J1", ROLE_FULL_HISTORY, 0, 1, manifest_sha256="nothex")

    def test_spec_field_conflicts_rejected(self):
        with pytest.raises(ValidationError):
            _src("J1", ROLE_FULL_HISTORY, 0, 1, dataset="XNAS.ITCH")
        with pytest.raises(ValidationError):
            _src("J1", ROLE_FULL_HISTORY, 0, 1, symbols=["ES.FUT"])

    def test_duplicate_ids_and_paths_rejected(self):
        with pytest.raises(ValidationError):
            Mbp1SourceRegistry(sources=[
                _src("J1", ROLE_FULL_HISTORY, 0, 10, path="raw/mbp1/a/J1"),
                _src("J1", ROLE_FULL_HISTORY, 10, 20, path="raw/mbp1/b/J1"),
            ])
        with pytest.raises(ValidationError):
            Mbp1SourceRegistry(sources=[
                _src("J1", ROLE_FULL_HISTORY, 0, 10, path="raw/mbp1/a/J1"),
                _src("J2", ROLE_FULL_HISTORY, 10, 20, path="raw/mbp1/a/J1"),
            ])

    def test_committed_registry_manifest_hashes_present(self):
        for s in load_mbp1_sources().sources:
            assert len(s.manifest_sha256) == 64

    def test_registry_affects_config_hash(self, tmp_path):
        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='x'\n")
        reg_yaml = root / "config" / "data" / "mbp1_sources.yaml"
        reg_yaml.write_text(
            "sources:\n"
            "  - request_id: J1\n    path: raw/mbp1/a/J1\n"
            "    role: FULL_HISTORY_CANONICAL\n    research_eligible: true\n"
            "    dataset: GLBX.MDP3\n    schema: mbp-1\n    symbols: [NQ.FUT]\n"
            "    stype_in: parent\n    stype_out: instrument_id\n"
            f"    manifest_sha256: \"{'0' * 64}\"\n"
            "    start_ns: 0\n    end_ns: 10\n"
        )
        h1 = effective_config_hash(root)
        reg_yaml.write_text(reg_yaml.read_text().replace("end_ns: 10", "end_ns: 20"))
        clear_config_cache()
        assert effective_config_hash(root) != h1


class TestAdjacency:
    def test_committed_annual_jobs_are_adjacent(self):
        reg = load_mbp1_sources()
        result = validate_adjacent_ranges(reg.research_sources())
        assert result["adjacent"] is True
        assert result["range_start_ns"] == 1723852800000000000
        assert result["range_end_ns"] == 1786924800000000000

    def test_gap_detected(self):
        r = validate_adjacent_ranges(
            [_src("A", ROLE_FULL_HISTORY, 0, 10), _src("B", ROLE_FULL_HISTORY, 15, 20)]
        )
        assert not r["adjacent"] and r["issues"][0]["issue"] == "gap"

    def test_overlap_detected(self):
        r = validate_adjacent_ranges(
            [_src("A", ROLE_FULL_HISTORY, 0, 12), _src("B", ROLE_FULL_HISTORY, 10, 20)]
        )
        assert not r["adjacent"] and r["issues"][0]["issue"] == "overlap"


def _make_job(data_root: Path, rel: str, dates: list[str]):
    d = data_root / rel
    d.mkdir(parents=True)
    for date in dates:
        (d / f"glbx-mdp3-{date}.mbp-1.dbn.zst").write_bytes(b"x")


class TestResearchInput:
    def test_sample_excluded_and_partitions_unique(self, tmp_path):
        _make_job(tmp_path, "raw/mbp1/a/J1", ["20240818", "20240819"])
        _make_job(tmp_path, "raw/mbp1/b/J2", ["20240820"])
        _make_job(tmp_path, "raw/mbp1/s/QA", ["20240819"])  # overlaps J1's date
        reg = Mbp1SourceRegistry(sources=[
            _src("J1", ROLE_FULL_HISTORY, 0, 10, path="raw/mbp1/a/J1"),
            _src("J2", ROLE_FULL_HISTORY, 10, 20, path="raw/mbp1/b/J2"),
            _src("QA", ROLE_M0_QA_SAMPLE, 3, 6, path="raw/mbp1/s/QA"),
        ])
        files = qa_corpus_files(reg, tmp_path)
        assert sorted(files) == ["20240818", "20240819", "20240820"]
        # The QA sample's copy of 20240819 must NOT be the selected file.
        assert "raw" in str(files["20240819"])
        assert str(tmp_path / "raw/mbp1/a/J1") in str(files["20240819"])
        assert "QA" not in str(files["20240819"])

    def test_research_eligible_overlap_fails_loudly(self, tmp_path):
        _make_job(tmp_path, "raw/mbp1/a/J1", ["20240818"])
        _make_job(tmp_path, "raw/mbp1/b/J2", ["20240818"])
        reg = Mbp1SourceRegistry(sources=[
            _src("J1", ROLE_FULL_HISTORY, 0, 10, path="raw/mbp1/a/J1"),
            _src("J2", ROLE_FULL_HISTORY, 10, 20, path="raw/mbp1/b/J2"),
        ])
        with pytest.raises(ResearchOverlapError):
            qa_corpus_files(reg, tmp_path)

    def test_no_eligible_sources_fails(self, tmp_path):
        reg = Mbp1SourceRegistry(sources=[
            _src("QA", ROLE_M0_QA_SAMPLE, 0, 1, path="raw/mbp1/s/QA"),
        ])
        with pytest.raises(SourceRegistryError):
            qa_corpus_files(reg, tmp_path)


class TestSampleScoping:
    def test_m0_sample_dir_is_registry_scoped(self):
        # The Milestone 0 audit directory is exactly the registered sample job,
        # never the whole raw/mbp1 tree that also holds the annual corpus.
        d = m0_sample_dir()
        assert d == paths.data_root() / (
            "raw/mbp1/2026-08-03_2026-08-15/GLBX-20260817-N8HD86YKNS"
        )
        assert d != paths.raw_mbp1()

    def test_sample_selection_requires_exactly_one(self):
        reg = Mbp1SourceRegistry(sources=[
            _src("J1", ROLE_FULL_HISTORY, 0, 10),
        ])
        with pytest.raises(SourceRegistryError):
            qa_sample_source(reg)

    def test_source_dir_is_relative_to_data_root(self, tmp_path):
        s = _src("J1", ROLE_FULL_HISTORY, 0, 10, path="raw/mbp1/a/J1")
        assert source_dir(s, tmp_path) == tmp_path / "raw/mbp1/a/J1"
        # And with no explicit root, it resolves under the configured D: root.
        assert source_dir(s) == paths.data_root() / "raw/mbp1/a/J1"
