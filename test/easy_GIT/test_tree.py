import asyncio

from textual import strip as strip_mod
from textual.widgets import OptionList

from easy_git.app import MIN_LEFT, EasyGitApp, pick, tree_entries, working_entries
from easy_git.gitio import FileChange, working_changes
from conftest import git, write
from test_app import _prompts, settle


def fc(path, group="unstaged", status="M", old_path=None):
    return FileChange(group, status, path, old_path, added=1, deleted=0)


def _rows(entries):
    return [(k, label) for k, label, _ in entries]


# --- 트리 만들기 (순수 함수) ---

def test_tree_nests_folders_and_compacts_single_child_chain():
    changes = [fc("src/easy_GIT/easy_git/app.py"), fc("README.md"), fc("src/easy_GIT/easy_git/gitio.py")]
    assert _rows(tree_entries(changes, set())) == [
        ("dir:unstaged:src/easy_GIT/easy_git", "▾ src/easy_GIT/easy_git/"),
        ("unstaged:src/easy_GIT/easy_git/app.py", "  M app.py  +1 -0"),
        ("unstaged:src/easy_GIT/easy_git/gitio.py", "  M gitio.py  +1 -0"),
        ("unstaged:README.md", "M README.md  +1 -0"),
    ]


def test_tree_folders_before_files_and_no_compaction_when_folder_has_files():
    changes = [fc("a/y.txt"), fc("a/b/x.txt")]
    assert _rows(tree_entries(changes, set())) == [
        ("dir:unstaged:a", "▾ a/"),
        ("dir:unstaged:a/b", "  ▾ b/"),
        ("unstaged:a/b/x.txt", "    M x.txt  +1 -0"),
        ("unstaged:a/y.txt", "  M y.txt  +1 -0"),
    ]


def test_tree_collapsed_folder_hides_children():
    changes = [fc("a/y.txt"), fc("a/b/x.txt"), fc("z.txt")]
    assert _rows(tree_entries(changes, {"dir:unstaged:a"})) == [
        ("dir:unstaged:a", "▸ a/"),
        ("unstaged:z.txt", "M z.txt  +1 -0"),
    ]


def test_tree_rename_shows_old_path():
    [(_, label, _)] = tree_entries([fc("b.txt", status="R", old_path="old/a.txt")], set())
    assert label == "R b.txt ← old/a.txt  +1 -0"


def test_working_entries_builds_one_tree_per_group():
    entries = working_entries([fc("a/s.txt", group="staged")], [fc("a/u.txt")], set())
    assert [k for k, _, _ in entries] == [None, "dir:staged:a", "staged:a/s.txt", None, "dir:unstaged:a", "unstaged:a/u.txt"]


def test_pick_skips_folders_when_no_exact_match():
    ids = [None, "dir:unstaged:a", "unstaged:a/u.txt"]
    assert pick(ids, None, None) == 2
    assert pick(ids, "dir:unstaged:a", None) == 1


# --- 화면 동작 ---

def _repo_with_folder(repo):
    write(repo, "src/a.py", "a\n"); write(repo, "src/b.py", "b\n"); write(repo, "top.txt", "t\n")
    git(repo, "add", "."); git(repo, "commit", "-m", "c1")
    write(repo, "src/a.py", "a2\n"); write(repo, "src/b.py", "b2\n"); write(repo, "top.txt", "t2\n")


def _highlight(files, option_id):
    files.highlighted = files.get_option_index(option_id)


def test_enter_and_arrows_collapse_and_expand_folder(repo):
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            files = app.query_one("#files", OptionList)
            files.focus(); _highlight(files, "dir:unstaged:src"); await settle(app, pilot)
            await pilot.press("enter"); await settle(app, pilot)
            assert "▸ src/" in _prompts(files) and "unstaged:src/a.py" not in app._files
            assert files.highlighted_option.id == "dir:unstaged:src"
            await pilot.press("right"); await settle(app, pilot)
            assert "unstaged:src/a.py" in app._files
            _highlight(files, "unstaged:src/b.py"); await settle(app, pilot)
            await pilot.press("left"); await settle(app, pilot)  # 파일에서 ← → 부모 폴더를 접고 그 폴더로
            assert files.highlighted_option.id == "dir:unstaged:src" and "▸ src/" in _prompts(files)

    asyncio.run(run())


