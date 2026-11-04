from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, OptionList, Static
from textual.widgets.option_list import Option
from textual.worker import get_current_worker

from easy_git import gitio
from easy_git.diffview import DiffView, colored

NARROW_BELOW = 90
SIDE_FROM = 160
MIN_LEFT, MIN_RIGHT, MIN_LIST = 20, 30, 3  # 마우스로 끌 때 칸이 사라지지 않게 하는 최소 크기
WORKING_MESSAGE = "Working changes (not committed)"
GIT_ERRORS = (gitio.GitError, OSError)

# 파일 목록 한 줄: (옵션 id 또는 묶음 제목이면 None, 화면 문구, 파일 — 폴더·제목이면 None)
# 폴더 id 는 "dir:{group}:{폴더 경로}", 파일 id 는 "{group}:{파일 경로}"
Entry = tuple[str | None, str, gitio.FileChange | None]


def rel_time(epoch: int, now: int) -> str:
    d = now - epoch
    if d < 60:
        return "just now"
    if d < 3600:
        return f"{d // 60}m ago"
    if d < 86400:
        return f"{d // 3600}h ago"
    if d < 30 * 86400:
        return f"{d // 86400}d ago"
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d")


def layout_for(width: int) -> str:
    if width < NARROW_BELOW:
        return "narrow"
    return "wide" if width >= SIDE_FROM else "medium"


def file_label(f: gitio.FileChange, name: str) -> str:
    renamed = f" ← {f.old_path}" if f.old_path else ""
    nums = "binary" if f.binary else f"+{f.added} -{f.deleted}"
    return f"{f.status} {name}{renamed}  {nums}"


def tree_entries(changes: list[gitio.FileChange], collapsed: set[str]) -> list[Entry]:
    """한 묶음의 파일들을 폴더 트리로. 폴더가 먼저, 하위 폴더 하나뿐인 폴더는 한 줄로 합친다."""
    root: dict = {}
    for f in changes:
        *dirs, name = f.path.split("/")
        node = root
        for d in dirs:
            node = node.setdefault(d + "/", {})
        node[name] = f
    entries: list[Entry] = []

    def walk(node: dict, prefix: str, depth: int) -> None:
        indent = "  " * depth
        for name in sorted((k for k in node if k.endswith("/")), key=str.casefold):
            child = node[name]
            while len(child) == 1 and next(iter(child)).endswith("/"):
                (sub, child), = child.items()
                name += sub
            folder_id = f"dir:{changes[0].group}:{prefix}{name}".rstrip("/")
            shut = folder_id in collapsed
            entries.append((folder_id, f"{indent}{'▸' if shut else '▾'} {name}", None))
            if not shut:
                walk(child, prefix + name, depth + 1)
        for name in sorted((k for k in node if not k.endswith("/")), key=str.casefold):
            f = node[name]
            entries.append((f"{f.group}:{f.path}", indent + file_label(f, name), f))

    walk(root, "", 0)
    return entries


def one_line(s: str) -> Text:
    """목록 한 줄: 칸보다 길면 다음 줄로 넘기지 않고 … 으로 자른다."""
    return Text(s, no_wrap=True, overflow="ellipsis")


STATUS_COLORS = {"M": "#E2C08D", "A": "#73C991", "D": "#C74E39", "R": "#4EC9B0"}  # VS Code git 표시 색


def status_prompt(label: str, change: gitio.FileChange | None) -> Text:
    """파일 줄이면 상태 글자(M/A/D/R)에 색을 입힌다. 글자는 들여쓰기 바로 뒤에 있다."""
    text = one_line(label)
    if change is not None and change.status in STATUS_COLORS:
        at = len(label) - len(label.lstrip(" "))
        text.stylize(STATUS_COLORS[change.status], at, at + 1)
    return text


