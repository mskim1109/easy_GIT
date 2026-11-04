import asyncio
import os
import time

from rich.style import Style

import file_viewer.files as files
import file_viewer.gitstate as gitstate
import file_viewer.shellops as shellops
from textual.command import CommandList, CommandPalette
from textual.widgets import OptionList

from file_viewer.app import FileTree, FileViewerApp, MenuScreen

from conftest import git, settle, wait_until, write


def run(repo, body, size=(120, 40), **kw):
    """앱을 띄워 body(app, pilot) 를 돌린다. 비동기 테스트 플러그인 없이 asyncio.run 으로."""
    async def go():
        app = FileViewerApp(repo, **kw)
        async with app.run_test(size=size) as pilot:
            await settle(app, pilot)
            await body(app, pilot)
    asyncio.run(go())


def _files(repo):
    write(repo, "config.json", '{\n  "name": "easy-git"\n}\n')
    write(repo, "notes.md", "# 제목\n\n![구조](a.png)\n")
    write(repo, "page.html", "<p>안녕</p>\n")
    write(repo, "logo.png", b"\x89PNG\x00\x00")
    git(repo, "add", "config.json"); git(repo, "commit", "-m", "init")
    write(repo, "config.json", '{\n  "name": "file-viewer"\n}\n')


def _node(tree, name):
    return next(n for n in tree.root.children if n.data.path.name == name)


def _shown(tab):
    """#body 안에서 지금 보이는 위젯 id."""
    return [c.id for c in tab.query_one("#body").children if c.display]


async def _open(app, pilot, path):
    app.open_file(path)
    await settle(app, pilot)
    return app.current_tab


def test_open_file_reuses_tab(repo):
    _files(repo)
    async def body(app, pilot):
        await _open(app, pilot, repo / "config.json")
        tab = await _open(app, pilot, repo / "config.json")
        assert len(app.tab_ids) == 1
        assert tab.kind == "code" and '"file-viewer"' in tab.loaded.text
        assert _shown(tab) == ["code"]
    run(repo, body)


def test_enter_in_tree_opens_file(repo):
    _files(repo)
    async def body(app, pilot):
        tree = app.query_one("#tree", FileTree)
        await wait_until(lambda: any(n.data.path.name == "config.json" for n in tree.root.children), app, pilot)
        tree.focus()
        tree.move_cursor(_node(tree, "config.json"))
        await pilot.press("enter")
        await settle(app, pilot)
        assert app.current_tab.path == repo / "config.json"
    run(repo, body)


def test_tab_and_w(repo):
    _files(repo)
    async def body(app, pilot):
        await _open(app, pilot, repo / "config.json")
        await _open(app, pilot, repo / "page.html")
        assert app.current_tab.path.name == "page.html"
        await pilot.press("tab"); await settle(app, pilot)
        assert app.current_tab.path.name == "config.json"
        await pilot.press("shift+tab"); await settle(app, pilot)
        assert app.current_tab.path.name == "page.html"
        await pilot.press("w"); await settle(app, pilot)
        assert len(app.tab_ids) == 1
    run(repo, body)


def test_md_rendered_then_raw(repo):
    _files(repo)
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "notes.md")
        assert tab.md_rendered and _shown(tab) == ["md"]
        assert "[그림: 구조]" in tab.shown_text
        await pilot.press("v"); await settle(app, pilot)
        assert not tab.md_rendered and _shown(tab) == ["code"]
    run(repo, body)


def test_html_title_and_o(repo, monkeypatch):
    _files(repo)
    browser, default = [], []
    monkeypatch.setattr(shellops, "open_browser", browser.append)
    monkeypatch.setattr(shellops, "open_default", default.append)
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "page.html")
        assert app.query_one("#tabs").get_tab(tab.id).label_text == "page.html ↗"
        await pilot.press("o"); await settle(app, pilot)
        assert browser == [repo / "page.html"]
        await _open(app, pilot, repo / "notes.md")
        await pilot.press("o"); await settle(app, pilot)
        assert default == [repo / "notes.md"]
    run(repo, body)


def test_binary_shows_notice(repo):
    _files(repo)
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "logo.png")
        assert tab.kind == "binary" and "미리 볼 수 없는 파일" in tab.notice
        assert _shown(tab) == ["notice"]
    run(repo, body)


