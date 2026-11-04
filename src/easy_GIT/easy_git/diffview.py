from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import Static

from easy_git.fulldiff import Row, SideRow, change_starts, side_rows

ADD = "on #2f4030"
DEL = "on #4a2c31"
FILL = "on #3b4252"

MARK = {"same": " ", "add": "+", "del": "-"}
STYLE = {"same": "", "add": ADD, "del": DEL}
SIDE_STYLE = {"same": ("", ""), "del": (DEL, FILL), "add": (FILL, ADD), "change": (DEL, ADD)}


def _text(lines: list[tuple[str, str, str]], cursor: int) -> Text:
    """(번호 칸, 나머지, 스타일) 줄들을 한 행 = 한 줄인 Text 로. 배경이 줄 끝까지 차도록 오른쪽을 채운다."""
    width = max(cell_len(rest) for _, rest, _ in lines)
    out = Text(no_wrap=True)
    for i, (no, rest, style) in enumerate(lines):
        if i:
            out.append("\n")
        out.append(no, "reverse" if i == cursor else style)
        out.append(rest + " " * (width - cell_len(rest)), style)
    return out


def _side(text: str | None) -> str:
    return "" if text is None else f" {text.expandtabs(4)}"


# ponytail: Static 전체 렌더링. 수만 줄에서 느리면 render_line 기반 ScrollView로
class DiffView(ScrollableContainer):
    DEFAULT_CSS = """
    DiffView Static { text-wrap: nowrap; text-overflow: clip; }
    DiffView > .unified { width: auto; }
    DiffView > Horizontal { height: auto; }
    DiffView > Horizontal > Static { width: 1fr; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.source: list[Row] | None = []
        self.rows: list[Row] | list[SideRow] | None = []
        self.mode = "unified"
        self.cursor_row = 0

    def compose(self) -> ComposeResult:
        yield Static(classes="unified")
        with Horizontal():
            yield Static(classes="old")
            yield Static(classes="new")

    def show(self, rows: list[Row] | None, mode: str, keep_scroll: bool = False) -> None:
        self.source, self.mode = rows, mode
        self.rows = side_rows(rows) if rows is not None and mode == "side" else rows
        y = self.scroll_y
        if not keep_scroll:
            starts = self._starts()
            self.cursor_row = starts[0] if starts else 0
            y = self._cursor_y()
        self._paint()
        self.call_after_refresh(self.scroll_to, y=y, animate=False)

    def set_mode(self, mode: str) -> None:
        self.show(self.source, mode)

    def next_change(self) -> None:
        later = [i for i in self._starts() if i > self.cursor_row]
        if later:
            self._move(later[0])

    def prev_change(self) -> None:
        earlier = [i for i in self._starts() if i < self.cursor_row]
        if earlier:
            self._move(earlier[-1])

    def _starts(self) -> list[int]:
        return change_starts([r.kind != "same" for r in self.rows or []])

    def _cursor_y(self) -> int:
        return max(0, self.cursor_row - self.size.height // 3)

    def _move(self, row: int) -> None:
        self.cursor_row = row
        self._paint()
        self.scroll_to(y=self._cursor_y(), animate=False)

    def _paint(self) -> None:
        unified = self.query_one(".unified", Static)
        side = self.query_one(Horizontal)
        side.display = bool(self.rows) and self.mode == "side"
        unified.display = not side.display
        if self.rows is None:
            unified.update(Text("바이너리 파일"))
        elif not self.rows:
            unified.update(Text("내용 변경 없음"))
        elif self.mode == "side":
            old = [(f"{s.left_no or '':>5}", _side(s.left), SIDE_STYLE[s.kind][0]) for s in self.rows]
            new = [(f"{s.right_no or '':>5}", _side(s.right), SIDE_STYLE[s.kind][1]) for s in self.rows]
            self.query_one(".old", Static).update(_text(old, self.cursor_row))
            self.query_one(".new", Static).update(_text(new, self.cursor_row))
        else:
            lines = [(f"{r.new_no or '':>5}", f" {MARK[r.kind]} {r.text.expandtabs(4)}", STYLE[r.kind]) for r in self.rows]
            unified.update(_text(lines, self.cursor_row))
