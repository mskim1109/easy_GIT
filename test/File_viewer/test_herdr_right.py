import json
import subprocess
import sys

import file_viewer.herdr_right as herdr_right


def test_splits_the_pressed_pane_right_and_runs_viewer_there(monkeypatch):
    calls = []
    replies = {
        "current": {"result": {"pane": {"pane_id": "w1:p1", "cwd": "D:\\한글"}}},
        "split": {"result": {"pane": {"pane_id": "w1:p9"}}},
        "run": None,  # 실제 herdr pane run 은 성공해도 아무것도 출력하지 않는다
    }
    def fake_run(args, **k):
        calls.append(args)
        reply = replies[args[2]]
        return subprocess.CompletedProcess(args, 0, b"" if reply is None else json.dumps(reply).encode("utf-8"), b"")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("HERDR_BIN_PATH", "C:\\h\\herdr.exe")
    monkeypatch.setattr(sys, "executable", "C:\\v\\Scripts\\pythonw.exe")
    assert herdr_right.main() == 0
    assert calls == [
        ["C:\\h\\herdr.exe", "pane", "current"],
        ["C:\\h\\herdr.exe", "pane", "split", "--pane", "w1:p1", "--direction", "right", "--cwd", "D:\\한글", "--focus"],
        # 새 칸의 셸(PowerShell)에서 띄우고, q 로 끝나면 셸도 끝내 칸을 닫는다
        ["C:\\h\\herdr.exe", "pane", "run", "w1:p9", "& 'C:\\v\\Scripts\\File_viewer.exe'; exit"],
    ]
