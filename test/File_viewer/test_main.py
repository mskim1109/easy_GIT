import file_viewer.herdr_right as herdr_right
import file_viewer.shellops as shellops
from file_viewer.__main__ import main
from file_viewer.app import FileViewerApp


def test_main_missing_dir_waits_for_enter(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("builtins.input", lambda prompt="": calls.append(prompt) or "")
    assert main([str(tmp_path / "없음")]) == 1
    assert "폴더가 아닙니다" in capsys.readouterr().out and len(calls) == 1


def test_main_runs_app_on_given_dir_and_routes_right_click(tmp_path, monkeypatch):
    seen, clicks = [], []
    monkeypatch.setattr(FileViewerApp, "run", lambda self, *a, **k: seen.append(self.root))
    monkeypatch.setattr(shellops, "set_right_click", lambda t: clicks.append(t))
    sub = tmp_path / "하위"; sub.mkdir()
    assert main([str(sub)]) == 0
    assert seen == [sub.resolve()] and clicks == ["pane", "herdr"]


def test_main_follow_starts_at_focused_pane_and_leaves_right_click(tmp_path, monkeypatch):
    seen, clicks = [], []
    monkeypatch.setattr(FileViewerApp, "run", lambda self, *a, **k: seen.append((self.root, self.follow)))
    monkeypatch.setattr(shellops, "set_right_click", lambda t: clicks.append(t))
    monkeypatch.setattr(herdr_right, "focused_cwd", lambda: tmp_path)
    assert main(["--follow"]) == 0
    assert seen == [(tmp_path.resolve(), True)] and clicks == []  # 따로 뜬 창은 Herdr 칸이 아니다
