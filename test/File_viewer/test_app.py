import asyncio
import subprocess
import sys
import os
import shutil
import time

import pytest
from rich.style import Style

import file_viewer.files as files
import file_viewer.gitstate as gitstate
import file_viewer.herdr_right as herdr_right
import file_viewer.shellops as shellops
import file_viewer.viewer as viewer
from textual.command import CommandList, CommandPalette
from textual.widgets import OptionList, Static, TextArea

from file_viewer.app import ConfirmScreen, FileTree, FileViewerApp, MenuScreen

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


def test_md_mermaid_chart_drawn_under_code_off_screen_thread(repo, monkeypatch):
    import threading
    threads = []
    def fake(src):
        threads.append(threading.current_thread())
        return "<<CHART " + src.splitlines()[0] + ">>"
    monkeypatch.setattr(viewer, "CHARTS", {})
    monkeypatch.setattr(viewer, "draw_mermaid", fake)
    write(repo, "d.md", "# 제목\n\n```mermaid\ngraph LR\nA --> B\n```\n\n끝\n")
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "d.md")
        md = tab.query_one("#md")
        await wait_until(lambda: any("<<CHART graph LR>>" in s.text for s in md._strips), app, pilot)
        texts = [s.text.strip() for s in md._strips]
        code = next(i for i, t in enumerate(texts) if t.startswith("A --> B"))
        chart = next(i for i, t in enumerate(texts) if "<<CHART" in t)
        assert code < chart < texts.index("끝")  # 코드 바로 밑, 다음 문단 위
        await pilot.press("v"); await settle(app, pilot)  # 원문 보기에는 그림이 없다
        assert not any("<<CHART" in str(line) for line in tab.query_one("#code")._lines)
    run(repo, body)
    assert threads and threading.main_thread() not in threads  # 0.4초씩 걸려 화면 스레드에서 그리면 멈춘다


