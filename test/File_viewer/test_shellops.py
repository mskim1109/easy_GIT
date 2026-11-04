import subprocess
import sys

import pytest

import file_viewer.shellops as shellops
from file_viewer.shellops import copy_text, open_browser, reveal, set_right_click

from conftest import write


def _get_clipboard() -> str:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        capture_output=True, check=True).stdout.decode("utf-8")
    return out.removesuffix("\r\n")


def test_reveal_file_and_dir(tmp_path, monkeypatch):
    calls = []; monkeypatch.setattr(subprocess, "Popen", lambda args, **k: calls.append(args))
    f = write(tmp_path, "한글/설정.txt", "x")
    reveal(f); reveal(f.parent)
    assert calls == [["explorer", f"/select,{f}"], ["explorer", str(f.parent)]]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 클립보드")
def test_copy_text_round_trip_korean():
    # 사용자 클립보드를 덮어쓴다. 테스트가 끝나면 원래 값으로 되돌린다.
    old = _get_clipboard()
    try:
        copy_text("D:\\한글\\설정.txt")
        assert _get_clipboard() == "D:\\한글\\설정.txt"
    finally:
        copy_text(old)


def test_open_browser_uses_http_default_not_file_association(tmp_path, monkeypatch):
    calls = []; monkeypatch.setattr(subprocess, "Popen", lambda args, **k: calls.append(args))
    monkeypatch.setattr(shellops, "_browser_command", lambda: '"C:\\Edge\\msedge.exe" --single-argument %1')
    p = write(tmp_path, "보기.html", "<p>x</p>")
    open_browser(p)
    assert calls == ['"C:\\Edge\\msedge.exe" --single-argument ' + p.as_uri()]


def test_set_right_click_only_inside_herdr(monkeypatch):
    calls = []; monkeypatch.setattr(subprocess, "run", lambda args, **k: calls.append(args))
    monkeypatch.delenv("HERDR_ENV", raising=False)
    set_right_click("pane"); assert calls == []
    monkeypatch.setenv("HERDR_ENV", "1"); monkeypatch.setenv("HERDR_PANE_ID", "w1:p2"); monkeypatch.setenv("HERDR_BIN_PATH", "C:\\h\\herdr.exe")
    set_right_click("pane")
    assert calls == [["C:\\h\\herdr.exe", "pane", "input", "--pane", "w1:p2", "--right-click", "pane"]]
