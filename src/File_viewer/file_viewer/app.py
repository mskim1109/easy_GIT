"""File_viewer 화면: 왼쪽 파일 트리 + 오른쪽 탭."""
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import ContentSwitcher, DirectoryTree, Footer, Static, TabbedContent, Tabs

import file_viewer.gitstate as gitstate
import file_viewer.shellops as shellops
from file_viewer.viewer import FileTab

MARK_COLOR = {"M": "#e2c08d", "•": "#e2c08d", "+": "#73c991"}


class FileTree(DirectoryTree):
    def __init__(self, root: Path, id: str = "tree"):
        super().__init__(root, id=id)
        self.root_path = Path(root)
        self.state: gitstate.GitState | None = None

    def rel(self, node) -> str:
        return "" if node is self.root else node.data.path.relative_to(self.root_path).as_posix()

    def render_label(self, node, base_style, style):
        label = super().render_label(node, base_style, style)
        if node.data is None:
            return label
        rel = self.rel(node)
        if gitstate.dimmed(self.state, rel):
            label.stylize("dim")
        m = gitstate.mark(self.state, rel, node.allow_expand)
        if m:
            label.append(f" {m}", style=MARK_COLOR[m])
        return label

    def set_state(self, state: gitstate.GitState | None) -> None:
        self.state = state
        self._clear_line_cache()
        self.refresh()


class FileViewerApp(App):
    CSS = """
    #tabs { width: 1fr; height: 1fr; }
    #tabs > ContentSwitcher { height: 1fr; }
    #empty { color: $text-muted; padding: 1 2; }
    """
    BINDINGS = [
        Binding("tab", "next_tab", "다음 탭", priority=True),
        Binding("shift+tab", "previous_tab", "이전 탭", priority=True, show=False),
        Binding("w", "close_tab", "탭 닫기"),
        Binding("v", "toggle_md", "md 보기"),
        Binding("o", "open_external", "열기"),
        Binding("q", "quit", "종료"),
    ]

    def __init__(self, root: Path, poll_interval: float = 1.0):
        super().__init__()
        self.root = root
        self.poll_interval = poll_interval
        self.tab_ids: dict[Path, str] = {}
        self._tab_no = 0
        self.tree_width = 32

    def compose(self) -> ComposeResult:
        with Horizontal():
            tree = FileTree(self.root)
            tree.styles.width = self.tree_width
            yield tree
            yield TabbedContent(id="tabs")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "nord"
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.mount(Static("왼쪽 트리에서 파일을 고르세요", id="empty"),
                   before=tabs.get_child_by_type(ContentSwitcher))
        self._load_state(self.query_one("#tree", FileTree))

    @work(thread=True, exclusive=True, group="git")
    def _load_state(self, tree: FileTree) -> None:
        try:
            state = gitstate.read_state(self.root)
        except gitstate.GitError:
            state = None
        self.call_from_thread(tree.set_state, state)

    @property
    def current_tab(self) -> FileTab | None:
        pane = self.query_one("#tabs", TabbedContent).active_pane
        return pane if isinstance(pane, FileTab) else None

    def open_file(self, path: Path) -> None:
        """이미 열려 있으면 그 탭으로, 아니면 새 탭을 연다."""
        new = path not in self.tab_ids
        if new:
            self._tab_no += 1
            self.tab_ids[path] = f"t{self._tab_no}"
        # 탭 붙이기는 비동기라 메시지 순서대로 처리되게 미룬다.
        self.call_later(self._show_tab, path, new)

    async def _show_tab(self, path: Path, new: bool) -> None:
        pane_id = self.tab_ids.get(path)
        if pane_id is None:  # 그 사이 닫힘
            return
        tabs = self.query_one("#tabs", TabbedContent)
        if new:
            await tabs.add_pane(FileTab(path, pane_id))
        tabs.active = pane_id
        self._update_empty()

    def _update_empty(self) -> None:
        self.query_one("#empty").display = not self.tab_ids

    def open_external(self, path: Path) -> None:
        try:
            if path.suffix.lower() in (".html", ".htm"):
                shellops.open_browser(path)
            else:
                shellops.open_default(path)
        except OSError as e:
            self.notify(f"열 수 없습니다: {e}", severity="error")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        event.stop()
        self.open_file(event.path)

    def action_next_tab(self) -> None:
        self.query_one("#tabs").query_one(Tabs).action_next_tab()

    def action_previous_tab(self) -> None:
        self.query_one("#tabs").query_one(Tabs).action_previous_tab()

    def action_close_tab(self) -> None:
        tab = self.current_tab
        if tab is None:
            return
        del self.tab_ids[tab.path]
        self.query_one("#tabs", TabbedContent).remove_pane(tab.id)
        self._update_empty()

    def action_toggle_md(self) -> None:
        if self.current_tab:
            self.current_tab.toggle_md()

    def action_open_external(self) -> None:
        if self.current_tab:
            self.open_external(self.current_tab.path)
