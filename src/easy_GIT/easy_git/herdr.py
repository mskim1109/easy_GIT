"""Herdr 에 묻기(easy_GIT --follow 용). file_viewer.herdr_right.focused_cwd 와 같은 일을 한다."""
import json
import os
import subprocess
from pathlib import Path


def focused_cwd() -> Path | None:
    """Herdr 에서 지금 포커스된 칸의 폴더. Herdr 가 없거나 답이 이상하면 None."""
    # HERDR_PANE_ID 가 있으면 Herdr 는 포커스된 칸이 아니라 그 칸(이 창을 띄운 칸)으로 답한다
    env = {k: v for k, v in os.environ.items() if k != "HERDR_PANE_ID"}
    try:
        out = subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), "pane", "current"], capture_output=True,
                             check=True, env=env, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        return Path(json.loads(out.stdout.decode("utf-8"))["result"]["pane"]["cwd"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