def test_big_file_shown_without_highlight(repo, monkeypatch):
    _files(repo)
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "config.json")
        assert tab.highlighted is True
        monkeypatch.setattr(files, "BIG_FILE", 10)
        await pilot.press("w"); await settle(app, pilot)
        tab = await _open(app, pilot, repo / "config.json")
        assert tab.highlighted is False and _shown(tab) == ["code"]
    run(repo, body)


def test_tree_labels_mark_and_dim(repo):
    _files(repo)
    write(repo, ".gitignore", ".venv/\nbuild/\n")
    write(repo, ".venv/x", "x"); write(repo, "build/y", "y")
    async def body(app, pilot):
        tree = app.query_one("#tree", FileTree)
        await wait_until(lambda: tree.state is not None and len(tree.root.children) > 0, app, pilot)
        label = lambda name: tree.render_label(_node(tree, name), Style(), Style())
        assert label("config.json").plain.endswith(" M")
        # .venv 는 점 파일이라 Textual 이 이미 흐리게 한다. 점 없는 build 로 git 무시 흐림을 따로 본다.
        assert any("dim" in str(s.style) for s in label(".venv").spans)
        assert any("dim" in str(s.style) for s in label("build").spans)
        assert not any("dim" in str(s.style) for s in label("notes.md").spans)
    run(repo, body)


def test_narrow_hides_tree_and_t_switches(repo):
    _files(repo)
    async def body(app, pilot):
        tree, tabs = app.query_one("#tree"), app.query_one("#tabs")
        assert app.narrow and not tree.display and tabs.display
        await pilot.press("t"); await settle(app, pilot)
        assert tree.display and not tabs.display
        await _open(app, pilot, repo / "config.json")
        assert not tree.display and tabs.display
    run(repo, body, size=(60, 30))


def test_resize_switches_layout(repo):
    async def body(app, pilot):
        tree = app.query_one("#tree")
        assert tree.display
        await pilot.resize_terminal(60, 30); await settle(app, pilot)
        assert not tree.display
        await pilot.resize_terminal(120, 40); await settle(app, pilot)
        assert tree.display
    run(repo, body)


def test_t_and_brackets_in_wide(repo):
    async def body(app, pilot):
        tree = app.query_one("#tree")
        await pilot.press("]"); await settle(app, pilot)
        assert app.tree_width == 36
        for _ in range(6):
            await pilot.press("[")
        await settle(app, pilot)
        assert app.tree_width == 16
        await pilot.press("t"); await settle(app, pilot)
        assert not tree.display and not app.tree_shown
        await pilot.press("t"); await settle(app, pilot)
        assert tree.display
    run(repo, body)


async def _choose(app, pilot, option_id):
    ol = app.screen.query_one(OptionList)
    ol.highlighted = ol.get_option_index(option_id)
    await pilot.press("enter"); await settle(app, pilot)


def test_slash_finds_and_opens(repo):
    write(repo, "docs/design.md", "# 설계\n"); write(repo, "a.txt", "x\n")
    async def body(app, pilot):
        await pilot.press("slash"); await settle(app, pilot)
        assert isinstance(app.screen, CommandPalette)
        for ch in "desi":
            await pilot.press(ch)
        await wait_until(lambda: app.screen.query_one(CommandList).highlighted is not None, app, pilot, timeout=5)
        await pilot.press("enter")
        await wait_until(lambda: app.current_tab is not None, app, pilot)
        assert app.current_tab.path == repo / "docs" / "design.md"
    run(repo, body)


def test_m_menu_copy_path(repo, monkeypatch):
    _files(repo)
    copied = []
    monkeypatch.setattr(shellops, "copy_text", copied.append)
    async def body(app, pilot):
        await _open(app, pilot, repo / "config.json")
        app.current_tab.query_one("#body").focus()
        await pilot.press("m"); await settle(app, pilot)
        assert isinstance(app.screen, MenuScreen) and app.screen.path == repo / "config.json"
        await _choose(app, pilot, "copy")
        assert copied == [str(repo / "config.json")]
    run(repo, body)


def test_m_on_tree_uses_tree_cursor(repo, monkeypatch):
    _files(repo)
    revealed = []
    monkeypatch.setattr(shellops, "reveal", revealed.append)
    async def body(app, pilot):
        tree = app.query_one("#tree", FileTree)
        await wait_until(lambda: len(tree.root.children) > 0, app, pilot)
        tree.focus()
        tree.move_cursor(_node(tree, "config.json"))
        await pilot.press("m"); await settle(app, pilot)
        await _choose(app, pilot, "reveal")
        assert revealed == [repo / "config.json"]
    run(repo, body)


