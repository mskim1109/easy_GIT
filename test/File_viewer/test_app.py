import asyncio

from rich.style import Style

import file_viewer.files as files
import file_viewer.shellops as shellops
from file_viewer.app import FileTree, FileViewerApp

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
