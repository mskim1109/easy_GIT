"""File_viewer [--follow] [경로] — 경로(없으면 현재 폴더)를 트리 맨 위로 띄운다.

--follow: 따로 뜬 창(다른 모니터)용. Herdr 에서 포커스된 칸의 폴더로 시작하고, 칸을 옮기면 따라간다.
"""
import sys
from pathlib import Path

import file_viewer.herdr_right as herdr_right
import file_viewer.shellops as shellops
from file_viewer.app import FileViewerApp


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    follow = "--follow" in args
    if follow:
        args.remove("--follow")
    start = args[0] if args else (follow and herdr_right.focused_cwd()) or "."
    # 저장소 최상위로 올라가지 않는다(설계 §7).
    root = Path(start).resolve()
    if not root.is_dir():
        print(f"폴더가 아닙니다: {root}")
        # Herdr type="pane" 칸은 프로그램이 끝나면 바로 닫히므로 안내를 읽을 시간을 준다.
        input("Enter를 누르면 닫습니다...")
        return 1
    if follow:  # 따로 뜬 창은 Herdr 칸이 아니다. 물려받은 HERDR_PANE_ID 칸의 우클릭을 건드리지 않는다
        FileViewerApp(root, follow=True).run()
        return 0
    shellops.set_right_click("pane")
    try:
        FileViewerApp(root).run()
    finally:
        shellops.set_right_click("herdr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
