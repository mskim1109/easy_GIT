import asyncio

from textual.widgets import OptionList

from easy_git.app import EasyGitApp, layout_for, rel_time
from easy_git.diffview import DiffView
from conftest import git, write


async def settle(app, pilot):
    for _ in range(2):
        await app.workers.wait_for_complete()
        await pilot.pause()


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
            assert str(commits_list.get_option_at_index(0).prompt).startswith("● 작업 중인 변경 (1)")
            assert any(p.startswith("Stage 안 된 변경 (1)") for p in _prompts(files))
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
    assert [rel_time(1000, 1030), rel_time(0, 120), rel_time(0, 7200), rel_time(0, 3 * 86400)] == ["방금", "2분 전", "2시간 전", "3일 전"]
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
