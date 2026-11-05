"""easy_GIT [--follow] [경로] — 경로(없으면 현재 폴더)가 든 git 저장소를 연다.

--follow: 따로 뜬 창(다른 모니터)용. Herdr 에서 포커스된 칸의 저장소로 시작하고, 칸을 옮기면 따라간다.
"""
import sys
from pathlib import Path

from easy_git import herdr
from easy_git.app import EasyGitApp
from easy_git.gitio import repo_root


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    follow = "--follow" in args
    if follow:
        args.remove("--follow")
    path = Path(args[0]) if args else (follow and herdr.focused_cwd()) or Path.cwd()
    root = repo_root(path)
    if root is None:
        print(f"Not a git repository: {path}")
        # Herdr 의 type = "pane" 칸은 프로그램이 끝나면 바로 닫혀서, 안내를 읽을 수 있게 기다린다
        input("Press Enter to close...")
        return 1
    EasyGitApp(root, follow=follow).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