def test_collapsed_folder_survives_reload_and_highlighting_folder_keeps_diff(repo):
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            files = app.query_one("#files", OptionList)
            diff_before = app.query_one("#diff").source
            files.focus(); _highlight(files, "dir:unstaged:src"); await settle(app, pilot)
            assert app.query_one("#diff").source == diff_before
            await pilot.press("enter"); await settle(app, pilot)
            app.reload(); await settle(app, pilot)
            assert "▸ src/" in _prompts(files)

    asyncio.run(run())


def test_space_on_folder_stages_every_file_in_it(repo):
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            files = app.query_one("#files", OptionList)
            files.focus(); _highlight(files, "dir:unstaged:src"); await settle(app, pilot)
            await pilot.press("space"); await settle(app, pilot)
            staged, unstaged = working_changes(repo)
            assert sorted(f.path for f in staged) == ["src/a.py", "src/b.py"]
            assert [f.path for f in unstaged] == ["top.txt"]

    asyncio.run(run())


def test_long_commit_title_stays_on_one_line(repo):
    write(repo, "a.txt", "1\n"); git(repo, "add", "."); git(repo, "commit", "-m", "아주 " * 60)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(100, 40)) as pilot:
            await settle(app, pilot)
            commits_list = app.query_one("#commits", OptionList)
            # 옵션 하나가 화면 한 줄: 넘어가면 그려진 높이가 옵션 수보다 커진다
            assert commits_list.virtual_size.height == commits_list.option_count == 2

    asyncio.run(run())


def test_splitters_draw_no_text(repo):
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            assert "Splitter" not in app.export_screenshot()  # 화면 그림(SVG)에 위젯 이름 글자가 없어야 한다

    asyncio.run(run())


# --- 마우스로 칸 크기 조절 ---

async def _drag(pilot, selector, dx, dy):
    # 실제 터미널처럼 화면 기준 좌표로 보낸다 (경계선이 움직인 뒤 그 기준으로 다시 계산되지 않게)
    region = pilot.app.query_one(selector).region
    to = (region.x + dx, region.y + dy)
    await pilot.mouse_down(selector)
    await pilot.hover(None, offset=to)
    await pilot.mouse_up(None, offset=to)


def test_drag_vertical_splitter_changes_left_width_with_minimum(repo):
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            left = app.query_one("#left")
            before = left.size.width
            await _drag(pilot, "#split-v", 20, 0); await pilot.pause()
            assert left.size.width == before + 20
            to_x5 = 5 - app.query_one("#split-v").region.x  # 화면 왼쪽 끝 근처까지 끌기
            await _drag(pilot, "#split-v", to_x5, 0); await pilot.pause()
            assert left.size.width == MIN_LEFT

    asyncio.run(run())


def test_while_dragging_only_guide_line_moves_and_size_applies_on_release(repo):
    # 끄는 동안 칸 크기를 바꾸면 매번 화면 전체를 다시 그려 버벅거린다. 안내선만 움직이고 놓을 때 한 번 반영한다.
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            left, ghost = app.query_one("#left"), app.query_one("#ghost")
            before, sp = left.size.width, app.query_one("#split-v").region
            await pilot.mouse_down("#split-v")
            await pilot.hover(None, offset=(sp.x + 20, sp.y + 3)); await pilot.pause()
            assert left.size.width == before
            assert ghost.display and ghost.region.x == sp.x + 20 and ghost.region.height == sp.height
            await pilot.mouse_up(None, offset=(sp.x + 20, sp.y + 3)); await pilot.pause()
            assert not ghost.display and left.size.width == before + 20

    asyncio.run(run())