def commit_message(c: gitio.Commit) -> str:
    when = datetime.fromtimestamp(c.when).strftime("%Y-%m-%d %H:%M")
    text = f"{c.short}  {c.subject}\n{c.author} · {when}"
    body = c.body.strip()
    return f"{text}\n\n{body}" if body else text


def working_entries(staged: list[gitio.FileChange], unstaged: list[gitio.FileChange], collapsed: set[str]) -> list[Entry]:
    entries: list[Entry] = []
    for title, changes in (("Staged changes", staged), ("Unstaged changes", unstaged)):
        entries.append((None, f"{title} ({len(changes)})", None))
        entries += tree_entries(changes, collapsed)
    return entries


def pick(ids: list[str | None], want_id: str | None, want_index: int | None) -> int | None:
    """want_id 가 있으면 그 자리, 없으면 want_index 이후 첫 파일(넘치면 마지막 파일). 폴더는 건너뛴다."""
    if want_id is not None and want_id in ids:  # 묶음 제목의 id 도 None 이다
        return ids.index(want_id)
    real = [i for i, k in enumerate(ids) if k and not k.startswith("dir:")]
    if not real:
        return None
    return next((i for i in real if i >= (want_index or 0)), real[-1])


def error_text(e: Exception) -> str:
    return getattr(e, "output", "").strip() or str(e)


class CommitScreen(ModalScreen[str | None]):
    DEFAULT_CSS = """
    CommitScreen { align: center middle; }
    CommitScreen > Vertical { width: 80%; height: auto; border: round $primary; background: $surface; padding: 0 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Commit message (Enter: commit · Esc: cancel)")
            yield Input()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ResultScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    ResultScreen { align: center middle; }
    ResultScreen > Vertical { width: 80%; height: auto; max-height: 80%; border: round $error; background: $surface; padding: 0 1; }
    ResultScreen VerticalScroll { height: auto; max-height: 30; }
    """
    BINDINGS = [Binding("escape", "close", "Close"), Binding("enter", "close", "Close")]

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Commit failed (Enter / Esc: close)")
            with VerticalScroll():
                yield Static(self.text, markup=False)

    def action_close(self) -> None:
        self.dismiss(None)


class Splitter(Widget):
    """마우스로 끌어 옆 칸 크기를 바꾸는 경계선."""
    DEFAULT_CSS = """
    Splitter { background: $panel; }
    Splitter:hover, Splitter.-dragging { background: $accent; }
    Splitter.-vertical { width: 1; height: 1fr; }
    Splitter.-horizontal { height: 1; width: 1fr; }
    """

    class Dragged(Message):
        """끄는 중이면 done=False (안내선만 옮긴다), 놓으면 done=True (칸 크기를 바꾼다)."""

        def __init__(self, splitter: "Splitter", x: int, y: int, done: bool) -> None:
            super().__init__()
            self.splitter, self.x, self.y, self.done = splitter, x, y, done

    def __init__(self, vertical: bool, id: str) -> None:
        super().__init__(id=id, classes="-vertical" if vertical else "-horizontal")

    def render(self) -> str:
        return ""  # 배경색만 보이는 선. 기본 render 는 위젯 이름을 그린다

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.capture_mouse()
        self.add_class("-dragging")

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.has_class("-dragging"):
            self.post_message(self.Dragged(self, event.screen_x, event.screen_y, done=False))

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self.has_class("-dragging"):
            self.post_message(self.Dragged(self, event.screen_x, event.screen_y, done=True))
        self.release_mouse()
        self.remove_class("-dragging")


