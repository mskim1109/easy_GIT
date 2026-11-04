"""git status 로 M / + / 흐림을 계산한다. git 은 읽기만 하고 lock 을 만들지 않는다."""
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class GitError(Exception):
    """git 실행 실패(lock 등). 폴링이 삼킨다."""


@dataclass(frozen=True)
class GitState:
    # 시작 폴더 기준 상대 경로, "/" 구분. 폴더 항목은 끝에 "/".
    modified: frozenset[str]
    untracked: frozenset[str]
    ignored: frozenset[str]
    changed_dirs: frozenset[str]  # modified·untracked 의 조상 폴더(끝 "/" 없음)


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
                          creationflags=subprocess.CREATE_NO_WINDOW)


def _ancestors(rel: str) -> list[str]:
    """"a/b/c.txt" → ["a/", "a/b/"]"""
    parts = rel.rstrip("/").split("/")
    return ["/".join(parts[:k]) + "/" for k in range(1, len(parts))]


def read_state(root: Path) -> GitState | None:
    try:
        top = run_git(root, "rev-parse", "--show-prefix")
    except FileNotFoundError:  # git 이 없음
        return None
    if top.returncode != 0:
        return None
    prefix = top.stdout.decode("utf-8", "replace").rstrip("\r\n")
    st = run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal",
                 "--ignored=matching", "--", ".")
    if st.returncode != 0:
        raise GitError(st.stderr.decode("utf-8", "replace").strip())
    sets = {"??": set(), "!!": set(), "": set()}
    fields = st.stdout.decode("utf-8", "replace").split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        xy, path = entry[:2], entry[3:]
        if "R" in xy or "C" in xy:
            i += 1  # 다음 필드는 원래 경로
        if path.startswith(prefix) and path != prefix:
            sets.get(xy, sets[""]).add(path[len(prefix):])
    modified, untracked, ignored = sets[""], sets["??"], sets["!!"]
    changed = set()
    for p in modified | untracked:
        changed.update(a.rstrip("/") for a in _ancestors(p))
        if p.endswith("/"):
            changed.add(p.rstrip("/"))
    return GitState(frozenset(modified), frozenset(untracked), frozenset(ignored), frozenset(changed))


def mark(state: GitState | None, rel: str, is_dir: bool) -> Literal["M", "+", "•", ""]:
    if state is None:
        return ""
    if is_dir:
        return "•" if rel in state.changed_dirs else ""
    if rel in state.modified:
        return "M"
    if rel in state.untracked or any(a in state.untracked for a in _ancestors(rel)):
        return "+"
    return ""


def dimmed(state: GitState | None, rel: str) -> bool:
    if rel == ".git" or rel.startswith(".git/"):
        return True
    if state is None:
        return False
    return (rel in state.ignored or rel + "/" in state.ignored
            or any(a in state.ignored for a in _ancestors(rel)))
