import sys
from pathlib import Path

from easy_git.app import EasyGitApp
from easy_git.gitio import repo_root


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else Path.cwd()
    root = repo_root(path)
    if root is None:
        print(f"Not a git repository: {path}")
        # Herdr 의 type = "pane" 칸은 프로그램이 끝나면 바로 닫혀서, 안내를 읽을 수 있게 기다린다
        input("Press Enter to close...")
        return 1
    EasyGitApp(root).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