def test_draw_mermaid_without_program_says_so(monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert "mermaid-ascii" in viewer.draw_mermaid("graph LR\nA --> B")


@pytest.mark.skipif(not shutil.which("mermaid-ascii"), reason="mermaid-ascii 가 PATH 에 없음")
def test_draw_mermaid_real_program():
    chart = viewer.draw_mermaid("graph LR\nA[시작] -->|예| B[끝]")
    assert "시작" in chart and "예" in chart and "┌" in chart
    assert "그릴 수 없는" in viewer.draw_mermaid("pie\n\"a\" : 1")


def test_follow_moves_tree_to_focused_pane_folder_and_keeps_tabs(repo, tmp_path, monkeypatch):
    other = tmp_path / "다른칸"
    write(other, "b.txt", "b\n"); write(repo, "a.txt", "a\n")
    focused = [repo]
    monkeypatch.setattr(herdr_right, "focused_cwd", lambda: focused[0])
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        tree = app.query_one("#tree", FileTree)
        focused[0] = other  # 사용자가 다른 칸으로 옮겨 갔다
        await wait_until(lambda: app.root == other.resolve()
                         and any(n.data.path.name == "b.txt" for n in tree.root.children), app, pilot)
        assert app.current_tab.path == repo / "a.txt"  # 열린 탭은 그대로
    run(repo, body, poll_interval=0.05, follow=True)


def test_without_follow_does_not_ask_herdr(repo, monkeypatch):
    asked = []
    monkeypatch.setattr(herdr_right, "focused_cwd", lambda: asked.append(1))
    write(repo, "a.txt", "a\n")
    async def body(app, pilot):
        for _ in range(5):
            await settle(app, pilot); await pilot.pause(0.06)
        assert app.root == repo
    run(repo, body, poll_interval=0.05)
    assert not asked


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


def test_poll_while_closing_is_harmless(repo):
    # 앱이 닫히는 중(위젯이 지워진 뒤)에 타이머가 한 번 더 돌아도 앱이 오류로 끝나지 않는다.
    async def body(app, pilot):
        await app.query_one("#tree").remove()
        app.poll_once()
        await settle(app, pilot)
        assert app.is_running
    run(repo, body)


def _editor(app):
    return app.current_tab.query_one("#editor", TextArea)


async def _edit(app, pilot, path):
    await _open(app, pilot, path)
    await pilot.press("e"); await settle(app, pilot)
    return _editor(app)


def test_edit_save_keeps_cp949_and_crlf(repo):
    write(repo, "a.txt", "가\r\n나\r\n".encode("cp949"))
    async def body(app, pilot):
        ed = await _edit(app, pilot, repo / "a.txt")
        assert app.current_tab.editing and ed.has_focus
        ed.text = "가\n다\n"
        await pilot.press("ctrl+s"); await settle(app, pilot)
        assert (repo / "a.txt").read_bytes() == "가\r\n다\r\n".encode("cp949")
    run(repo, body)


def test_save_asks_before_overwriting_external_change(repo):
    write(repo, "a.txt", "a\n")
    async def body(app, pilot):
        ed = await _edit(app, pilot, repo / "a.txt")
        ed.text = "MINE\n"
        write(repo, "a.txt", "AGENT\n")
        await pilot.press("ctrl+s"); await settle(app, pilot)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n"); await settle(app, pilot)
        assert (repo / "a.txt").read_bytes() == b"AGENT\n"
        await pilot.press("ctrl+s"); await settle(app, pilot)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y"); await settle(app, pilot)
        assert (repo / "a.txt").read_bytes() == b"MINE\n"
    run(repo, body)


def test_edit_of_stale_view_still_asks_before_overwrite(repo):
    # 보던 내용이 낡았을 때(폴링 전에 에이전트가 고침) e → 저장하면, 편집 칸 내용 이후에 바뀐 것이므로 묻는다.
    write(repo, "a.txt", "a\n")
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        write(repo, "a.txt", "AGENT\n")
        await pilot.press("e"); await settle(app, pilot)
        ed = _editor(app)
        assert ed.text == "a\n"
        ed.text = "MINE\n"
        await pilot.press("ctrl+s"); await settle(app, pilot)
        assert isinstance(app.screen, ConfirmScreen)
        assert (repo / "a.txt").read_bytes() == b"AGENT\n"
    run(repo, body, poll_interval=60)


def test_escape_with_unsaved_changes_asks(repo):
    write(repo, "a.txt", "a\n")
    async def body(app, pilot):
        ed = await _edit(app, pilot, repo / "a.txt")
        ed.text = "changed\n"
        await pilot.press("escape"); await settle(app, pilot)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y"); await settle(app, pilot)
        assert not app.current_tab.editing
        assert (repo / "a.txt").read_bytes() == b"a\n"
    run(repo, body)


def test_close_tab_and_quit_with_unsaved_changes_ask(repo):
    # 편집 중에는 w·q 가 글자로 들어가므로 액션을 직접 부른다
    write(repo, "a.txt", "a\n")
    async def body(app, pilot):
        ed = await _edit(app, pilot, repo / "a.txt")
        ed.text = "x\n"
        app.action_close_tab(); await settle(app, pilot)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n"); await settle(app, pilot)
        assert len(app.tab_ids) == 1
        await app.action_quit(); await settle(app, pilot)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n"); await settle(app, pilot)
        assert app.is_running
    run(repo, body)


def test_editing_keys_go_to_editor(repo):
    write(repo, "a.txt", "a\n"); write(repo, "b.txt", "b\n")
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        ed = await _edit(app, pilot, repo / "b.txt")
        await pilot.press("tab"); await settle(app, pilot)
        assert app.current_tab.path == repo / "b.txt"
        assert ed.text != "b\n" and ed.text.strip() == "b"
        await pilot.press("q"); await settle(app, pilot)
        assert app.is_running and "q" in ed.text
    run(repo, body)


def test_ctrl_e_starts_edit_even_with_korean_ime(repo):
    # 한글 입력 상태에서는 e 가 'ㄷ' 조합으로 먹혀 앱에 오지 않는다. Ctrl 조합은 입력기가 건드리지 않는다.
    write(repo, "a.txt", "a\n")
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        await pilot.press("ctrl+e"); await settle(app, pilot)
        assert app.current_tab.editing
    run(repo, body)


def test_editing_tab_not_auto_refreshed(repo):
    write(repo, "a.txt", "a\n")
    async def body(app, pilot):
        ed = await _edit(app, pilot, repo / "a.txt")
        ed.text = "MINE\n"
        write(repo, "a.txt", "AGENT\n")
        await _for(app, pilot, 0.5)
        assert ed.text == "MINE\n"
    run(repo, body, poll_interval=0.1)


def test_not_editable_file_refuses(repo):
    write(repo, "x.txt", b"ok \xff\xfe\xfa\n"); write(repo, "logo.png", b"\x89PNG\x00\x00")
    async def body(app, pilot):
        await _open(app, pilot, repo / "x.txt")
        await pilot.press("e"); await settle(app, pilot)
        assert not app.current_tab.editing
        await _open(app, pilot, repo / "logo.png")
        await pilot.press("e"); await settle(app, pilot)
        assert not app.current_tab.editing
    run(repo, body)


def test_save_unencodable_char_keeps_file(repo):
    # CP949 로 쓸 수 없는 글자를 넣고 저장해도 앱이 살아 있고 파일은 그대로다.
    write(repo, "a.txt", "가\r\n".encode("cp949"))
    async def body(app, pilot):
        ed = await _edit(app, pilot, repo / "a.txt")
        ed.text = "😀\n"
        await pilot.press("ctrl+s"); await settle(app, pilot)
        assert app.is_running and (repo / "a.txt").read_bytes() == "가\r\n".encode("cp949")
    run(repo, body)


def test_priority_keys_under_modal_do_not_touch_main_screen(repo):
    # Tab·Esc 는 priority 바인딩이라 창이 떠 있어도 앱까지 온다. 뒤의 탭을 바꾸거나 편집을 끝내면 안 된다.
    write(repo, "a.txt", "a\n"); write(repo, "b.txt", "b\n")
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        await _open(app, pilot, repo / "b.txt")
        app.current_tab.query_one("#body").focus()
        await pilot.press("m"); await settle(app, pilot)
        assert isinstance(app.screen, MenuScreen)
        await pilot.press("tab"); await settle(app, pilot)
        assert app.current_tab.path == repo / "b.txt"
        await pilot.press("escape"); await settle(app, pilot)
        ed = await _edit(app, pilot, repo / "b.txt")
        ed.text = "MINE\n"
        write(repo, "b.txt", "AGENT\n")
        await pilot.press("ctrl+s"); await settle(app, pilot)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("escape"); await settle(app, pilot)  # 확인 창의 "아니요"
        assert not isinstance(app.screen, ConfirmScreen) and app.current_tab.editing
        assert (repo / "b.txt").read_bytes() == b"AGENT\n"
    run(repo, body)


def test_empty_hint_matches_layout(repo):
    # 좁으면 왼쪽 트리가 숨어 있으므로 안내도 t 키를 말한다.
    async def body(app, pilot):
        hint = app.query_one("#empty", Static)
        assert "t" in str(hint.content) and "왼쪽" not in str(hint.content)
        await pilot.resize_terminal(120, 40); await settle(app, pilot)
        assert "왼쪽 트리" in str(hint.content)
    run(repo, body, size=(52, 30))


def test_medium_and_big_files_do_not_freeze(repo):
    # 리뷰 실측: 200KB .py 8초, 55KB md 7초, 5MB 로그 6~13초 멈춤. 열기와 다시 그리기 모두 1.5초 안이어야 한다.
    py = "def f(x):\n    return x * 2  # 주석 가나다\n\n"
    write(repo, "mid.py", py * (90_000 // len(py.encode())))  # 강조 기준(100KB) 바로 아래
    # 설계·계획 문서와 비슷한 55KB md: 문단·목록·코드 블록, 표는 가끔
    md = "".join(f"## 절 {i}\n\n" + "설명 문장입니다. " * 20 + "\n\n- 항목 가\n- 항목 나\n\n```python\nx = {i}\n```\n\n"
                 + ("| a | b |\n|---|---|\n| 1 | 2 |\n\n" if i % 10 == 0 else "") for i in range(90))
    write(repo, "doc.md", md)
    line = "2026-11-04 12:00:00.000 INFO  [worker-3] 요청 처리 id=0123456789 status=ok\n"
    write(repo, "big.log", line * (5_000_000 // len(line.encode())))
    async def body(app, pilot):
        for name in ["mid.py", "doc.md", "big.log"]:
            t = time.perf_counter()
            tab = await _open(app, pilot, repo / name)
            await pilot.pause(); await pilot.pause()
            assert (took := time.perf_counter() - t) < 1.5, f"{name} 열기 {took:.1f}s"
            t = time.perf_counter()
            tab.refresh_content(True)  # 에이전트가 고칠 때마다 타는 경로
            await pilot.pause(); await pilot.pause()
            assert (took := time.perf_counter() - t) < 1.5, f"{name} 다시 그리기 {took:.1f}s"
        assert app.query_one("#tabs").get_pane(app.tab_ids[repo / "mid.py"]).highlighted
    run(repo, body, poll_interval=3600)


def test_edit_refuses_text_the_editor_would_change(repo):
    # TextArea 는 \x0c·U+2028 등도 줄바꿈으로 나눠 저장 때 내용이 바뀐다. 그런 파일은 편집을 거절한다.
    original = b'a = 1\n\x0c\nb = "\xe2\x80\xa8"\n'
    write(repo, "a.py", original)
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.py")
        await pilot.press("e"); await settle(app, pilot)
        assert not app.current_tab.editing
        assert (repo / "a.py").read_bytes() == original
    run(repo, body)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 정션")
def test_junction_to_outside_root_does_not_crash(repo, tmp_path):
    write(tmp_path, "outside/x.txt", "x\n")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(repo / "link"), str(tmp_path / "outside")],
                   check=True, capture_output=True)
    async def body(app, pilot):
        tree = app.query_one("#tree", FileTree)
        await wait_until(lambda: any(n.data.path.name == "link" for n in tree.root.children), app, pilot)
        node = _node(tree, "link")
        node.expand()
        await wait_until(lambda: len(node.children) > 0, app, pilot)
        tree.render_label(node.children[0], Style(), Style())
        await _open(app, pilot, node.children[0].data.path)
        (tmp_path / "outside" / "x.txt").unlink()
        await wait_until(lambda: app.current_tab.deleted, app, pilot)
        assert app.is_running
    run(repo, body, poll_interval=0.1)


def test_narrow_open_focuses_content_for_keyboard_scroll(repo):
    write(repo, "long.txt", "".join(f"line {i}\n" for i in range(200)))
    async def body(app, pilot):
        tab = await _open(app, pilot, repo / "long.txt")
        scroll = tab.query_one("#body")
        await pilot.press("pagedown"); await settle(app, pilot)
        assert scroll.scroll_y > 0
        scroll.scroll_home(animate=False)
        await pilot.press("t"); await pilot.press("t"); await settle(app, pilot)  # 트리 화면 → 내용 화면
        await pilot.press("pagedown"); await settle(app, pilot)
        assert scroll.scroll_y > 0
    run(repo, body, size=(60, 30))


def test_poll_survives_unexpected_stat_error(repo, monkeypatch):
    _commit_a(repo)
    calls = []
    def denied(path):
        calls.append(path)
        raise PermissionError("거부")
    async def body(app, pilot):
        await _open(app, pilot, repo / "a.txt")
        monkeypatch.setattr(files, "stat_key", denied)
        await _for(app, pilot, 0.5)
        assert calls and app.is_running
    run(repo, body, poll_interval=0.1)
