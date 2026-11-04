from __future__ import annotations

from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

from easy_git.fulldiff import Row, SideRow, change_starts, side_rows
from easy_git.highlight import DEFAULT, Line, highlight_lines

ADD = "on #2f4030"
DEL = "on #4a2c31"
FILL = "on #3b4252"

MARK = {"same": " ", "add": "+", "del": "-"}
STYLE = {"same": "", "add": ADD, "del": DEL}
SIDE_STYLE = {"same": ("", ""), "del": (DEL, FILL), "add": (FILL, ADD), "change": (DEL, ADD)}
REVERSE = Style.parse("reverse")

# 한 칸: (번호, 색을 입힌 글 조각들, 배경 스타일). 파일을 띄울 때 한 번 만들고, 그릴 때는 자르기만 한다.
Cell = tuple[str, list[Segment], Style]


def _cell(no: str, parts: Line, bg: str) -> Cell:
    back = Style.parse(bg) if bg else Style()
    return no, [Segment(text, Style(color=color) + back) for text, color in parts], back


def _strip(cell: Cell, width: int, cursor: bool, scroll_x: int = 0) -> Strip:
    """한 칸을 width 너비로. 번호는 고정, 글은 scroll_x 만큼 밀고, 배경은 끝까지 채운다."""
    no, segments, back = cell
    head = Segment(no, REVERSE if cursor else back)
    body = Strip(segments).crop(scroll_x, scroll_x + max(0, width - cell_len(no)))
    return Strip([head, *body]).extend_cell_length(width, back).crop(0, width)


Colors = tuple[dict[int, Line], dict[int, Line]]


def colored(rows: list[Row], path: str) -> Colors:
    """이전 파일·이후 파일을 각각 통째로 색칠해 줄 번호 → 조각으로. (여러 줄 문자열·주석이 어긋나지 않게)
    큰 파일은 0.5초 넘게 걸리니 화면 스레드가 아닌 곳(worker)에서 불러 show(colors=...) 로 넘긴다."""
    old = {r.old_no: r.text.expandtabs(4) for r in rows if r.old_no}
    new = {r.new_no: r.text.expandtabs(4) for r in rows if r.new_no}
    result = []
    for side in (old, new):
        nos = sorted(side)
        result.append(dict(zip(nos, highlight_lines([side[n] for n in nos], path))))
    return result[0], result[1]


class DiffView(ScrollView):
    """파일 전체 diff. 화면에 보이는 줄만 그때그때 그린다 (큰 파일·안내선이 지나갈 때도 가볍게)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.source: list[Row] | None = []
        self.rows: list[Row] | list[SideRow] | None = []
        self.mode = "unified"
        self.cursor_row = 0
        self.path = ""  # 확장자로 언어를 정해 색을 입힌다
        self._colors: Colors | None = None  # source 를 칠한 결과. 보기 전환(v) 때 다시 쓴다
        self._cells: list[Cell] | list[tuple[Cell, Cell]] = []

    def show(self, rows: list[Row] | None, mode: str, keep_scroll: bool = False,
             path: str | None = None, colors: Colors | None = None) -> None:
        if colors is not None:
            self._colors = colors
        elif rows is not self.source or (path is not None and path != self.path):
            self._colors = None  # 새 내용인데 색을 안 받았다: _build 에서 칠한다
        if path is not None:
            self.path = path
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
            self._cells = [_cell("", [("바이너리 파일" if self.rows is None else "내용 변경 없음", DEFAULT)], "")]
            return self._finish(0)
        if self._colors is None:
            self._colors = colored(self.source, self.path)
        old, new = self._colors
        if self.mode == "side":
            gap = [(" ", DEFAULT)]
            self._cells = [
                (_cell(f"{s.left_no or '':>5}", gap + old[s.left_no] if s.left_no else [], SIDE_STYLE[s.kind][0]),
                 _cell(f"{s.right_no or '':>5}", gap + new[s.right_no] if s.right_no else [], SIDE_STYLE[s.kind][1]))
                for s in self.rows
            ]
            width = 0  # 좌우 보기는 가로 스크롤 없이 반씩 자른다
        else:
            self._cells = [
                _cell(f"{r.new_no or '':>5}", [(f" {MARK[r.kind]} ", DEFAULT)] + (new[r.new_no] if r.new_no else old[r.old_no]), STYLE[r.kind])
                for r in self.rows
            ]
            width = max(cell_len(no) + sum(s.cell_length for s in segs) for no, segs, _ in self._cells)
        self._finish(width)

    def _finish(self, width: int) -> None:
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
