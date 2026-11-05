"""탭 한 장: 파일 내용을 종류에 맞게 보여준다."""
from pathlib import Path

from rich.cells import cell_len
from rich.markdown import Markdown as RichMarkdown
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.containers import VerticalScroll
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static, TabPane, TextArea

import file_viewer.files as files
from file_viewer.highlight import highlight_lines

NUMBER_STYLE = Style(color="#616e88")


def code_lines(text: str, path: Path, highlight: bool) -> list[str | Text]:
    """줄 목록. 강조하지 않으면 str 그대로 두고 그릴 때 Text 로 만든다(수 MB 도 즉시).
    강조는 easy_GIT 과 같은 VS Code Dark+ 색(highlight.py)."""
    body = text[:-1] if text.endswith("\n") else text
    if not highlight:
        return body.split("\n")
    return [Text.assemble(*parts) for parts in highlight_lines(body.split("\n"), str(path))]


class Lines(Widget):
    """보이는 줄만 그린다(Textual Line API). 큰 파일·긴 md 도 열 때와 새로 고칠 때 멈추지 않는다.

    Static 에 Syntax·Markdown 위젯을 통째로 넣으면 Textual 이 전체를 배치해 20KB 에 1초, 55KB md 에 7초가 걸렸다.
    """

    DEFAULT_CSS = """
    Lines { width: auto; height: auto; }
    Lines.wrap { width: 1fr; }
    """

    def __init__(self, id: str):
        super().__init__(id=id)
        self._lines: list[str | Text] = []
        self._width = self._gutter = 0
        self._md: RichMarkdown | None = None
        self._strips: list[Strip] = []
        self._md_width = -1

    def show_code(self, lines: list[str | Text]) -> None:
        for line in lines:
            if isinstance(line, Text) and "\t" in line.plain:
                line.expand_tabs(4)
        self._lines = [line.expandtabs(4) if isinstance(line, str) else line for line in lines]
        self._md = None
        self.remove_class("wrap")
        self._gutter = len(str(len(self._lines))) + 1
        self._width = self._gutter + max(
            (cell_len(line) if isinstance(line, str) else line.cell_len for line in self._lines), default=0)
        self.refresh(layout=True)

    def show_markdown(self, text: str) -> None:
        self._md, self._md_width = RichMarkdown(text), -1
        self.add_class("wrap")
        self.refresh(layout=True)

    def get_content_width(self, container, viewport) -> int:
        return container.width if self._md is not None else self._width

    def get_content_height(self, container, viewport, width: int) -> int:
        if self._md is None:
            return len(self._lines)
        if width != self._md_width:  # md 는 폭에 맞춰 줄을 접으므로 폭이 바뀔 때만 다시 그린다
            # ponytail: md 전체를 rich 로 한 번에 그림(55KB 문서 0.4초). 표 수백 개면 초 단위, 그때는 보이는 구간만
            console = self.app.console
            self._strips = [Strip(line) for line in console.render_lines(self._md, console.options.update_width(width))]
            self._md_width = width
        return len(self._strips)

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if self._md is not None:
            return self._strips[y].extend_cell_length(width) if y < len(self._strips) else Strip.blank(width)
        if y >= len(self._lines):
            return Strip.blank(width)
        line = self._lines[y]
        text = Text(line) if isinstance(line, str) else line
        number = Segment(f"{y + 1:>{self._gutter - 1}} ", NUMBER_STYLE)
        return Strip([number, *text.render(self.app.console)]).extend_cell_length(width)


