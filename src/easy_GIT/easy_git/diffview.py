from __future__ import annotations

from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

from easy_git.fulldiff import Row, SideRow, change_starts, side_rows

ADD = "on #2f4030"
DEL = "on #4a2c31"
FILL = "on #3b4252"

MARK = {"same": " ", "add": "+", "del": "-"}
STYLE = {"same": "", "add": ADD, "del": DEL}
SIDE_STYLE = {"same": ("", ""), "del": (DEL, FILL), "add": (FILL, ADD), "change": (DEL, ADD)}

# 한 칸: (번호, 나머지 글, 스타일)
Cell = tuple[str, str, str]


def _side(text: str | None) -> str:
    return "" if text is None else f" {text.expandtabs(4)}"


def _strip(cell: Cell, width: int, cursor: bool, scroll_x: int = 0) -> Strip:
    """한 칸을 width 너비로. 번호는 고정, 글은 scroll_x 만큼 밀고, 배경은 끝까지 채운다."""
    no, rest, style = cell
    s = Style.parse(style) if style else Style()
    head = Segment(no, Style.parse("reverse") if cursor else s)
    body = Strip([Segment(rest, s)]).crop(scroll_x, scroll_x + max(0, width - cell_len(no)))
    return Strip([head, *body]).extend_cell_length(width, s).crop(0, width)


class DiffView(ScrollView):
    """파일 전체 diff. 화면에 보이는 줄만 그때그때 그린다 (큰 파일·안내선이 지나갈 때도 가볍게)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.source: list[Row] | None = []
        self.rows: list[Row] | list[SideRow] | None = []
        self.mode = "unified"
        self.cursor_row = 0
        self._cells: list[Cell] | list[tuple[Cell, Cell]] = []

    def show(self, rows: list[Row] | None, mode: str, keep_scroll: bool = False) -> None:
        self.source, self.mode = rows, mode
        self.rows = side_rows(rows) if rows is not None and mode == "side" else rows
        y = self.scroll_y
        if not keep_scroll:
            starts = self._starts()
            self.cursor_row = starts[0] if starts else 0
            y = self._cursor_y()
        self._build()
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
        self.refresh()
        self.scroll_to(y=self._cursor_y(), animate=False)

    def _build(self) -> None:
        if not self.rows:
            self._cells = [("", "바이너리 파일" if self.rows is None else "내용 변경 없음", "")]
            width = 0
        elif self.mode == "side":
            self._cells = [
                ((f"{s.left_no or '':>5}", _side(s.left), SIDE_STYLE[s.kind][0]),
                 (f"{s.right_no or '':>5}", _side(s.right), SIDE_STYLE[s.kind][1]))
                for s in self.rows
            ]
            width = 0  # 좌우 보기는 가로 스크롤 없이 반씩 자른다
        else:
            self._cells = [(f"{r.new_no or '':>5}", f" {MARK[r.kind]} {r.text.expandtabs(4)}", STYLE[r.kind]) for r in self.rows]
            width = max(cell_len(no) + cell_len(rest) for no, rest, _ in self._cells)
        self.virtual_size = Size(width, len(self._cells))
        self.refresh()

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        i, width = scroll_y + y, self.size.width
        if i >= len(self._cells):
            return Strip.blank(width)
        cursor = bool(self.rows) and i == self.cursor_row
        if self.mode == "side" and self.rows:
            left, right = self._cells[i]
            half = width // 2
            return Strip.join([_strip(left, half, cursor), _strip(right, width - half, cursor)])
        return _strip(self._cells[i], width, cursor, scroll_x)
