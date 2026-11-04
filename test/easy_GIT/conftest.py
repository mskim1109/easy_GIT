import subprocess

import pytest


@pytest.fixture
def repo(tmp_path, monkeypatch):
    cfg = tmp_path / "gitconfig"
    cfg.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(k, "tester")
    for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, "t@example.com")
    r = tmp_path / "r"
    subprocess.run(["git", "init", "-b", "main", str(r)], check=True, capture_output=True)
    return r


def git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout.decode("utf-8")


def write(repo, rel, text, encoding="utf-8") -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding=encoding, newline="")
