"""바깥으로 넘기기: 탐색기, 클립보드, 기본 프로그램, 브라우저, Herdr 우클릭 설정."""
import os
import subprocess
import webbrowser
import winreg
from pathlib import Path
from typing import Literal


def reveal(path: Path) -> None:
    # explorer 는 늘 종료 코드 1 을 내므로 결과를 보지 않는다.
    subprocess.Popen(["explorer", str(path)] if path.is_dir() else ["explorer", f"/select,{path}"])


def copy_text(text: str) -> None:
    # BOM 을 붙이지 않는다. 붙이면 클립보드에 U+FEFF 가 남는다.
    subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True)


def open_default(path: Path) -> None:
    os.startfile(path)


def _browser_command() -> str:
    """http 기본 브라우저의 실행 줄(예: "...msedge.exe" --single-argument %1)."""
    choice = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, choice) as k:
        prog_id = winreg.QueryValueEx(k, "ProgId")[0]
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as k:
        return winreg.QueryValueEx(k, "")[0]


def open_browser(path: Path) -> None:
    """.html 의 파일 연결이 아니라 http 기본 브라우저로 연다."""
    try:
        command = _browser_command()
    except OSError:
        webbrowser.open(path.as_uri())
        return
    subprocess.Popen(command.replace("%1", path.as_uri()))


def set_right_click(target: Literal["pane", "herdr"]) -> None:
    """Herdr 칸 안에서만 우클릭을 이 프로그램(pane) 또는 Herdr 메뉴(herdr)로 보낸다."""
    pane_id = os.environ.get("HERDR_PANE_ID")
    if os.environ.get("HERDR_ENV") != "1" or not pane_id:
        return
    try:
        subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), "pane", "input", "--pane", pane_id,
                        "--right-click", target], capture_output=True, timeout=5)
    except Exception:  # 우클릭 설정이 안 돼도 앱은 돈다(메뉴는 m 키로).
        pass
