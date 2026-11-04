import subprocess

from file_viewer.gitstate import dimmed, mark, read_state

from conftest import git, write


def _base(repo):
    write(repo, "a/b.txt", "1\n"); write(repo, "c.txt", "1\n")
    write(repo, ".gitignore", ".venv/\n*.log\n")
    git(repo, "add", "."); git(repo, "commit", "-m", "init")


def test_modified_untracked_and_folder_mark(repo):
    _base(repo)
    write(repo, "a/b.txt", "2\n"); write(repo, "d/e.txt", "new\n"); write(repo, "f.txt", "new\n")
    s = read_state(repo)
    assert [mark(s, "a/b.txt", False), mark(s, "a", True), mark(s, "d", True), mark(s, "d/e.txt", False),
            mark(s, "f.txt", False), mark(s, "c.txt", False)] == ["M", "•", "•", "+", "+", ""]


def test_staged_and_renamed_count_as_modified(repo):
    _base(repo)
    write(repo, "c.txt", "2\n"); git(repo, "add", "c.txt")
    git(repo, "mv", "a/b.txt", "a/g.txt")
    s = read_state(repo)
    assert mark(s, "c.txt", False) == "M" and mark(s, "a/g.txt", False) == "M"


def test_ignored_dir_is_one_entry(repo):
    _base(repo)
    for i in range(50): write(repo, f".venv/lib/m{i}.py", "x\n")
    write(repo, "x.log", "x\n")
    s = read_state(repo)
    assert ".venv/" in s.ignored and not any(p.startswith(".venv/lib") for p in s.ignored)
    assert dimmed(s, ".venv") and dimmed(s, ".venv/lib/m1.py") and dimmed(s, "x.log")
    assert dimmed(s, ".git") and dimmed(s, ".git/config") and not dimmed(s, "c.txt")
    assert mark(s, ".venv", True) == ""


def test_subdir_root_sees_only_its_files(repo):
    _base(repo)
    write(repo, "a/b.txt", "2\n"); write(repo, "c.txt", "2\n")
    assert read_state(repo / "a").modified == {"b.txt"}


def test_korean_path(repo):
    _base(repo)
    write(repo, "한글/설정.txt", "가\n".encode("cp949"))
    s = read_state(repo)
    assert mark(s, "한글/설정.txt", False) == "+" and mark(s, "한글", True) == "•"


def test_not_a_repo_and_no_locks(tmp_path, monkeypatch, repo):
    # tmp_path/"plain" 은 repo(tmp_path/"repo")의 형제 폴더라 git 저장소가 아니다.
    (tmp_path / "plain").mkdir()
    assert read_state(tmp_path / "plain") is None
    assert dimmed(None, ".git") and mark(None, "x", False) == ""
    seen = []
    real = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: seen.append(k.get("env", {})) or real(*a, **k))
    read_state(repo)
    assert seen and all(e.get("GIT_OPTIONAL_LOCKS") == "0" for e in seen)
