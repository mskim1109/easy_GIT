from file_viewer.files import Loaded, find_candidates, kind_of, load, md_for_view, save, stat_key

from conftest import write


def test_load_utf8_cp949_bom_and_newline(tmp_path):
    a = write(tmp_path, "a.txt", "가\r\n나\r\n".encode("cp949"))
    b = write(tmp_path, "b.txt", "﻿# 제목\n".encode("utf-8"))
    c = write(tmp_path, "c.txt", "x = 1\n".encode("utf-8"))
    assert load(a) == Loaded("가\n나\n", "cp949", "\r\n", True, False)
    assert load(b) == Loaded("# 제목\n", "utf-8-sig", "\n", True, False)
    assert load(c) == Loaded("x = 1\n", "utf-8", "\n", True, False)


def test_undecodable_is_shown_but_not_editable(tmp_path):
    p = write(tmp_path, "x.txt", b"ok \xff\xfe\xfa end\n")
    got = load(p)
    assert got.editable is False and got.binary is False and "ok" in got.text


def test_binary_by_nul_or_extension(tmp_path):
    assert load(write(tmp_path, "a.bin", b"ab\x00cd")).binary is True
    assert load(write(tmp_path, "b.pdf", b"%PDF-1.7 text only")).binary is True


def test_save_round_trip_keeps_format(tmp_path):
    p = write(tmp_path, "a.txt", "가\r\n나\r\n".encode("cp949"))
    save(p, "가\n다\n", load(p))
    assert p.read_bytes() == "가\r\n다\r\n".encode("cp949")
    q = write(tmp_path, "b.md", "﻿# 제목\n".encode("utf-8"))
    save(q, "# 새 제목\n", load(q))
    assert q.read_bytes() == "﻿# 새 제목\n".encode("utf-8")


def test_kind_of(tmp_path):
    kinds = {n: kind_of(p := write(tmp_path, n, "x\n"), load(p)) for n in ["a.py", "b.json", "c.md", "d.html", "e.htm", "f.txt"]}
    assert kinds == {"a.py": "code", "b.json": "code", "c.md": "md", "d.html": "html", "e.htm": "html", "f.txt": "code"}
    g = write(tmp_path, "g.png", b"\x89PNG\x00")  # assert 안의 := 는 pytest 다시 쓰기가 이전 p 를 씀
    assert kind_of(g, load(g)) == "binary"


def test_stat_key_and_md_for_view(tmp_path):
    assert stat_key(tmp_path / "없음.txt") is None
    assert md_for_view("앞 ![구조도](a.png) 뒤\n![](b.png)") == "앞 [그림: 구조도] 뒤\n[그림]"


def test_find_skips_ignored_dirs(repo):
    write(repo, ".gitignore", "node_modules/\n"); write(repo, "docs/design.md", "x")
    write(repo, "node_modules/p/index.js", "x"); write(repo, "새파일.txt", "x")
    got = find_candidates(repo)
    assert "docs/design.md" in got and "새파일.txt" in got and ".gitignore" in got
    assert not any(p.startswith("node_modules/") for p in got)


def test_find_candidates_without_git(tmp_path):
    write(tmp_path, "plain/a.txt", "x"); write(tmp_path, "plain/.git/HEAD", "x")
    assert find_candidates(tmp_path / "plain") == ["a.txt"]