class FileTab(TabPane):
    DEFAULT_CSS = """
    FileTab { height: 1fr; padding: 0; }
    /* 스크롤바 자리를 늘 잡아 두어 md 를 폭 하나로 한 번만 그린다(생기는 순간 폭이 바뀌면 두 번 그림) */
    FileTab #body { height: 1fr; overflow-x: auto; scrollbar-gutter: stable; }
    FileTab #notice { padding: 1 2; }
    FileTab #editor { display: none; height: 1fr; }
    """

    def __init__(self, path: Path, pane_id: str):
        html = path.suffix.lower() in (".html", ".htm")
        super().__init__(path.name + (" ↗" if html else ""), id=pane_id)
        self.path = path
        self.loaded: files.Loaded | None = None
        self.kind: files.Kind = "code"
        self.key: tuple[int, int] | None = None
        self.md_rendered = path.suffix.lower() in (".md", ".markdown")
        self.deleted = False
        self.editing = False
        self.edit_key: tuple[int, int] | None = None
        self.highlighted = False
        self.notice: str | None = None
        self.shown_text = ""

    def compose(self):
        # 내용 위젯은 하나씩만 두고 보이기만 바꾼다(같은 id 를 지우고 다시 붙이면 Textual 이 충돌).
        with VerticalScroll(id="body"):
            yield Lines(id="code")
            yield Lines(id="md")
            yield Static(id="notice")
        yield TextArea(id="editor", show_line_numbers=True, soft_wrap=False, tab_behavior="indent")

    def start_edit(self) -> bool:
        """편집 상태로. 편집할 수 없는 파일이면 False."""
        if self.loaded is None or not self.loaded.editable or self.loaded.binary or self.deleted:
            return False
        editor = self.query_one("#editor", TextArea)
        editor.load_text(self.loaded.text)  # md 도 원문으로 편집한다
        if editor.text != self.loaded.text:
            # TextArea 는 \x0c·\x0b·U+2028·홀로 있는 \r 등도 줄바꿈으로 나눈다. 저장하면 내용이 바뀌므로 거절한다.
            return False
        # 기준은 편집 칸에 넣은 내용을 읽었을 때의 상태다. 그 뒤 디스크가 바뀌었으면 저장 때 묻는다.
        self.editing, self.edit_key = True, self.key
        self.query_one("#body").display = False
        editor.display = True
        editor.focus()
        return True

    def is_dirty(self) -> bool:
        return self.editing and self.query_one("#editor", TextArea).text != self.loaded.text

    def write_file(self) -> None:
        files.save(self.path, self.query_one("#editor", TextArea).text, self.loaded)
        self.loaded = files.load(self.path)
        self.key = self.edit_key = files.stat_key(self.path)

    def stop_edit(self) -> None:
        """보기 상태로 돌아가 디스크 내용을 다시 읽는다."""
        self.editing = False
        self.query_one("#editor").display = False
        body = self.query_one("#body")
        body.display = True
        body.focus()
        try:
            self.refresh_content()
        except OSError as e:
            self.show_notice(f"읽을 수 없습니다: {e}")

    def on_mount(self) -> None:
        try:
            self.refresh_content()
        except OSError as e:  # 에이전트가 쓰는 중이면 다음 확인 때 다시 읽는다.
            self.show_notice(f"읽을 수 없습니다: {e}")

    def refresh_content(self, keep_scroll: bool = False) -> None:
        """디스크에서 다시 읽어 그린다. OSError 는 그대로 올린다."""
        key = files.stat_key(self.path)  # 읽기 전에 잡아야 읽는 사이 바뀐 것을 다음에 놓치지 않는다
        loaded = files.load(self.path)
        self.key, self.loaded, self.kind, self.deleted = key, loaded, files.kind_of(self.path, loaded), False
        self._draw(keep_scroll)

    def toggle_md(self) -> None:
        if self.kind != "md" or self.loaded is None:
            return
        self.md_rendered = not self.md_rendered
        self._draw(False)

    def show_notice(self, text: str) -> None:
        self.notice = text
        self.query_one("#notice", Static).update(text)
        self._show("notice")

    def _show(self, which: str) -> None:
        for child in self.query_one("#body").children:
            child.display = child.id == which

    def _draw(self, keep_scroll: bool) -> None:
        body = self.query_one("#body", VerticalScroll)
        y = body.scroll_y
        text = self.loaded.text
        if self.kind == "binary":
            self.show_notice("미리 볼 수 없는 파일입니다 — o 로 기본 프로그램에서 엽니다")
        elif self.kind == "md" and self.md_rendered:
            self.shown_text = files.md_for_view(text)
            self.query_one("#md", Lines).show_markdown(self.shown_text)
            self._show("md")
        else:
            self.shown_text = text
            self.highlighted = (self.key[1] if self.key else len(text)) <= files.BIG_FILE
            self.query_one("#code", Lines).show_code(code_lines(text, self.path, self.highlighted))
            self._show("code")
        if keep_scroll:
            self.call_after_refresh(body.scroll_to, y=y, animate=False)
        else:
            body.scroll_home(animate=False)
