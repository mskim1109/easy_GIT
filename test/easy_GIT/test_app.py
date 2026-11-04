import asyncio

from textual.widgets import Input, OptionList

from easy_git import gitio
from easy_git.app import CommitScreen, EasyGitApp, ResultScreen, layout_for, rel_time
from easy_git.diffview import DiffView
from easy_git.gitio import commits, working_changes
from conftest import git, write


async def settle(app, pilot):
    # 두 번은 기다리고, 뒤따라 생긴 worker(폴링이 부른 reload 등)가 남아 있으면 최대 5번까지 더 기다린다.
    # exclusive worker 는 뒤 요청에 밀려 취소될 수 있다(의도된 동작). 취소된 것 때문에 멈추지 않게 예외를 모은다.
    for i in range(5):
        await asyncio.gather(*(w.wait() for w in app.workers), return_exceptions=True)
        await pilot.pause()
        if i >= 1 and not app.workers:
            break


def _repo_with_change(repo):
    write(repo, "config.py", "".join(f"line{i}\n" for i in range(1, 11)))
    git(repo, "add", "."); git(repo, "commit", "-m", "설정 추가\n\n본문 설명")
    write(repo, "config.py", "".join(("CHANGED\n" if i == 5 else f"line{i}\n") for i in range(1, 11)))


def _prompts(option_list):
    return [str(option_list.get_option_at_index(i).prompt) for i in range(option_list.option_count)]