def test_right_click_on_tree_opens_menu_for_that_row(repo):
    # 루트에 .git, a.txt, b.txt 만 → 줄 0 루트, 1 .git, 2 a.txt
    write(repo, "a.txt", "a\n"); write(repo, "b.txt", "b\n")
    async def body(app, pilot):
        tree = app.query_one("#tree", FileTree)
        await wait_until(lambda: len(tree.root.children) == 3, app, pilot)
        await pilot.click(FileTree, offset=(4, 2), button=3); await settle(app, pilot)
        assert isinstance(app.screen, MenuScreen) and app.screen.path == repo / "a.txt"
        assert app.current_tab is None  # 우클릭이 파일을 열지 않는다
        await pilot.press("escape"); await settle(app, pilot)
        assert not isinstance(app.screen, MenuScreen)
    run(repo, body)


def test_right_click_on_tab_opens_menu_for_that_file(repo):
    _files(repo)
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "config.json")
        await _open(app, pilot, repo / "notes.md")
        await pilot.click(app.query_one("#tabs").get_tab(tab.id), button=3); await settle(app, pilot)
        assert isinstance(app.screen, MenuScreen) and app.screen.path == repo / "config.json"
    run(repo, body)


def _commit_a(repo):
    write(repo, "a.txt", "a\n"); git(repo, "add", "a.txt"); git(repo, "commit", "-m", "a")


async def _for(app, pilot, seconds):
    """seconds 동안 settle 을 반복한다(그 사이 폴링이 여러 번 돈다)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        await settle(app, pilot)
        await pilot.pause(0.05)


def test_open_tab_follows_external_edit(repo):
    _commit_a(repo)
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        write(repo, "a.txt", "AGENT\n")
        await wait_until(lambda: "AGENT" in app.current_tab.loaded.text, app, pilot)
    run(repo, body, poll_interval=0.1)


def test_refresh_keeps_scroll(repo):
    lines = "".join(f"line {i}\n" for i in range(200))
    write(repo, "long.txt", lines)
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "long.txt")
        scroll = tab.query_one("#body")
        scroll.scroll_to(y=50, animate=False); await settle(app, pilot)
        assert scroll.scroll_y == 50
        write(repo, "long.txt", lines.replace("line 150\n", "line 150 CHANGED\n"))
        await wait_until(lambda: "CHANGED" in tab.loaded.text, app, pilot)
        await settle(app, pilot)
        assert scroll.scroll_y == 50
    run(repo, body, poll_interval=0.1)


def test_new_file_gets_plus_and_does_not_steal_view(repo):
    _commit_a(repo)
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        tree = app.query_one("#tree", FileTree)
        write(repo, "new.txt", "x")
        def has_plus():
            n = next((n for n in tree.root.children if n.data.path.name == "new.txt"), None)
            return n is not None and tree.render_label(n, Style(), Style()).plain.endswith(" +")
        await wait_until(has_plus, app, pilot)
        assert app.current_tab.path == repo / "a.txt" and len(app.tab_ids) == 1
    run(repo, body, poll_interval=0.1)


def test_deleted_open_file_keeps_tab(repo):
    _commit_a(repo)
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        (repo / "a.txt").unlink()
        await wait_until(lambda: app.current_tab.deleted, app, pilot)
        assert "지워진 파일" in app.current_tab.notice and len(app.tab_ids) == 1
    run(repo, body, poll_interval=0.1)


def test_poll_survives_git_error(repo, monkeypatch):
    _commit_a(repo)
    calls = []
    def boom(root):
        calls.append(root)
        raise gitstate.GitError("index.lock")
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        monkeypatch.setattr(gitstate, "read_state", boom)
        await _for(app, pilot, 0.5)
        assert calls and app.is_running and len(app.tab_ids) == 1
    run(repo, body, poll_interval=0.1)


def test_poll_survives_unreadable_file(repo, monkeypatch):
    _commit_a(repo)
    calls = []
    def locked(path):
        calls.append(path)
        raise PermissionError("잠김")
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "a.txt")
        monkeypatch.setattr(files, "load", locked)
        p = repo / "a.txt"; st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        await _for(app, pilot, 0.5)
        assert calls and app.is_running and tab.loaded.text == "a\n"
    run(repo, body, poll_interval=0.1)
