import asyncio

from textual.app import App

from easy_git.diffview import DiffView
from easy_git.fulldiff import Row
from easy_git.highlight import CLASS, COMMENT, CONTROL, DEFAULT, FUNCTION, KEYWORD, NUMBER, STRING, VARIABLE, highlight_lines


def color_of(line, word):
    """그 줄에서 word 로 시작하는 첫 조각의 색."""
    return next(color for text, color in line if text.startswith(word))


def test_python_tokens_get_dark_plus_colors():
    def_line, ret_line, call_line, class_line = highlight_lines(
        ["def f(x):  # 주석", "    return print('a', 1)", "foo(2)", "class Box:"], "app.py")
    assert (color_of(def_line, "def"), color_of(def_line, "f"), color_of(def_line, "x"), color_of(def_line, "# 주석")) \
        == (KEYWORD, FUNCTION, VARIABLE, COMMENT)
    assert (color_of(ret_line, "return"), color_of(ret_line, "print"), color_of(ret_line, "1")) == (CONTROL, FUNCTION, NUMBER)
    assert {c for t, c in ret_line if t in ("'", "a")} == {STRING}
    assert color_of(call_line, "foo") == FUNCTION  # 괄호가 붙은 이름은 호출이라 함수 색
    assert color_of(class_line, "Box") == CLASS


def test_multiline_string_keeps_each_line_aligned():
    lines = highlight_lines(['x = """a', 'b"""', "y = 1"], "m.py")
    assert len(lines) == 3
    assert {c for _, c in lines[1]} == {STRING}
    assert color_of(lines[2], "y") == VARIABLE


def test_text_is_unchanged_and_unknown_extension_is_plain():
    src = ["\tindent(1)", "", "끝"]
    assert ["".join(t for t, _ in line) for line in highlight_lines(src, "a.py")] == src
    assert highlight_lines(["hello world"], "notes.unknownext") == [[("hello world", DEFAULT)]]


def test_coloring_runs_off_the_screen_thread(repo, monkeypatch):
    # 큰 파일은 색칠에 0.5초 넘게 걸린다. 화면 스레드에서 하면 그동안 화면이 멈춘다.
    import threading
    from easy_git import diffview
    from easy_git.app import EasyGitApp
    from conftest import git, write
    from test_app import settle

    write(repo, "a.py", "x = 1\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "a.py", "x = 2\n")
    threads = []
    real = diffview.highlight_lines
    monkeypatch.setattr(diffview, "highlight_lines", lambda lines, path: (threads.append(threading.current_thread()), real(lines, path))[1])

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            await pilot.press("v"); await settle(app, pilot)  # 보기 전환은 이미 칠한 색을 다시 쓴다
            assert app.query_one(DiffView).mode == "side"

    asyncio.run(run())
    assert threads and threading.main_thread() not in threads


def test_diff_view_colors_code_and_keeps_line_background():
    rows = [Row("same", 1, 1, "def f():"), Row("add", None, 2, "    return 1")]

    class T(App):
        def compose(self):
            yield DiffView()

    async def run():
        app = T()
        async with app.run_test(size=(80, 10)) as pilot:
            diff = app.query_one(DiffView)
            diff.show(rows, "unified", path="a.py"); await pilot.pause()
            segs = {s.text.strip(): s.style for s in diff.render_line(1) if s.text.strip()}
            assert segs["return"].color.name.lower() == CONTROL.lower()
            assert segs["return"].bgcolor is not None  # 추가된 줄의 초록 배경은 그대로
            first = {s.text.strip(): s.style for s in diff.render_line(0) if s.text.strip()}
            assert first["f"].color.name.lower() == FUNCTION.lower()

    asyncio.run(run())