def test_wide_opens_working_changes_with_full_file(repo):
    _repo_with_change(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            commits_list = app.query_one("#commits", OptionList)
            files = app.query_one("#files", OptionList)
            diff = app.query_one(DiffView)
            assert str(commits_list.get_option_at_index(0).prompt).startswith("● Working changes (1)")
            assert any(p.startswith("Unstaged changes (1)") for p in _prompts(files))
            assert files.highlighted_option.id == "unstaged:config.py"
            assert diff.mode == "unified" and len(diff.rows) == 11 and diff.cursor_row == 4

    asyncio.run(run())


def test_v_toggles_side_by_side(repo):
    _repo_with_change(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            diff = app.query_one(DiffView)
            await pilot.press("v"); await settle(app, pilot)
            assert diff.mode == "side" and len(diff.rows) == 10
            await pilot.press("v"); await settle(app, pilot)
            assert diff.mode == "unified"

    asyncio.run(run())


def test_selecting_commit_shows_full_message(repo):
    _repo_with_change(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            app.query_one("#commits", OptionList).focus()
            await pilot.press("down"); await settle(app, pilot)
            assert "설정 추가" in app.message_text and "본문 설명" in app.message_text
            assert app.query_one("#files", OptionList).get_option_at_index(0).id == "commit:config.py"

    asyncio.run(run())


def test_n_and_p_move_between_changes(repo):
    write(repo, "config.py", "".join(f"line{i}\n" for i in range(1, 11)))
    git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "config.py", "".join(("X\n" if i in (2, 8) else f"line{i}\n") for i in range(1, 11)))

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            diff = app.query_one(DiffView)
            assert diff.cursor_row == 1
            await pilot.press("n"); assert diff.cursor_row == 8
            await pilot.press("n"); assert diff.cursor_row == 8
            await pilot.press("p"); assert diff.cursor_row == 1

    asyncio.run(run())


def test_rel_time():
    assert [rel_time(1000, 1030), rel_time(0, 120), rel_time(0, 7200), rel_time(0, 3 * 86400)] == ["just now", "2m ago", "2h ago", "3d ago"]
    assert rel_time(0, 40 * 86400) == "1970-01-01"


def test_layout_for():
    assert [layout_for(w) for w in (89, 90, 159, 160)] == ["narrow", "medium", "medium", "wide"]


def test_medium_forces_unified_and_restores_side(repo):
    _repo_with_change(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            diff = app.query_one(DiffView)
            await pilot.press("v"); await settle(app, pilot)
            assert diff.mode == "side"
            await pilot.resize_terminal(120, 40); await settle(app, pilot)
            assert (app.layout_name, diff.mode, app.view_mode) == ("medium", "unified", "side")
            await pilot.resize_terminal(200, 50); await settle(app, pilot)
            assert diff.mode == "side"

    asyncio.run(run())


def test_narrow_pages_between_list_and_diff(repo):
    _repo_with_change(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(70, 30)) as pilot:
            await settle(app, pilot)
            left, right = app.query_one("#left"), app.query_one("#right")
            files = app.query_one("#files", OptionList)
            assert (app.layout_name, app.narrow_page, right.display) == ("narrow", "list", False)
            files.focus(); await pilot.press("enter"); await settle(app, pilot)
            assert (app.narrow_page, left.display, right.display) == ("diff", False, True)
            await pilot.press("escape"); await settle(app, pilot)
            assert app.narrow_page == "list" and app.focused is files

    asyncio.run(run())


def test_space_stages_highlighted_unstaged_file(repo):
    _repo_with_change(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            files = app.query_one("#files", OptionList)
            assert files.highlighted_option.id == "unstaged:config.py"
            await pilot.press("space"); await settle(app, pilot)
            assert [f.path for f in working_changes(repo)[0]] == ["config.py"]
            assert "staged:config.py" in [files.get_option_at_index(i).id for i in range(files.option_count)]

    asyncio.run(run())


def test_commit_flow_with_korean_message(repo):
    _repo_with_change(repo)
    git(repo, "add", "config.py")

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            await pilot.press("c"); await settle(app, pilot)
            assert isinstance(app.screen, CommitScreen)
            app.screen.query_one(Input).value = "테스트 커밋"
            await pilot.press("enter"); await settle(app, pilot)
            assert commits(repo)[0].subject == "테스트 커밋"
            assert app.screen is app.screen_stack[0]

    asyncio.run(run())


def test_commit_failure_shows_git_output(repo):
    _repo_with_change(repo)
    git(repo, "add", "config.py")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho hook says no >&2\nexit 1\n", newline="\n")

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            await pilot.press("c"); await settle(app, pilot)
            app.screen.query_one(Input).value = "x"
            await pilot.press("enter"); await settle(app, pilot)
            assert isinstance(app.screen, ResultScreen) and "hook says no" in app.screen.text

    asyncio.run(run())


def test_commit_with_nothing_staged_does_not_open_input(repo):
    _repo_with_change(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            await pilot.press("c"); await settle(app, pilot)
            assert not isinstance(app.screen, CommitScreen)

    asyncio.run(run())


def test_auto_refresh_picks_up_external_edit(repo):
    _repo_with_change(repo)

    async def run():
        app = EasyGitApp(repo, poll_interval=0.1)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            diff = app.query_one(DiffView)
            write(repo, "config.py", "".join(("CHANGED\n" if i == 5 else "AGENT\n" if i == 9 else f"line{i}\n") for i in range(1, 11)))
            for _ in range(30):
                await pilot.pause(0.1); await settle(app, pilot)
                if any(r.text == "AGENT" for r in diff.rows):
                    break
            assert any(r.text == "AGENT" for r in diff.rows)

    asyncio.run(run())


def test_refresh_keeps_selection_and_scroll(repo):
    write(repo, "long.txt", "".join(f"line{i}\n" for i in range(1, 201)))
    write(repo, "other.txt", "a\n")
    git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "long.txt", "".join(("FIRST\n" if i == 1 else f"line{i}\n") for i in range(1, 201)))
    write(repo, "other.txt", "b\n")

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            files = app.query_one("#files", OptionList)
            diff = app.query_one(DiffView)
            files.highlighted = files.get_option_index("unstaged:long.txt"); await settle(app, pilot)
            diff.scroll_to(y=50, animate=False); await pilot.pause()
            write(repo, "other.txt", "c\n")
            app.reload(); await settle(app, pilot)
            assert files.highlighted_option.id == "unstaged:long.txt" and diff.scroll_y == 50

    asyncio.run(run())


def test_poll_survives_git_error(repo, monkeypatch):
    _repo_with_change(repo)

    def boom(*args, **kwargs):
        raise gitio.GitError("index.lock")

    async def run():
        app = EasyGitApp(repo, poll_interval=0.1)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            diff = app.query_one(DiffView)
            rows = diff.rows
            monkeypatch.setattr(gitio, "snapshot", boom)
            await settle(app, pilot)  # 패치 전에 이미 돌던 폴링이 끝나기를 기다린다
            write(repo, "config.py", "changed again\n")
            await pilot.pause(0.5)
            assert app.is_running and diff.rows == rows

    asyncio.run(run())


def test_git_errors_from_user_keys_are_notified(repo, monkeypatch):
    _repo_with_change(repo)

    def boom(*args, **kwargs):
        raise gitio.GitError("fatal: index.lock exists")

    async def run():
        app = EasyGitApp(repo)
        notes = []
        app.notify = lambda message, **kwargs: notes.append(message)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            monkeypatch.setattr(gitio, "stage", boom)
            await pilot.press("space"); await settle(app, pilot)
            monkeypatch.setattr(gitio, "working_changes", boom)
            await pilot.press("r"); await settle(app, pilot)
            assert app.is_running and notes == ["fatal: index.lock exists"] * 2

    asyncio.run(run())
