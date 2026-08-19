"""Raw-write protection: destination checks resist relative paths, `..`,
case differences, and link aliases. Temporary synthetic files only."""

import os
import sys
from pathlib import Path

import pytest

from nqresearch.rawguard import RawWriteError, assert_write_outside_raw


@pytest.fixture()
def data_root(tmp_path):
    (tmp_path / "raw" / "mbp1").mkdir(parents=True)
    (tmp_path / "qa").mkdir()
    return tmp_path


class TestRawGuard:
    def test_inside_raw_refused(self, data_root):
        with pytest.raises(RawWriteError):
            assert_write_outside_raw(data_root / "raw" / "mbp1" / "x.json", data_root)

    def test_new_subdir_inside_raw_refused(self, data_root):
        with pytest.raises(RawWriteError):
            assert_write_outside_raw(
                data_root / "raw" / "new" / "deep" / "y.parquet", data_root
            )

    def test_outside_raw_allowed(self, data_root):
        assert_write_outside_raw(data_root / "qa" / "artifact.json", data_root)
        assert_write_outside_raw(data_root / "normalized" / "p.parquet", data_root)

    def test_dotdot_escape_into_raw_refused(self, data_root):
        sneaky = data_root / "qa" / ".." / "raw" / "z.json"
        with pytest.raises(RawWriteError):
            assert_write_outside_raw(sneaky, data_root)

    def test_dotdot_out_of_raw_allowed(self, data_root):
        fine = data_root / "raw" / ".." / "qa" / "ok.json"
        assert_write_outside_raw(fine, data_root)

    @pytest.mark.skipif(os.name != "nt", reason="Windows case-insensitivity")
    def test_case_variation_refused(self, data_root):
        upper = data_root / "RAW" / "MBP1" / "x.json"
        with pytest.raises(RawWriteError):
            assert_write_outside_raw(upper, data_root)

    def test_link_alias_refused(self, data_root, tmp_path):
        alias = tmp_path / "alias_dir"
        try:
            os.symlink(data_root / "raw", alias, target_is_directory=True)
        except OSError:
            if sys.platform == "win32":
                import subprocess

                r = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(alias),
                     str(data_root / "raw")],
                    capture_output=True,
                )
                if r.returncode != 0:
                    pytest.skip("cannot create symlink or junction")
            else:
                pytest.skip("cannot create symlink")
        with pytest.raises(RawWriteError):
            assert_write_outside_raw(alias / "hidden.json", data_root)

    def test_prefix_collision_directory_allowed(self, data_root):
        # 'rawx' must not be confused with 'raw'.
        assert_write_outside_raw(data_root / "rawx" / "ok.json", data_root)

    def test_drive_relative_windows_path(self, data_root, monkeypatch):
        if os.name != "nt":
            pytest.skip("Windows drive-relative semantics")
        monkeypatch.chdir(data_root / "raw" / "mbp1")
        drive = os.path.splitdrive(str(data_root))[0]  # e.g. "C:"
        with pytest.raises(RawWriteError):
            assert_write_outside_raw(Path(f"{drive}evil.json"), data_root)

    def test_unc_style_prefix_logic(self):
        from nqresearch.rawguard import _is_within
        from pathlib import Path as P

        assert _is_within(P(r"\\server\share\data\raw\x.json"),
                          P(r"\\server\share\data\raw"))
        assert not _is_within(P(r"\\server\share\data\rawx\x.json"),
                              P(r"\\server\share\data\raw"))

    def test_nested_link_chain_refused(self, data_root, tmp_path):
        hop1 = tmp_path / "hop1"
        hop2 = tmp_path / "hop2"

        def link(dst, target):
            try:
                os.symlink(target, dst, target_is_directory=True)
            except OSError:
                if sys.platform == "win32":
                    import subprocess

                    r = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(dst), str(target)],
                        capture_output=True,
                    )
                    if r.returncode != 0:
                        pytest.skip("cannot create link/junction")
                else:
                    pytest.skip("cannot create symlink")

        link(hop1, data_root / "raw")
        link(hop2, hop1)
        with pytest.raises(RawWriteError):
            assert_write_outside_raw(hop2 / "mbp1" / "deep.json", data_root)

    def test_final_name_traversal_in_write_artifact(self, data_root, monkeypatch):
        # A path-containing artifact NAME must not escape the checked out_dir
        # into raw.
        from nqresearch.config import clear_config_cache
        from nqresearch.qa.report import write_artifact

        monkeypatch.setenv("NQR_DATA_ROOT", str(data_root))
        clear_config_cache()
        with pytest.raises(RawWriteError):
            write_artifact({"a": 1}, data_root / "qa",
                           "../raw/mbp1/evil", data_root)
        clear_config_cache()

    def test_write_artifact_uses_resolved_path(self, data_root, monkeypatch):
        from nqresearch.config import clear_config_cache
        from nqresearch.qa.report import write_artifact

        monkeypatch.setenv("NQR_DATA_ROOT", str(data_root))
        clear_config_cache()
        out = write_artifact({"a": 1, "status": "PASS"}, data_root / "qa",
                             "fine", data_root)
        assert out.is_file() and out.name == "fine.json"
        clear_config_cache()

    def test_write_artifact_refuses_raw_destination(self, data_root, monkeypatch):
        from nqresearch.qa.report import write_artifact

        monkeypatch.setenv("NQR_DATA_ROOT", str(data_root))
        from nqresearch.config import clear_config_cache

        clear_config_cache()
        with pytest.raises(RawWriteError):
            write_artifact({"a": 1}, data_root / "raw" / "evil", "x", data_root)
        clear_config_cache()

    def test_run_cached_refuses_raw_cache_dir(self, data_root, monkeypatch):
        from nqresearch.config import clear_config_cache
        from nqresearch.qa.cache import run_cached

        monkeypatch.setenv("NQR_DATA_ROOT", str(data_root))
        clear_config_cache()
        f = data_root / "qa" / "input.bin"
        f.write_bytes(b"x")
        with pytest.raises(RawWriteError):
            run_cached([f], lambda p: {"ok": 1}, (), 1,
                       data_root / "raw" / "cache", {})
        clear_config_cache()