class EasyGitApp(App):
    CSS = """
    #commits, #files { height: 1fr; text-wrap: nowrap; text-overflow: ellipsis; }
    #message { height: auto; max-height: 40%; padding: 0 1; }
    #diff { height: 1fr; }
    Screen { layers: base guide; }
    #ghost { layer: guide; display: none; background: $accent; }
    Screen.-narrow #right, Screen.-narrow #split-v { display: none; }
    Screen.-narrow.-page-diff #left { display: none; }
    Screen.-narrow.-page-diff #right { display: block; }
    """
    BINDINGS = [
        Binding("v", "toggle_view", "View"),
        Binding("n", "next_change", "Next change"),
        Binding("p", "prev_change", "Prev change"),
        Binding("space", "toggle_stage", "Stage"),
        Binding("c", "commit", "Commit"),
        Binding("r", "reload", "Refresh"),
        Binding("escape", "back", "Back", show=False),
        Binding("left", "fold(False)", "Collapse", show=False),
        Binding("right", "fold(True)", "Expand", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, repo: Path, poll_interval: float = 1.0) -> None:
        super().__init__()
        self.repo = repo
        self.poll_interval = poll_interval
        self.view_mode = "unified"
        self.message_text = ""
        self.layout_name = "wide"
        self.narrow_page = "list"
        self._commits: dict[str, gitio.Commit] = {}
        self._staged: list[gitio.FileChange] = []
        self._unstaged: list[gitio.FileChange] = []
        self._files: dict[str, gitio.FileChange] = {}
        self._commit_changes: list[gitio.FileChange] = []  # 지금 고른 커밋의 파일 (폴더 접기·펴기 때 다시 그리려고)
        self._collapsed: set[str] = set()  # 접힌 폴더 id. 새로 고침해도 유지한다
        self._left_width: int | None = None  # 마우스로 끌어 정한 왼쪽 열 너비. 끄면 잊는다
        self._snap: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="left"):
                yield OptionList(id="commits", markup=False)
                yield Splitter(vertical=False, id="split-h")
                yield OptionList(id="files", markup=False)
            yield Splitter(vertical=True, id="split-v")
            with Vertical(id="right"):
                yield Static(id="message", markup=False)
                yield DiffView(id="diff")
        yield Static(id="ghost")  # 경계를 끄는 동안만 보이는 안내선 (배치 위에 따로 얹힌다)
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "nord"
        self._apply_layout(self.size.width)
        self.reload()
        self.set_interval(self.poll_interval, self._poll)

    def _git_failed(self, e: Exception, quiet: bool = False) -> None:
        """worker 안에서 난 git 오류. 폴링이면 조용히 넘기고, 사용자 동작이면 git 메시지를 보여준다."""
        if not quiet:
            self.call_from_thread(self.notify, error_text(e), title="git error", severity="error")

    # --- 배치 ---

    def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(event.size.width)

    def _apply_layout(self, width: int) -> None:
        self.layout_name = layout_for(width)
        left = self.query_one("#left")
        if self.layout_name == "narrow":
            left.styles.width = "100%"
        elif self._left_width:
            left.styles.width = max(MIN_LEFT, min(self._left_width, width - MIN_RIGHT))
        else:
            left.styles.width = "40%"
        self._apply_page()
        self._sync_mode()

    @on(Splitter.Dragged)
    def _splitter_dragged(self, event: Splitter.Dragged) -> None:
        ghost, r = self.query_one("#ghost"), event.splitter.region
        vertical = event.splitter.id == "split-v"
        if not event.done:  # 칸은 그대로 두고 안내선만 옮긴다 (칸 크기를 바꾸면 화면 전체를 다시 그린다)
            ghost.styles.width, ghost.styles.height = (1, r.height) if vertical else (r.width, 1)
            ghost.styles.offset = (event.x, r.y) if vertical else (r.x, event.y)
            ghost.display = True
            return
        ghost.display = False
        if vertical:
            left = self.query_one("#left")
            self._left_width = max(MIN_LEFT, min(event.x - left.region.x, self.size.width - MIN_RIGHT))
            left.styles.width = self._left_width
        else:
            commits, left = self.query_one("#commits"), self.query_one("#left")
            commits.styles.height = max(MIN_LIST, min(event.y - commits.region.y, left.region.height - MIN_LIST - 1))

    def _apply_page(self) -> None:
        screen = self.screen_stack[0]  # 모달이 떠 있어도 메인 화면에
        screen.set_class(self.layout_name == "narrow", "-narrow")
        screen.set_class(self.narrow_page == "diff", "-page-diff")

    def _shown_mode(self) -> str:
        return "side" if self.view_mode == "side" and self.layout_name == "wide" else "unified"

    # --- 다시 읽기 ---

    def _selection(self) -> tuple[str | None, str | None, int | None]:
        files = self.query_one("#files", OptionList)
        commit = self.query_one("#commits", OptionList).highlighted_option
        file = files.highlighted_option
        return (commit.id if commit else None, file.id if file else None, files.highlighted)

    def reload(self, quiet: bool = False) -> None:
        """선택과 스크롤을 유지하며 다시 읽는다."""
        self._reload(self._selection(), quiet)

    @work(thread=True, exclusive=True, group="lists")
    def _reload(self, selection: tuple[str | None, str | None, int | None], quiet: bool) -> None:
        commit_id, file_id, file_index = selection
        try:
            try:  # 읽기 전에 찍어 두어야 읽는 도중의 변경을 다음 폴링이 잡는다
                self._snap = gitio.snapshot(self.repo)
            except GIT_ERRORS:
                pass
            commits = gitio.commits(self.repo)
            staged, unstaged = gitio.working_changes(self.repo)
            chosen = next((c for c in commits if c.sha == commit_id), None)
            collapsed = set(self._collapsed)
            commit_changes = gitio.commit_changes(self.repo, chosen) if chosen else []
            if chosen:
                message, entries = commit_message(chosen), tree_entries(commit_changes, collapsed)
            else:
                message, entries = WORKING_MESSAGE, working_entries(staged, unstaged, collapsed)
            index = pick([k for k, _, _ in entries], file_id, file_index)
            change = entries[index][2] if index is not None else None  # 폴더면 None
            rows = gitio.file_rows(self.repo, change) if change else []
            colors = colored(rows, change.path) if rows else None  # 색칠은 여기(worker)서: 큰 파일은 오래 걸린다
        except GIT_ERRORS as e:
            self._git_failed(e, quiet)
            return
        if not get_current_worker().is_cancelled:
            self.call_from_thread(
                self._apply_reload, selection, quiet, commits, staged, unstaged,
                chosen.sha if chosen else "WORKING", message, entries, index, rows, commit_changes, colors,
            )

    def _apply_reload(self, selection, quiet, commits, staged, unstaged, commit_id, message, entries, index, rows, commit_changes, colors) -> None:
        if self._selection() != selection:
            # 읽는 동안 사용자가 다른 항목으로 옮겼다. 그 선택으로 다시 읽는다.
            self.reload(quiet)
            return
        same_file = commit_id == selection[0] and index is not None and entries[index][0] == selection[1]
        self._commit_changes = commit_changes
        with self.prevent(OptionList.OptionHighlighted):  # 목록을 다시 채우며 본문이 처음으로 돌아가지 않게
            self._fill_commits(commits, staged, unstaged, commit_id)
            self._fill_files(message, entries, index)
        if index is not None and entries[index][2] is None:
            return  # 폴더에 있었다: 본문은 그대로 둔다
        path = entries[index][2].path if index is not None else ""
        self.query_one(DiffView).show(rows, self._shown_mode(), keep_scroll=same_file, path=path, colors=colors)

    def _poll(self) -> None:
        # 이전 확인이 아직 돌고 있으면 이번 주기는 건너뛴다 (스레드가 쌓이지 않게)
        if not any(w.group == "poll" and not w.is_finished for w in self.workers):
            self._check_changes()

    @work(thread=True, group="poll")
    def _check_changes(self) -> None:
        try:
            snap = gitio.snapshot(self.repo)
        except GIT_ERRORS:
            return  # index.lock 등: 다음 주기에 다시
        if snap != self._snap:
            self._snap = snap
            self.call_from_thread(self.reload, True)

    # --- 커밋 목록 ---

    def _fill_commits(self, commits: list[gitio.Commit], staged: list[gitio.FileChange], unstaged: list[gitio.FileChange], commit_id: str) -> None:
        self._commits = {c.sha: c for c in commits}
        self._staged, self._unstaged = staged, unstaged
        now = int(time.time())
        options = [Option(one_line(f"● Working changes ({len(staged) + len(unstaged)})"), id="WORKING")]
        options += [Option(one_line(f"{c.short}  {c.subject}  {rel_time(c.when, now)}"), id=c.sha) for c in commits]
        lst = self.query_one("#commits", OptionList)
        lst.set_options(options)
        lst.highlighted = lst.get_option_index(commit_id)

    @on(OptionList.OptionHighlighted, "#commits")
    def _commit_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id == "WORKING":
            # git 호출이 없으니 worker 없이 바로 채운다
            self._commit_changes = []
            entries = working_entries(self._staged, self._unstaged, self._collapsed)
            self._fill_files(WORKING_MESSAGE, entries, pick([k for k, _, _ in entries], None, None))
        else:
            self.load_commit_files(self._commits[event.option.id])

    @work(thread=True, exclusive=True, group="files")
    def load_commit_files(self, commit: gitio.Commit) -> None:
        try:
            changes = gitio.commit_changes(self.repo, commit)
        except GIT_ERRORS as e:
            self._git_failed(e)
            return
        if not get_current_worker().is_cancelled:
            self.call_from_thread(self._show_commit_files, commit, changes)

    def _show_commit_files(self, commit: gitio.Commit, changes: list[gitio.FileChange]) -> None:
        self._commit_changes = changes
        entries = tree_entries(changes, self._collapsed)
        self._fill_files(commit_message(commit), entries, pick([k for k, _, _ in entries], None, None))

    # --- 파일 목록 ---

    def _fill_files(self, message: str, entries: list[Entry], index: int | None) -> None:
        self.message_text = message
        self.query_one("#message", Static).update(message)
        self._files = {k: f for k, _, f in entries if f}
        lst = self.query_one("#files", OptionList)
        lst.set_options([Option(status_prompt(label, f), id=k, disabled=k is None) for k, label, f in entries])
        if index is None:
            self.query_one(DiffView).show([], self._shown_mode())
        else:
            lst.highlighted = index

    def _redraw_files(self, want_id: str) -> None:
        """폴더를 접거나 편 뒤, git 을 다시 읽지 않고 파일 목록만 다시 그린다."""
        commit = self.query_one("#commits", OptionList).highlighted_option
        if commit is not None and commit.id != "WORKING":
            entries = tree_entries(self._commit_changes, self._collapsed)
        else:
            entries = working_entries(self._staged, self._unstaged, self._collapsed)
        with self.prevent(OptionList.OptionHighlighted):
            self._fill_files(self.message_text, entries, pick([k for k, _, _ in entries], want_id, None))

    @on(OptionList.OptionHighlighted, "#files")
    def _file_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id in self._files:  # 폴더면 본문은 그대로 둔다
            self.load_rows(self._files[event.option.id])

    @on(OptionList.OptionSelected, "#files")
    def _file_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id not in self._files:  # 폴더: Enter·클릭으로 접고 편다
            self._set_folded(event.option.id, event.option.id not in self._collapsed)
            return
        if self.layout_name == "narrow":
            self.narrow_page = "diff"
            self._apply_page()
            self.call_after_refresh(self.query_one(DiffView).focus)

    @work(thread=True, exclusive=True, group="rows")
    def load_rows(self, change: gitio.FileChange) -> None:
        try:
            rows = gitio.file_rows(self.repo, change)
            colors = colored(rows, change.path) if rows else None  # 색칠은 여기(worker)서
        except GIT_ERRORS as e:
            self._git_failed(e)
            return
        if not get_current_worker().is_cancelled:
            self.call_from_thread(lambda: self.query_one(DiffView).show(rows, self._shown_mode(), path=change.path, colors=colors))

    # --- 키 ---

    def action_toggle_view(self) -> None:
        self.view_mode = "side" if self.view_mode == "unified" else "unified"
        self._sync_mode()

    def _sync_mode(self) -> None:
        diff = self.query_one(DiffView)
        if diff.mode != self._shown_mode():
            diff.set_mode(self._shown_mode())

    def action_next_change(self) -> None:
        self.query_one(DiffView).next_change()

    def action_prev_change(self) -> None:
        self.query_one(DiffView).prev_change()

    def action_back(self) -> None:
        if self.layout_name == "narrow":
            self.narrow_page = "list"
            self._apply_page()
            self.call_after_refresh(self.query_one("#files").focus)

    def action_reload(self) -> None:
        self.reload()

    def _set_folded(self, folder_id: str, folded: bool) -> None:
        (self._collapsed.add if folded else self._collapsed.discard)(folder_id)
        self._redraw_files(folder_id)

    def action_fold(self, expand: bool) -> None:
        files = self.query_one("#files", OptionList)
        option = files.highlighted_option
        if self.focused is not files or option is None or option.id is None:
            return
        if option.id not in self._files:  # 폴더
            self._set_folded(option.id, not expand)
            return
        if not expand:  # 파일에서 ← : 그 파일이 든 폴더를 접고 그 폴더로 옮긴다
            change = self._files[option.id]
            parents = [k for k in self._folder_ids() if change.path.startswith(k.split(":", 2)[2] + "/") and k.startswith(f"dir:{change.group}:")]
            if parents:
                self._set_folded(max(parents, key=len), True)

    def _folder_ids(self) -> list[str]:
        files = self.query_one("#files", OptionList)
        ids = (files.get_option_at_index(i).id for i in range(files.option_count))
        return [k for k in ids if k and k not in self._files]

    def action_toggle_stage(self) -> None:
        option = self.query_one("#files", OptionList).highlighted_option
        if option is None or option.id is None:
            return
        if option.id in self._files:
            changes = [self._files[option.id]]
        else:  # 폴더: 접혀 있어도 그 안의 파일 전체
            _, group, folder = option.id.split(":", 2)
            changes = [f for f in self._staged + self._unstaged if f.group == group and f.path.startswith(folder + "/")]
        if not changes or changes[0].group == "commit":
            self.notify("Only working changes can be staged")
            return
        self._toggle_stage(changes)

    @work(thread=True, group="git")
    def _toggle_stage(self, changes: list[gitio.FileChange]) -> None:
        try:
            for change in changes:  # ponytail: 파일마다 git 한 번. 수백 개 폴더에서 느리면 경로를 묶어 한 번에
                (gitio.stage if change.group == "unstaged" else gitio.unstage)(self.repo, change)
        except GIT_ERRORS as e:
            self._git_failed(e)
            return
        self.call_from_thread(self.reload)

    def action_commit(self) -> None:
        if not self._staged:
            self.notify("Nothing staged.")
            return
        self.push_screen(CommitScreen(), self._commit_entered)

    def _commit_entered(self, message: str | None) -> None:
        if message is not None:
            self._commit(message)

    @work(thread=True, group="git")
    def _commit(self, message: str) -> None:
        try:
            ok, out = gitio.commit(self.repo, message)
            short = gitio.commits(self.repo, 1)[0].short if ok else ""
        except GIT_ERRORS as e:
            self._git_failed(e)
            return
        if ok:
            self.call_from_thread(self.notify, f"Committed {short}")
            self.call_from_thread(self.reload)
        else:
            self.call_from_thread(self.push_screen, ResultScreen(out))
