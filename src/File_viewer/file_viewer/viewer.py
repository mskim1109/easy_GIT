"""탭 한 장: 파일 내용을 종류에 맞게 보여준다."""
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static, TabPane, TextArea

import file_viewer.files as files


class FileTab(TabPane):
    DEFAULT_CSS = """
    FileTab { height: 1fr; padding: 0; }
    FileTab #body { height: 1fr; overflow-x: auto; }
    FileTab #code { width: auto; }
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
            yield Static(id="code")
            yield Markdown(id="md")
            yield Static(id="notice")
        yield TextArea(id="editor", show_line_numbers=True, soft_wrap=False, tab_behavior="indent")

    def start_edit(self) -> bool:
        """편집 상태로. 편집할 수 없는 파일이면 False."""
        if self.loaded is None or not self.loaded.editable or self.loaded.binary or self.deleted:
            return False
        editor = self.query_one("#editor", TextArea)
        editor.load_text(self.loaded.text)  # md 도 원문으로 편집한다
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
            self.query_one("#md", Markdown).update(self.shown_text)
            self._show("md")
        else:
            self.shown_text = text
            # ponytail: Static 전체 렌더링. 수만 줄에서 느리면 render_line 기반 ScrollView로
            self.highlighted = (self.key[1] if self.key else len(text)) <= files.BIG_FILE
            renderable = (Syntax(text, Syntax.guess_lexer(str(self.path), text), line_numbers=True,
                                 word_wrap=False, theme="monokai")
                          if self.highlighted else Text(text))
            self.query_one("#code", Static).update(renderable)
            self._show("code")
        if keep_scroll:
            self.call_after_refresh(body.scroll_to, y=y, animate=False)
        else:
            body.scroll_home(animate=False)
