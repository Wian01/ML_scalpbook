import subprocess

from nqresearch.qa.report import _git_sha


class TestGitSha:
    def test_unborn_repository_records_none_not_HEAD(self, tmp_path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        assert _git_sha(tmp_path) is None

    def test_non_repository_records_none(self, tmp_path):
        assert _git_sha(tmp_path) is None

    def test_repository_with_commit_records_sha(self, tmp_path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        (tmp_path / "a.txt").write_text("x")
        env_args = ["-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(["git", "-C", str(tmp_path), "add", "a.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), *env_args, "commit", "-q", "-m", "t",
             "--no-gpg-sign"],
            check=True,
        )
        sha = _git_sha(tmp_path)
        assert sha is not None and len(sha) == 40
