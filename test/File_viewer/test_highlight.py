from pathlib import Path

from file_viewer.highlight import CLASS, COMMENT, CONTROL, DEFAULT, FUNCTION, KEYWORD, NUMBER, STRING, VARIABLE, highlight_lines
from file_viewer.viewer import code_lines


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


def test_code_lines_use_dark_plus_colors_without_background():
    lines = code_lines("def f():\n\n    return 1\n", Path("a.py"), highlight=True)
    assert [line.plain for line in lines] == ["def f():", "", "    return 1"]
    spans = {lines[2].plain[s.start:s.end]: s.style for s in lines[2].spans}
    assert spans["return"] == CONTROL  # monokai 가 아니라 VS Code Dark+ 색, 배경 없음