def _strips_per_guide_step(repo, lines):
    """본문에 lines 줄짜리 파일을 띄우고, 안내선을 본문 위에서 한 칸 옮기는 동안 만들어진 줄(Strip) 수."""
    body = "".join(f"line {i}\n" for i in range(lines))
    write(repo, "f.txt", body); git(repo, "add", "."); git(repo, "commit", "-m", f"c{lines}")
    write(repo, "f.txt", body + "more\n")
    made = []

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            sp = app.query_one("#split-v").region
            await pilot.mouse_down("#split-v")
            await pilot.hover(None, offset=(sp.x + 5, sp.y + 3)); await pilot.pause()
            original = strip_mod.Strip.__init__
            strip_mod.Strip.__init__ = lambda self, *a, **k: (made.append(1), original(self, *a, **k))[1]
            try:
                await pilot.hover(None, offset=(sp.x + 6, sp.y + 3)); await pilot.pause()
            finally:
                strip_mod.Strip.__init__ = original
            await pilot.mouse_up(None, offset=(sp.x + 6, sp.y + 3))

    asyncio.run(run())
    return len(made)


def test_guide_line_over_diff_costs_the_same_for_big_files(repo):
    # 안내선이 본문 위를 지날 때 파일 전체를 다시 그리면 큰 파일에서 버벅거린다. 보이는 줄만 그려야 한다.
    small = _strips_per_guide_step(repo, 30)
    big = _strips_per_guide_step(repo, 3000)
    assert big < small * 1.5, (small, big)


def test_drag_horizontal_splitter_changes_commit_list_height(repo):
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            commits_list = app.query_one("#commits")
            before = commits_list.size.height
            await _drag(pilot, "#split-h", 0, -5); await pilot.pause()
            assert commits_list.size.height == before - 5

    asyncio.run(run())


def test_dragged_width_is_kept_across_narrow_layout(repo):
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            left = app.query_one("#left")
            await _drag(pilot, "#split-v", 10, 0); await pilot.pause()
            dragged = left.size.width
            await pilot.resize_terminal(70, 30); await settle(app, pilot)
            assert left.size.width == 70 and app.query_one("#split-v").display is False
            await pilot.resize_terminal(200, 50); await settle(app, pilot)
            assert left.size.width == dragged

    asyncio.run(run())


# --- 상태 글자 색 ---

def test_status_letter_is_colored_by_kind():
    from easy_git.app import STATUS_COLORS, status_prompt
    for status, path in (("M", "a/app.py"), ("A", "new.py"), ("D", "old.py"), ("R", "b.py")):
        label = "  " + f"{status} {path.split('/')[-1]}  +1 -0"
        text = status_prompt(label, fc(path, status=status))
        assert str(text) == label
        assert [(s.start, s.end, str(s.style)) for s in text.spans] == [(2, 3, STATUS_COLORS[status])]
    assert status_prompt("▾ src/", None).spans == []  # 폴더·묶음 제목은 색 없음


def test_file_list_shows_colored_status_letters(repo):
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            files = app.query_one("#files", OptionList)
            prompt = files.get_option("unstaged:src/a.py").prompt
            assert any(str(s.style) == "#E2C08D" for s in prompt.spans)

    asyncio.run(run())


def test_key_menu_labels_are_english():
    from easy_git.app import CommitScreen, ResultScreen
    labels = [b.description for cls in (EasyGitApp, CommitScreen, ResultScreen) for b in cls.BINDINGS]
    assert labels and all(label.isascii() for label in labels), labels


def test_screen_text_has_no_korean(repo):
    # 화면 글은 영어로: 묶음 제목, 작업 중인 변경, 빈 본문 안내 등
    import re
    _repo_with_folder(repo)

    async def run():
        app = EasyGitApp(repo)
        async with app.run_test(size=(200, 50)) as pilot:
            await settle(app, pilot)
            assert not re.search("[\uac00-\ud7a3]", app.export_screenshot())

    asyncio.run(run())
