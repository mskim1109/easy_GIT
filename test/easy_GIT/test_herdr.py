import json
import subprocess
from pathlib import Path

from easy_git import herdr


def test_focused_cwd_asks_without_own_pane_id(monkeypatch):
    seen = {}
    def fake_run(args, **k):
        seen["args"], seen["env"] = args, k.get("env")
        return subprocess.CompletedProcess(args, 0, json.dumps({"result": {"pane": {"cwd": "D:\\일"}}}).encode("utf-8"), b"")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")  # 있으면 Herdr 가 포커스된 칸이 아니라 이 칸으로 답한다
    assert herdr.focused_cwd() == Path("D:\\일")
    assert seen["args"][1:] == ["pane", "current"] and "HERDR_PANE_ID" not in seen["env"]


def test_focused_cwd_none_when_herdr_fails(monkeypatch):
    def boom(args, **k):
        raise FileNotFoundError(args[0])
    monkeypatch.setattr(subprocess, "run", boom)
    assert herdr.focused_cwd() is None
