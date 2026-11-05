"""File_viewer 화면: 왼쪽 파일 트리 + 오른쪽 탭."""
import asyncio
import os
import subprocess
from functools import partial
from pathlib import Path

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import CommandPalette, Hit, Hits, Provider
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import ContentSwitcher, DirectoryTree, Footer, OptionList, Static, TabbedContent, Tabs
from textual.widgets.option_list import Option

import file_viewer.files as files
import file_viewer.gitstate as gitstate
import file_viewer.herdr_right as herdr_right
import file_viewer.shellops as shellops
from file_viewer.viewer import FileTab

MARK_COLOR = {"M": "#e2c08d", "•": "#e2c08d", "+": "#73c991"}
# ponytail: 기준 80열은 짐작. 실제 Herdr 칸에서 보고 조정
NARROW_BELOW = 80  # 이보다 좁으면 트리를 숨기고 t 로 트리 화면 ↔ 내용 화면
TREE_MIN = 16
TREE_STEP = 4
CONTENT_MIN = 30


def rel_to(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


class FileTree(DirectoryTree):
    def __init__(self, root: Path, id: str = "tree"):
        super().__init__(root, id=id)
        self.root_path = Path(root)
        self.state: gitstate.GitState | None = None

    def rel(self, node) -> str | None:
        """시작 폴더 기준 상대 경로. 루트 밖(정션·링크를 DirectoryTree 가 resolve 한 경로)이면 None."""
        return "" if node is self.root else rel_to(node.data.path, self.root_path)

    def render_label(self, node, base_style, style):
        label = super().render_label(node, base_style, style)
        if node.data is None:
            return label
        rel = self.rel(node)
        if rel is None:  # 루트 밖: git 표시를 하지 않는다
            return label
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

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 3:
            return
        offset = event.get_content_offset(self)
        node = None if offset is None else self.get_node_at_line(offset.y + int(self.scroll_offset.y))
        if node is None or node.data is None:
            return
        event.stop()
        self.move_cursor(node)
        self.app.open_menu(node.data.path)

    def on_click(self, event: events.Click) -> None:
        if event.button == 3:
            event.prevent_default()  # Tree 기본 클릭(커서 줄 선택 → 파일 열기)을 막는다


class FileProvider(Provider):
    """/ 키 팔레트: 파일 이름으로 찾기."""

    async def startup(self) -> None:
        # ponytail: 열 때마다 전체 목록을 다시 모음. 파일 수십만 개면 캐시
        self._paths = await asyncio.to_thread(files.find_candidates, self.app.root)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for rel in self._paths:
            score = matcher.match(rel)
            if score > 0:
                yield Hit(score, matcher.highlight(rel), partial(self.app.open_file, self.app.root / rel), text=rel)


class MenuScreen(ModalScreen[str | None]):
    """우클릭·m 메뉴."""

    DEFAULT_CSS = """
    MenuScreen { align: center middle; }
    MenuScreen > OptionList { width: 36; height: auto; border: round $accent; }
    """
    BINDINGS = [Binding("escape", "close", "닫기")]

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def compose(self) -> ComposeResult:
        yield OptionList(Option("탐색기에서 열기", id="reveal"), Option("경로 복사", id="copy"),
                         Option("기본 프로그램으로 열기", id="open"))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_close(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """y / Enter → True, n / Esc → False."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Static { width: auto; max-width: 70; border: round $warning; padding: 1 2; background: $surface; }
    """
    BINDINGS = [Binding("y", "answer(True)"), Binding("enter", "answer(True)"),
                Binding("n", "answer(False)"), Binding("escape", "answer(False)")]

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        yield Static(self.question + "  (y 예 / n 아니요)")

    def action_answer(self, yes: bool) -> None:
        self.dismiss(yes)


# priority 바인딩은 메뉴·확인·찾기 창이 떠 있어도 앱까지 온다. 그때는 끈다(일반 키는 Textual 이 막는다).
PRIORITY_ACTIONS = {"next_tab", "previous_tab", "stop_edit"}


class FileViewerApp(App):
    CSS = """
    #tabs { width: 1fr; height: 1fr; }
    #tabs > ContentSwitcher { height: 1fr; }
    #empty { color: $text-muted; padding: 1 2; }
    """
    ENABLE_COMMAND_PALETTE = False  # ctrl+p 기본 팔레트 대신 / 로 파일 찾기
    BINDINGS = [
        Binding("slash", "find", "찾기", key_display="/"),
        Binding("tab", "next_tab", "다음 탭", priority=True),
        Binding("shift+tab", "previous_tab", "이전 탭", priority=True, show=False),
        Binding("w", "close_tab", "탭 닫기"),
        Binding("t", "toggle_tree", "트리"),
        Binding("left_square_bracket", f"tree_width({-TREE_STEP})", "트리 좁게", key_display="["),
        Binding("right_square_bracket", f"tree_width({TREE_STEP})", "트리 넓게", key_display="]"),
        Binding("v", "toggle_md", "md 보기"),
        Binding("o", "open_external", "열기"),
        Binding("m", "menu", "메뉴"),
        # 한글 입력 상태에서는 e 가 'ㄷ' 조합으로 먹혀 앱에 오지 않는다. Ctrl 조합은 입력기가 건드리지 않는다.
        Binding("e,ctrl+e", "edit", "편집", key_display="e/^e"),
        Binding("ctrl+s", "save", "저장"),
        # TextArea(tab_behavior=indent)가 Esc 를 먼저 먹으므로 priority. 편집 중에만 켜진다(check_action).
        Binding("escape", "stop_edit", "편집 끝", priority=True),
        Binding("q", "quit", "종료"),
    ]

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in PRIORITY_ACTIONS and isinstance(self.screen, ModalScreen):
            return False
        tab = self.current_tab
        editing = tab is not None and tab.editing
        if action in ("next_tab", "previous_tab", "edit"):
            return not editing  # 편집 중 Tab 은 TextArea 의 들여쓰기로 간다
        if action in ("save", "stop_edit"):
            return editing
        return True

    def __init__(self, root: Path, poll_interval: float = 1.0, follow: bool = False):
        super().__init__()
        self.root = root
        self.poll_interval = poll_interval
        self.follow = follow  # Herdr 에서 포커스된 칸의 폴더를 따라간다(따로 뜬 창)
        self.tab_ids: dict[Path, str] = {}
        self._tab_no = 0
        self.tree_width = 32
        self.narrow = False
        self.tree_shown = True  # 넓을 때 사용자가 고른 값
        self.tree_screen = False  # 좁을 때 트리 화면을 보고 있는지
        self._poll_worker = None
        self._listing: dict[Path, list[str] | None] = {}  # 폴링 스레드만 읽고 쓴다
        self._hint = Static(id="empty")  # 탭이 없을 때 안내. 첫 Resize 가 on_mount 보다 먼저 와서 미리 만든다

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
        tabs.mount(self._hint,
                   before=tabs.get_child_by_type(ContentSwitcher))
        self._load_state(self.query_one("#tree", FileTree))
        self.apply_layout()
        self.set_interval(self.poll_interval, self.poll_once)

    def poll_once(self) -> None:
        """한 번 확인한다. 대상은 메인 스레드에서 모으고, 디스크·git 은 스레드에서 읽는다."""
        if self._poll_worker is not None and self._poll_worker.is_running:
            return  # 앞 확인이 아직 도는 중(느린 git). 겹쳐 돌리지 않는다
        try:
            tree = self.query_one("#tree", FileTree)
        except NoMatches:  # 앱이 닫히는 중: 위젯이 먼저 지워지고 타이머가 한 번 더 돈다
            return
        tabs = [(t, t.path, t.key, t.deleted) for t in self.query(FileTab) if not t.editing]
        dirs, todo = [], [tree.root]
        while todo:
            node = todo.pop()
            if node.data is not None and node.allow_expand and node.is_expanded:
                dirs.append(node.data.path)
                todo.extend(node.children)
        self._poll_worker = self._poll(tree, tabs, dirs)

    @work(thread=True, group="poll", exit_on_error=False)  # 예상 못 한 예외로 앱을 끝내지 않는다
    def _poll(self, tree: FileTree, tabs: list, dirs: list[Path]) -> None:
        # 화면을 옮기지 않는다: 여기서는 open_file·커서 이동·탭 전환을 하지 않는다(설계 §6).
        if self.follow:
            cwd = herdr_right.focused_cwd()
            cwd = cwd.resolve() if cwd is not None and cwd.is_dir() else None
            if cwd is not None and cwd != self.root:
                self.call_from_thread(self.set_root, cwd)
                return  # 옛 폴더의 목록·git 은 볼 필요 없다. 다음 주기에 새 폴더로
        for tab, path, key, deleted in tabs:
            try:
                now = files.stat_key(path)
            except OSError:  # 권한 등. 이 탭은 이번 주기를 건너뛴다
                continue
            if now is None:
                if not deleted:
                    self.call_from_thread(self._mark_deleted, tab)
            elif now != key or deleted:
                self.call_from_thread(self._refresh_tab, tab)
        listing = {}
        for d in dirs:
            try:
                listing[d] = sorted(os.listdir(d))
            except OSError:
                listing[d] = None
        prev, self._listing = self._listing, listing
        if any(d in prev and prev[d] != names for d, names in listing.items()):
            self.call_from_thread(tree.reload)  # 펼침 상태와 커서는 reload 가 지킨다
        try:
            state = gitstate.read_state(self.root)
        except (gitstate.GitError, OSError):
            return  # 이전 표시를 두고 다음 주기에 다시
        if state != tree.state:
            self.call_from_thread(tree.set_state, state)

    def set_root(self, root: Path) -> None:
        """트리 맨 위를 바꾼다(--follow). 열린 탭은 그대로 둔다."""
        self.root = root
        tree = self.query_one("#tree", FileTree)
        tree.root_path, tree.state = root, None
        tree.path = root  # DirectoryTree 가 새 폴더로 다시 읽는다
        self._load_state(tree)

    def _refresh_tab(self, tab: FileTab) -> None:
        if tab.editing or not tab.is_attached:  # 그 사이 편집을 시작했거나 닫힘
            return
        try:
            tab.refresh_content(True)
        except OSError:
            pass  # 에이전트가 쓰는 중. 이전 내용을 두고 다음 주기에 다시 읽는다

    def _mark_deleted(self, tab: FileTab) -> None:
        if not tab.is_attached:
            return
        tab.deleted = True
        tab.show_notice(f"지워진 파일입니다: {rel_to(tab.path, self.root) or tab.path}")

    def on_resize(self, event: events.Resize) -> None:
        self.apply_layout(event.size.width)  # 이 시점의 self.size 는 아직 옛 값이다

    def apply_layout(self, width: int | None = None) -> None:
        tree, tabs = self.query_one("#tree", FileTree), self.query_one("#tabs")
        self.narrow = (width or self.size.width) < NARROW_BELOW
        if self.narrow:
            tree.display, tabs.display = self.tree_screen, not self.tree_screen
            tree.styles.width = "1fr"
        else:
            tree.display, tabs.display = self.tree_shown, True
            tree.styles.width = self.tree_width
        self._hint.update(
            "t 를 눌러 트리에서 파일을 고르세요" if self.narrow else "왼쪽 트리에서 파일을 고르세요")

    def action_toggle_tree(self) -> None:
        if self.narrow:
            self.tree_screen = shown = not self.tree_screen
        else:
            self.tree_shown = shown = not self.tree_shown
        self.apply_layout()
        if shown:
            self.query_one("#tree").focus()
        elif self.narrow:
            self._focus_content()

    def action_tree_width(self, step: int) -> None:
        if self.narrow:
            return
        self.tree_width = max(TREE_MIN, min(self.size.width - CONTENT_MIN, self.tree_width + step))
        self.apply_layout()

    @work(thread=True, exclusive=True, group="git", exit_on_error=False)
    def _load_state(self, tree: FileTree) -> None:
        try:
            state = gitstate.read_state(self.root)
        except gitstate.GitError:
            state = None
        self.call_from_thread(tree.set_state, state)

    @property
    def current_tab(self) -> FileTab | None:
        try:
            pane = self.query_one("#tabs", TabbedContent).active_pane
        except NoMatches:  # 뜨기 전·닫히는 중(check_action 이 이때도 불린다)
            return None
        return pane if isinstance(pane, FileTab) else None

    def open_file(self, path: Path) -> None:
        """이미 열려 있으면 그 탭으로, 아니면 새 탭을 연다."""
        new = path not in self.tab_ids
        if new:
            self._tab_no += 1
            self.tab_ids[path] = f"t{self._tab_no}"
        # 탭 붙이기는 비동기라 메시지 순서대로 처리되게 미룬다.
        self.call_later(self._show_tab, path, new)
        if self.narrow:
            self.tree_screen = False
        self.apply_layout()

    async def _show_tab(self, path: Path, new: bool) -> None:
        pane_id = self.tab_ids.get(path)
        if pane_id is None:  # 그 사이 닫힘
            return
        tabs = self.query_one("#tabs", TabbedContent)
        if new:
            await tabs.add_pane(FileTab(path, pane_id))
        tabs.active = pane_id
        self._update_empty()
        if self.narrow:  # 좁으면 트리가 숨어 포커스가 사라지므로 내용에 준다(PgDn 등으로 스크롤)
            self._focus_content()

    def _focus_content(self) -> None:
        tab = self.current_tab
        if tab is not None and not tab.editing:
            tab.query_one("#body").focus()

    def _update_empty(self) -> None:
        self._hint.display = not self.tab_ids

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
        self._unless_dirty(tab.is_dirty(), lambda: self._close(tab))

    def _close(self, tab: FileTab) -> None:
        if self.tab_ids.pop(tab.path, None) is None:
            return
        self.query_one("#tabs", TabbedContent).remove_pane(tab.id)
        self._update_empty()

    def _unless_dirty(self, dirty: bool, then) -> None:
        """저장하지 않은 변경이 있으면 버릴지 묻고, 예일 때만 then()."""
        if not dirty:
            then()
            return
        self.push_screen(ConfirmScreen("저장하지 않은 변경을 버릴까요?"), lambda yes: yes and then())

    def action_edit(self) -> None:
        tab = self.current_tab
        if tab is None:
            return
        if not tab.start_edit():
            self.notify("이 파일은 편집할 수 없습니다", severity="warning")
        self.refresh_bindings()

    def action_save(self) -> None:
        tab = self.current_tab
        if tab is None or not tab.editing:
            return
        if files.stat_key(tab.path) != tab.edit_key:
            self.push_screen(ConfirmScreen("다른 곳에서 파일이 바뀌었습니다. 덮어쓸까요?"),
                             lambda yes: yes and self._write(tab))
        else:
            self._write(tab)

    def _write(self, tab: FileTab) -> None:
        try:
            tab.write_file()
        except (OSError, UnicodeEncodeError) as e:  # 인코딩은 쓰기 전에 실패하므로 파일은 그대로
            self.notify(f"저장 실패: {e}", severity="error")
            return
        self.notify("저장했습니다")

    def action_stop_edit(self) -> None:
        tab = self.current_tab
        if tab is None or not tab.editing:
            return

        def stop() -> None:
            tab.stop_edit()
            self.refresh_bindings()
        self._unless_dirty(tab.is_dirty(), stop)

    async def action_quit(self) -> None:
        self._unless_dirty(any(t.is_dirty() for t in self.query(FileTab)), self.exit)

    def action_toggle_md(self) -> None:
        if self.current_tab:
            self.current_tab.toggle_md()

    def action_open_external(self) -> None:
        if self.current_tab:
            self.open_external(self.current_tab.path)

    def action_find(self) -> None:
        self.push_screen(CommandPalette(providers=[FileProvider], placeholder="파일 이름으로 찾기"))

    def action_menu(self) -> None:
        tree = self.query_one("#tree", FileTree)
        if tree.has_focus and tree.cursor_node is not None and tree.cursor_node.data is not None:
            self.open_menu(tree.cursor_node.data.path)
        elif self.current_tab:
            self.open_menu(self.current_tab.path)

    def open_menu(self, path: Path) -> None:
        def done(choice: str | None) -> None:
            try:
                if choice == "reveal":
                    shellops.reveal(path)
                elif choice == "copy":
                    shellops.copy_text(str(path))
                    self.notify("경로를 복사했습니다")
                elif choice == "open":
                    self.open_external(path)
            except (OSError, subprocess.SubprocessError) as e:
                self.notify(f"실패: {e}", severity="error")
        self.push_screen(MenuScreen(path), done)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """탭 머리 우클릭 → 그 탭 파일의 메뉴. 트리 우클릭은 FileTree 가 처리한다."""
        if event.button != 3 or event.widget is None:
            return
        tabs = self.query_one("#tabs", TabbedContent)
        for path, pane_id in self.tab_ids.items():
            try:
                hit = tabs.get_tab(pane_id) is event.widget
            except Exception:  # 아직 붙지 않은 탭
                continue
            if hit:
                self.open_menu(path)
                return
