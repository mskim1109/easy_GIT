from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, OptionList, Static
from textual.widgets.option_list import Option
from textual.worker import get_current_worker

from easy_git import gitio
from easy_git.diffview import DiffView

NARROW_BELOW = 90
SIDE_FROM = 160
WORKING_MESSAGE = "작업 중인 변경 (커밋 전)"
GIT_ERRORS = (gitio.GitError, OSError)

# 파일 목록 한 줄: (옵션 id 또는 묶음 제목이면 None, 화면 문구, 파일)
Entry = tuple[str | None, str, gitio.FileChange | None]


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


def working_entries(staged: list[gitio.FileChange], unstaged: list[gitio.FileChange]) -> list[Entry]:
    entries: list[Entry] = []
    for title, changes in (("Stage된 변경", staged), ("Stage 안 된 변경", unstaged)):
        entries.append((None, f"{title} ({len(changes)})", None))
        entries += commit_entries(changes)
    return entries


def commit_entries(changes: list[gitio.FileChange]) -> list[Entry]:
    return [(f"{f.group}:{f.path}", file_label(f), f) for f in changes]


def pick(ids: list[str | None], want_id: str | None, want_index: int | None) -> int | None:
    """want_id 가 있으면 그 자리, 없으면 want_index 이후 첫 파일(넘치면 마지막 파일)."""
    if want_id is not None and want_id in ids:  # 묶음 제목의 id 도 None 이다
        return ids.index(want_id)
    real = [i for i, k in enumerate(ids) if k]
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
    BINDINGS = [Binding("escape", "cancel", "취소")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("커밋 메시지 (Enter 커밋 · Esc 취소)")
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
    BINDINGS = [Binding("escape", "close", "닫기"), Binding("enter", "close", "닫기")]

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("커밋하지 못했습니다 (Enter / Esc 닫기)")
            with VerticalScroll():
                yield Static(self.text, markup=False)

    def action_close(self) -> None:
        self.dismiss(None)


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
        Binding("space", "toggle_stage", "Stage"),
        Binding("c", "commit", "커밋"),
        Binding("r", "reload", "새로 고침"),
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
        self._snap: str | None = None

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
        self.reload()
        self.set_interval(self.poll_interval, self._poll)

    def _git_failed(self, e: Exception, quiet: bool = False) -> None:
        """worker 안에서 난 git 오류. 폴링이면 조용히 넘기고, 사용자 동작이면 git 메시지를 보여준다."""
        if not quiet:
            self.call_from_thread(self.notify, error_text(e), title="git 오류", severity="error")

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
            if chosen:
                message, entries = commit_message(chosen), commit_entries(gitio.commit_changes(self.repo, chosen))
            else:
                message, entries = WORKING_MESSAGE, working_entries(staged, unstaged)
            index = pick([k for k, _, _ in entries], file_id, file_index)
            change = entries[index][2] if index is not None else None
            rows = gitio.file_rows(self.repo, change) if change else []
        except GIT_ERRORS as e:
            self._git_failed(e, quiet)
            return
        if not get_current_worker().is_cancelled:
            self.call_from_thread(
                self._apply_reload, selection, quiet, commits, staged, unstaged,
                chosen.sha if chosen else "WORKING", message, entries, index, rows,
            )

    def _apply_reload(self, selection, quiet, commits, staged, unstaged, commit_id, message, entries, index, rows) -> None:
        if self._selection() != selection:
            # 읽는 동안 사용자가 다른 항목으로 옮겼다. 그 선택으로 다시 읽는다.
            self.reload(quiet)
            return
        same_file = commit_id == selection[0] and index is not None and entries[index][0] == selection[1]
        with self.prevent(OptionList.OptionHighlighted):  # 목록을 다시 채우며 본문이 처음으로 돌아가지 않게
            self._fill_commits(commits, staged, unstaged, commit_id)
            self._fill_files(message, entries, index)
        self.query_one(DiffView).show(rows, self._shown_mode(), keep_scroll=same_file)

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
        options = [Option(f"● 작업 중인 변경 ({len(staged) + len(unstaged)})", id="WORKING")]
        options += [Option(f"{c.short}  {c.subject}  {rel_time(c.when, now)}", id=c.sha) for c in commits]
        lst = self.query_one("#commits", OptionList)
        lst.set_options(options)
        lst.highlighted = lst.get_option_index(commit_id)

    @on(OptionList.OptionHighlighted, "#commits")
    def _commit_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id == "WORKING":
            # git 호출이 없으니 worker 없이 바로 채운다
            entries = working_entries(self._staged, self._unstaged)
            self._fill_files(WORKING_MESSAGE, entries, pick([k for k, _, _ in entries], None, None))
        else:
            self.load_commit_files(self._commits[event.option.id])

    @work(thread=True, exclusive=True, group="files")
    def load_commit_files(self, commit: gitio.Commit) -> None:
        try:
            entries = commit_entries(gitio.commit_changes(self.repo, commit))
        except GIT_ERRORS as e:
            self._git_failed(e)
            return
        if not get_current_worker().is_cancelled:
            self.call_from_thread(self._fill_files, commit_message(commit), entries, pick([k for k, _, _ in entries], None, None))

    # --- 파일 목록 ---

    def _fill_files(self, message: str, entries: list[Entry], index: int | None) -> None:
        self.message_text = message
        self.query_one("#message", Static).update(message)
        self._files = {k: f for k, _, f in entries if k}
        lst = self.query_one("#files", OptionList)
        lst.set_options([Option(label, id=k, disabled=k is None) for k, label, _ in entries])
        if index is None:
            self.query_one(DiffView).show([], self._shown_mode())
        else:
            lst.highlighted = index

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
        try:
            rows = gitio.file_rows(self.repo, change)
        except GIT_ERRORS as e:
            self._git_failed(e)
            return
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

    def action_reload(self) -> None:
        self.reload()

    def action_toggle_stage(self) -> None:
        option = self.query_one("#files", OptionList).highlighted_option
        if option is None or option.id is None:
            return
        change = self._files[option.id]
        if change.group == "commit":
            self.notify("작업 중인 변경의 파일에서만 됩니다")
            return
        self._toggle_stage(change)

    @work(thread=True, group="git")
    def _toggle_stage(self, change: gitio.FileChange) -> None:
        try:
            (gitio.stage if change.group == "unstaged" else gitio.unstage)(self.repo, change)
        except GIT_ERRORS as e:
            self._git_failed(e)
            return
        self.call_from_thread(self.reload)

    def action_commit(self) -> None:
        if not self._staged:
            self.notify("Stage된 파일이 없습니다.")
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
            self.call_from_thread(self.notify, f"커밋했습니다: {short}")
            self.call_from_thread(self.reload)
        else:
            self.call_from_thread(self.push_screen, ResultScreen(out))
