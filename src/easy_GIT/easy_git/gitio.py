"""git CLI 호출: 커밋·변경 목록, 파일별 행."""

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .fulldiff import Row, parse_unified


class GitError(Exception):
    def __init__(self, output: str):
        super().__init__(output)
        self.output = output


def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def run_git(repo: Path, *args: str, input: bytes | None = None, check: bool = True) -> bytes:
    # stdin 을 DEVNULL 로 막아 콘솔 키 입력을 git 이 빼앗지 않게 한다.
    feed = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
    p = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, **feed,
    )
    if check and p.returncode != 0:
        raise GitError(decode_text(p.stderr + p.stdout))
    return p.stdout


def repo_root(path: Path) -> Path | None:
    try:
        out = run_git(path, "rev-parse", "--show-toplevel")
    except GitError:
        return None
    return Path(decode_text(out).strip()).resolve()


@dataclass(frozen=True)
class Commit:
    sha: str
    short: str
    parents: tuple[str, ...]
    author: str
    when: int
    subject: str
    body: str


@dataclass(frozen=True)
class FileChange:
    group: Literal["commit", "staged", "unstaged"]
    status: str
    path: str
    old_path: str | None = None
    added: int | None = None
    deleted: int | None = None
    binary: bool = False
    base: str = ""
    target: str = ""


def commits(repo: Path, limit: int = 200) -> list[Commit]:
    # ponytail: 200개 고정, 더 보기는 필요해지면
    try:
        out = run_git(repo, "log", f"-n{limit}", "--format=%H%x1f%h%x1f%P%x1f%an%x1f%at%x1f%s%x1f%b%x1e")
    except GitError:
        return []
    result = []
    for rec in decode_text(out).split("\x1e"):
        rec = rec.lstrip("\n")
        if not rec:
            continue
        sha, short, parents, author, when, subject, body = rec.split("\x1f", 6)
        result.append(Commit(sha, short, tuple(parents.split()), author, int(when), subject, body))
    return result


def _diff(repo: Path, *args: str) -> bytes:
    return run_git(repo, "-c", "core.quotepath=false", "diff", *args)


def _changes(repo: Path, group: str, *diff_args: str, base: str = "", target: str = "") -> list[FileChange]:
    stats: dict[str, tuple[int | None, int | None, bool]] = {}
    parts = decode_text(_diff(repo, "--numstat", "-z", "-M", *diff_args)).split("\0")
    i = 0
    while i < len(parts) and parts[i]:
        a, d, p = parts[i].split("\t", 2)
        if p:
            i += 1
        else:  # 이름 변경: "a\td\t\0old\0new\0"
            p = parts[i + 2]
            i += 3
        stats[p] = (None, None, True) if a == "-" else (int(a), int(d), False)

    result = []
    parts = decode_text(_diff(repo, "--name-status", "-z", "-M", *diff_args)).split("\0")
    i = 0
    while i < len(parts) and parts[i]:
        st = parts[i]
        if st[0] in "RC":  # "R100\0old\0new\0"
            old, path = parts[i + 1], parts[i + 2]
            i += 3
        else:
            old, path = None, parts[i + 1]
            i += 2
        added, deleted, binary = stats.get(path, (None, None, False))
        result.append(FileChange(group, st[0], path, old, added, deleted, binary, base, target))
    return result


def commit_changes(repo: Path, commit: Commit) -> list[FileChange]:
    if commit.parents:
        base = commit.parents[0]
    else:
        base = decode_text(run_git(repo, "hash-object", "-t", "tree", "--stdin", input=b"")).strip()
    return _changes(repo, "commit", base, commit.sha, base=base, target=commit.sha)


def working_changes(repo: Path) -> tuple[list[FileChange], list[FileChange]]:
    staged = _changes(repo, "staged", "--cached")
    unstaged = _changes(repo, "unstaged")
    out = run_git(repo, "-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard", "-z")
    for path in filter(None, decode_text(out).split("\0")):
        try:
            data = (repo / path).read_bytes()
        except FileNotFoundError:  # 목록을 얻은 직후 지워진 파일
            continue
        lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        unstaged.append(FileChange("unstaged", "A", path, added=lines, deleted=0, binary=b"\0" in data[:8000]))
    return staged, unstaged


def file_rows(repo: Path, change: FileChange) -> list[Row] | None:
    if change.binary:
        return None
    if change.group == "unstaged" and change.status == "A":
        try:
            data = (repo / change.path).read_bytes()
        except FileNotFoundError:
            return []
        lines = decode_text(data).split("\n")
        if lines[-1] == "":
            lines.pop()
        return [Row("add", None, n, t.removesuffix("\r")) for n, t in enumerate(lines, 1)]
    args = {"commit": (change.base, change.target), "staged": ("--cached",), "unstaged": ()}[change.group]
    out = _diff(repo, "--no-color", "--no-ext-diff", "-M", "-U1000000", *args, "--", *_paths(change))
    if b"Binary files" in out.partition(b"\n@@")[0]:
        return None
    # 줄마다 따로 해독: UTF-8 경로 헤더, 이전 UTF-8 / 이후 CP949 처럼 섞여도 깨지지 않게
    return parse_unified("\n".join(decode_text(line) for line in out.split(b"\n")))


def _paths(change: FileChange) -> tuple[str, ...]:
    return (change.old_path, change.path) if change.old_path else (change.path,)


def _head(repo: Path) -> bytes:
    return run_git(repo, "rev-parse", "-q", "--verify", "HEAD", check=False)


def stage(repo: Path, change: FileChange) -> None:
    run_git(repo, "add", "--", *_paths(change))


def unstage(repo: Path, change: FileChange) -> None:
    if _head(repo):
        run_git(repo, "restore", "--staged", "--", *_paths(change))
    else:
        run_git(repo, "rm", "--cached", "-q", "--", change.path)


def commit(repo: Path, message: str) -> tuple[bool, str]:
    if not message.strip():
        return False, "커밋 메시지가 비어 있습니다."
    try:  # --quiet: stage된 것이 없으면 종료 코드 0, 있으면 1(GitError)
        run_git(repo, "diff", "--cached", "--quiet")
        return False, "Stage된 파일이 없습니다."
    except GitError:
        pass
    try:  # 훅은 평소처럼 돈다. --no-verify 금지.
        return True, decode_text(run_git(repo, "commit", "-F", "-", input=message.encode("utf-8")))
    except GitError as e:
        return False, e.output


def snapshot(repo: Path) -> str:
    # ponytail: 1초마다 git status 전체 실행. 큰 저장소에서 느리면 파일 감시로
    status = run_git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    h = hashlib.sha1(_head(repo) + status)
    parts = status.split(b"\0")
    i = 0
    while i < len(parts) and parts[i]:
        entry = parts[i]
        paths = [entry[3:]]
        i += 1
        if any(c in b"RC" for c in entry[:2]):  # "XY new\0orig\0"
            paths.append(parts[i])
            i += 1
        for p in paths:
            try:
                st = (repo / decode_text(p)).stat()
                h.update(f"{st.st_mtime_ns},{st.st_size};".encode())
            except OSError:
                h.update(b"-;")
    return h.hexdigest()
