from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option
from textual.worker import get_current_worker

from easy_git import gitio
from easy_git.diffview import DiffView

NARROW_BELOW = 90
SIDE_FROM = 160


def rel_time(epoch: int, now: int) -> str:
    d = now - epoch
    if d < 60:
        return "방금"
    if d < 3600:
        return f"{d // 60}분 전"
    if d < 86400:
        return f"{d // 3600}시간 전"
    if d < 30 * 86400:
        return f"{d // 86400}일 전"
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d")


def layout_for(width: int) -> str:
    if width < NARROW_BELOW:
        return "narrow"
    return "wide" if width >= SIDE_FROM else "medium"


def file_label(f: gitio.FileChange) -> str:
    path = f"{f.old_path} → {f.path}" if f.old_path else f.path
    nums = "바이너리" if f.binary else f"+{f.added} -{f.deleted}"
    return f"{f.status} {path}  {nums}"


def commit_message(c: gitio.Commit) -> str:
    when = datetime.fromtimestamp(c.when).strftime("%Y-%m-%d %H:%M")
    text = f"{c.short}  {c.subject}\n{c.author} · {when}"
    body = c.body.strip()
    return f"{text}\n\n{body}" if body else text


class EasyGitApp(App):
    CSS = """
    #left { width: 40%; }
    #commits, #files { height: 1fr; }
    #message { height: auto; max-height: 40%; padding: 0 1; }
    #diff { height: 1fr; }
    Screen.-narrow #left { width: 100%; }
    Screen.-narrow #right { display: none; }
    Screen.-narrow.-page-diff #left { display: none; }
    Screen.-narrow.-page-diff #right { display: block; }
    """
    BINDINGS = [
        Binding("v", "toggle_view", "보기 전환"),
        Binding("n", "next_change", "다음 변경"),
        Binding("p", "prev_change", "이전 변경"),
        Binding("escape", "back", "목록으로", show=False),
        Binding("q", "quit", "닫기"),
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

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="left"):
                yield OptionList(id="commits", markup=False)
                yield OptionList(id="files", markup=False)
            with Vertical(id="right"):
                yield Static(id="message", markup=False)
                yield DiffView(id="diff")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "nord"
        self._apply_layout(self.size.width)
        self.load_lists()

    # --- 배치 ---

    def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(event.size.width)

    def _apply_layout(self, width: int) -> None:
        self.layout_name = layout_for(width)
        self._apply_page()
        self._sync_mode()

    def _apply_page(self) -> None:
        screen = self.screen_stack[0]  # 모달이 떠 있어도 메인 화면에
        screen.set_class(self.layout_name == "narrow", "-narrow")
        screen.set_class(self.narrow_page == "diff", "-page-diff")

    def _shown_mode(self) -> str:
        return "side" if self.view_mode == "side" and self.layout_name == "wide" else "unified"

    # --- 커밋 목록 ---

    @work(thread=True, exclusive=True, group="lists")
    def load_lists(self) -> None:
        commits = gitio.commits(self.repo)
        staged, unstaged = gitio.working_changes(self.repo)
        if not get_current_worker().is_cancelled:
            self.call_from_thread(self._fill_commits, commits, staged, unstaged)

    def _fill_commits(self, commits: list[gitio.Commit], staged: list[gitio.FileChange], unstaged: list[gitio.FileChange]) -> None:
        self._commits = {c.sha: c for c in commits}
        self._staged, self._unstaged = staged, unstaged
        now = int(time.time())
        options = [Option(f"● 작업 중인 변경 ({len(staged) + len(unstaged)})", id="WORKING")]
        options += [Option(f"{c.short}  {c.subject}  {rel_time(c.when, now)}", id=c.sha) for c in commits]
        lst = self.query_one("#commits", OptionList)
        lst.set_options(options)
        lst.highlighted = 0

    @on(OptionList.OptionHighlighted, "#commits")
    def _commit_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id == "WORKING":
            # git 호출이 없으니 worker 없이 바로 채운다
            groups = [("Stage된 변경", self._staged), ("Stage 안 된 변경", self._unstaged)]
            self._fill_files("작업 중인 변경 (커밋 전)", groups)
        else:
            self.load_commit_files(self._commits[event.option.id])

    @work(thread=True, exclusive=True, group="files")
    def load_commit_files(self, commit: gitio.Commit) -> None:
        changes = gitio.commit_changes(self.repo, commit)
        if not get_current_worker().is_cancelled:
            self.call_from_thread(self._fill_files, commit_message(commit), [(None, changes)])

    # --- 파일 목록 ---

    def _fill_files(self, message: str, groups: list[tuple[str | None, list[gitio.FileChange]]]) -> None:
        self.message_text = message
        self.query_one("#message", Static).update(message)
        self._files = {}
        options: list[Option] = []
        for title, changes in groups:
            if title:
                options.append(Option(f"{title} ({len(changes)})", disabled=True))
            for f in changes:
                key = f"{f.group}:{f.path}"
                self._files[key] = f
                options.append(Option(file_label(f), id=key))
        lst = self.query_one("#files", OptionList)
        lst.set_options(options)
        first = next((i for i, o in enumerate(options) if o.id), None)
        if first is None:
            self.query_one(DiffView).show([], self._shown_mode())
        else:
            lst.highlighted = first

    @on(OptionList.OptionHighlighted, "#files")
    def _file_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self.load_rows(self._files[event.option.id])

    @on(OptionList.OptionSelected, "#files")
    def _file_selected(self) -> None:
        if self.layout_name == "narrow":
            self.narrow_page = "diff"
            self._apply_page()
            self.call_after_refresh(self.query_one(DiffView).focus)

    @work(thread=True, exclusive=True, group="rows")
    def load_rows(self, change: gitio.FileChange) -> None:
        rows = gitio.file_rows(self.repo, change)
        if not get_current_worker().is_cancelled:
            self.call_from_thread(lambda: self.query_one(DiffView).show(rows, self._shown_mode()))

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
