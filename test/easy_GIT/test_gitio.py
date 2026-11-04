from conftest import git, write
from easy_git.fulldiff import Row
from easy_git.gitio import (
    commit, commit_changes, commits, decode_text, file_rows, repo_root, snapshot, stage, unstage, working_changes,
)


def test_repo_root_from_subdir(repo, tmp_path):
    sub = repo / "a" / "b"; sub.mkdir(parents=True)
    assert repo_root(sub) == repo.resolve()
    (tmp_path / "plain").mkdir()
    assert repo_root(tmp_path / "plain") is None

def test_commits_korean_message(repo):
    write(repo, "a.txt", "1\n"); git(repo, "add", "."); git(repo, "commit", "-m", "설정 로더 보강\n\n설정 파일이 없을 때 빈 설정으로 시작.")
    [c] = commits(repo)
    assert (c.subject, c.body.strip(), c.author, c.parents) == ("설정 로더 보강", "설정 파일이 없을 때 빈 설정으로 시작.", "tester", ())
    assert len(c.short) >= 7 and c.sha.startswith(c.short)

def test_empty_repo(repo):
    assert commits(repo) == []
    write(repo, "new.txt", "a\nb\n"); git(repo, "add", ".")
    staged, unstaged = working_changes(repo)
    assert unstaged == []
    assert [(f.group, f.status, f.path, f.added, f.deleted) for f in staged] == [("staged", "A", "new.txt", 2, 0)]
    assert [r.kind for r in file_rows(repo, staged[0])] == ["add", "add"]

def test_commit_changes_root_and_rename(repo):
    write(repo, "a.txt", "1\n2\n3\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    git(repo, "mv", "a.txt", "b.txt"); git(repo, "commit", "-m", "c2")
    second, first = commits(repo)
    [r] = commit_changes(repo, second)
    assert (r.status, r.old_path, r.path) == ("R", "a.txt", "b.txt")
    [a] = commit_changes(repo, first)
    assert (a.status, a.path, a.added, a.deleted) == ("A", "a.txt", 3, 0)
    assert [x.kind for x in file_rows(repo, a)] == ["add"] * 3

def test_merge_commit_compares_first_parent(repo):
    write(repo, "a.txt", "1\n"); git(repo, "add", "."); git(repo, "commit", "-m", "base")
    git(repo, "switch", "-c", "side"); write(repo, "b.txt", "x\n"); git(repo, "add", "."); git(repo, "commit", "-m", "side")
    git(repo, "switch", "main"); git(repo, "merge", "--no-ff", "-m", "merge", "side")
    assert [f.path for f in commit_changes(repo, commits(repo)[0])] == ["b.txt"]

def test_partly_staged_file_appears_in_both_groups(repo):
    write(repo, "a.txt", "x\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "a.txt", "x\ny\n"); git(repo, "add", "a.txt")
    write(repo, "a.txt", "x\ny\nz\n")
    staged, unstaged = working_changes(repo)
    assert [(f.path, f.added) for f in staged] == [("a.txt", 1)]
    assert [(f.path, f.added) for f in unstaged] == [("a.txt", 1)]
    assert file_rows(repo, staged[0]) == [Row("same", 1, 1, "x"), Row("add", None, 2, "y")]
    assert file_rows(repo, unstaged[0]) == [Row("same", 1, 1, "x"), Row("same", 2, 2, "y"), Row("add", None, 3, "z")]

def test_untracked_and_binary(repo):
    write(repo, "new.txt", "a\nb\n"); (repo / "img.bin").write_bytes(b"\x00\x01")
    _, unstaged = working_changes(repo)
    by = {f.path: f for f in unstaged}
    assert (by["new.txt"].status, by["new.txt"].added, by["new.txt"].binary) == ("A", 2, False)
    assert by["img.bin"].binary is True and file_rows(repo, by["img.bin"]) is None

def test_korean_path_and_cp949_content(repo):
    write(repo, "한글/설정.txt", "포트=8080\n", encoding="cp949"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "한글/설정.txt", "포트=9090\n", encoding="cp949")
    _, [f] = working_changes(repo)
    assert f.path == "한글/설정.txt"
    assert file_rows(repo, f) == [Row("del", 1, None, "포트=8080"), Row("add", None, 1, "포트=9090")]

def test_mixed_encoding_old_utf8_new_cp949(repo):
    write(repo, "한글/설정.txt", "포트=8080\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "한글/설정.txt", "포트=9090\n", encoding="cp949")
    _, [f] = working_changes(repo)
    assert file_rows(repo, f) == [Row("del", 1, None, "포트=8080"), Row("add", None, 1, "포트=9090")]

def test_decode_text():
    assert decode_text("한글".encode("cp949")) == "한글"
    assert decode_text("﻿abc".encode("utf-8")) == "abc"

def _partly_staged(repo):
    write(repo, "a.txt", "x\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "a.txt", "x\ny\n"); git(repo, "add", "a.txt"); write(repo, "a.txt", "x\ny\nz\n")

def test_stage_and_unstage_whole_file(repo):
    _partly_staged(repo)
    stage(repo, working_changes(repo)[1][0])
    staged, unstaged = working_changes(repo)
    assert ([f.added for f in staged], unstaged) == ([2], [])
    unstage(repo, staged[0])
    staged, unstaged = working_changes(repo)
    assert (staged, [f.path for f in unstaged]) == ([], ["a.txt"])

def test_unstage_in_empty_repo(repo):
    write(repo, "n.txt", "a\n"); git(repo, "add", ".")
    unstage(repo, working_changes(repo)[0][0])
    staged, unstaged = working_changes(repo)
    assert (staged, [(f.path, f.status) for f in unstaged]) == ([], [("n.txt", "A")])

def test_unstage_in_empty_repo_after_edit_keeps_file(repo):
    write(repo, "n.txt", "a\n"); git(repo, "add", "."); write(repo, "n.txt", "a\nb\n")
    unstage(repo, working_changes(repo)[0][0])
    staged, unstaged = working_changes(repo)
    assert (staged, [(f.path, f.status, f.added) for f in unstaged]) == ([], [("n.txt", "A", 2)])
    assert (repo / "n.txt").read_text() == "a\nb\n"

def test_commit_success_with_korean_message(repo):
    write(repo, "a.txt", "1\n"); git(repo, "add", ".")
    ok, _ = commit(repo, "첫 커밋")
    assert ok and commits(repo)[0].subject == "첫 커밋"

def test_commit_refuses_empty_message_or_nothing_staged(repo):
    write(repo, "a.txt", "1\n"); git(repo, "add", ".")
    assert commit(repo, "   ") == (False, "커밋 메시지가 비어 있습니다.")
    git(repo, "commit", "-m", "c1")
    assert commit(repo, "x") == (False, "Stage된 파일이 없습니다.")

def test_commit_runs_pre_commit_hook_and_shows_output(repo):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho hook says no >&2\nexit 1\n", newline="\n")
    write(repo, "a.txt", "1\n"); git(repo, "add", ".")
    ok, out = commit(repo, "x")
    assert not ok and "hook says no" in out and commits(repo) == []

def test_snapshot_changes_when_modified_file_is_edited_again(repo):
    write(repo, "a.txt", "1\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "a.txt", "2\n")
    s1 = snapshot(repo)
    assert snapshot(repo) == s1
    write(repo, "a.txt", "22\n")
    assert snapshot(repo) != s1

def test_snapshot_changes_on_new_commit(repo):
    write(repo, "a.txt", "1\n"); git(repo, "add", ".")
    s1 = snapshot(repo); git(repo, "commit", "-m", "c1")
    assert snapshot(repo) != s1
