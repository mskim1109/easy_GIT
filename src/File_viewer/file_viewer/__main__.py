"""File_viewer [경로] — 경로(없으면 현재 폴더)를 트리 맨 위로 띄운다."""
import sys
from pathlib import Path

import file_viewer.shellops as shellops
from file_viewer.app import FileViewerApp


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    # 저장소 최상위로 올라가지 않는다(설계 §7).
    root = Path(args[0] if args else ".").resolve()
    if not root.is_dir():
        print(f"폴더가 아닙니다: {root}")
        # Herdr type="pane" 칸은 프로그램이 끝나면 바로 닫히므로 안내를 읽을 시간을 준다.
        input("Enter를 누르면 닫습니다...")
        return 1
    shellops.set_right_click("pane")
    try:
        FileViewerApp(root).run()
    finally:
        shellops.set_right_click("herdr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
