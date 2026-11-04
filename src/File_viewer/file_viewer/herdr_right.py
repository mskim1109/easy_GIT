"""prefix+alt+f 용: 누른 칸의 오른쪽을 나눠 그 칸의 폴더로 File_viewer 를 띄운다.

Herdr 0.9.5 의 type="pane" 은 탭 전체를 덮는 임시 칸이라, type="shell" 로 이 모듈을 부른다:
    pythonw.exe -m file_viewer.herdr_right
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def _herdr(*args: str) -> dict:
    out = subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), *args], capture_output=True, check=True,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    text = out.stdout.decode("utf-8").strip()
    return json.loads(text)["result"] if text else {}  # pane run 은 성공해도 출력이 없다


def main() -> int:
    pressed = _herdr("pane", "current")["pane"]
    new = _herdr("pane", "split", "--pane", pressed["pane_id"], "--direction", "right",
                 "--cwd", pressed["cwd"], "--focus")["pane"]
    exe = Path(sys.executable).with_name("File_viewer.exe")
    # ponytail: 새 칸의 셸을 PowerShell 로 가정(이 PC 기본). cmd 로 바뀌면 '"exe" & exit' 로
    _herdr("pane", "run", new["pane_id"], f"& '{exe}'; exit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
