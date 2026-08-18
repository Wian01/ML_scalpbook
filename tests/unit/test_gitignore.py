"""Git-ignore behavior: the data tree is ignored, but committed configuration
under config/data/ must NOT be (a bare `data/` pattern would ignore it)."""

import subprocess

import pytest

from nqresearch import paths


def _is_ignored(relpath: str) -> bool:
    """git check-ignore: rc 0 = ignored, rc 1 = not ignored. Any other return
    code is a Git EXECUTION failure (e.g. dubious-ownership under a different
    account) and must fail loudly — treating it as 'not ignored' would let
    the negative assertions pass vacuously."""
    out = subprocess.run(
        ["git", "-C", str(paths.ROOT), "check-ignore", "-q", relpath],
        capture_output=True, text=True,
    )
    if out.returncode == 0:
        return True
    if out.returncode == 1:
        return False
    raise RuntimeError(
        f"git check-ignore failed (rc={out.returncode}) for {relpath!r}: "
        f"{out.stderr.strip()}"
    )


class TestGitIgnore:
    @pytest.mark.parametrize(
        "relpath",
        ["config/data/paths.yaml", "config/data/sessions.yaml"],
    )
    def test_config_files_are_not_ignored(self, relpath):
        assert (paths.ROOT / relpath).is_file(), f"{relpath} must exist"
        assert not _is_ignored(relpath), f"{relpath} must be committed to Git"

    @pytest.mark.parametrize(
        "relpath",
        ["data/qa/m0/storage_gate.json", "data/raw/x.dbn.zst", "data/"],
    )
    def test_data_tree_is_ignored(self, relpath):
        assert _is_ignored(relpath)
