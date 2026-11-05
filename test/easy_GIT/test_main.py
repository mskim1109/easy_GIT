from easy_git import herdr
from easy_git.__main__ import main
from easy_git.app import EasyGitApp


def test_main_not_a_repo_waits_for_enter(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("builtins.input", lambda prompt="": calls.append(prompt) or "")
    assert main([str(tmp_path)]) == 1
    assert "Not a git repository" in capsys.readouterr().out and len(calls) == 1


def test_main_opens_repo_root_from_subdir(repo, monkeypatch):
    seen = []
    monkeypatch.setattr(EasyGitApp, "run", lambda self, *a, **k: seen.append(self.repo))
    sub = repo / "x"; sub.mkdir()
    assert main([str(sub)]) == 0 and seen == [repo.resolve()]


def test_main_follow_starts_at_focused_pane_repo(repo, monkeypatch):
    seen = []
    monkeypatch.setattr(EasyGitApp, "run", lambda self, *a, **k: seen.append((self.repo, self.follow)))
    sub = repo / "x"; sub.mkdir()
    monkeypatch.setattr(herdr, "focused_cwd", lambda: sub)
    assert main(["--follow"]) == 0 and seen == [(repo.resolve(), True)]
