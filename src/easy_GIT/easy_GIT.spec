# easy_GIT 을 exe 로 묶는다(폴더 방식). 저장소 최상위에서 PowerShell 로:
#   uv run --project src/easy_GIT --with pyinstaller pyinstaller src/easy_GIT/easy_GIT.spec --noconfirm --distpath D:\Tools --workpath "$env:TEMP\eg-build"
# 결과(D:\Tools\easy_GIT\): easy_GIT.exe(콘솔). git 은 그 PC 의 PATH 에 있어야 한다.
import os

from PyInstaller.utils.hooks import collect_submodules

# textual 위젯과 pygments 문법 강조기는 실행 중에 불러오므로 빌드가 스스로 찾지 못한다
hidden = collect_submodules("textual") + collect_submodules("pygments")

main = Analysis([os.path.join(SPECPATH, "easy_git", "__main__.py")], pathex=[SPECPATH], hiddenimports=hidden)
main_exe = EXE(PYZ(main.pure), main.scripts, exclude_binaries=True, name="easy_GIT", console=True)
COLLECT(main_exe, main.binaries, main.datas, name="easy_GIT")
