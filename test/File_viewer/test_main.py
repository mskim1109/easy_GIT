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
