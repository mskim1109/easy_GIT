# File_viewer 를 exe 로 묶는다(폴더 방식). 저장소 최상위에서 PowerShell 로:
#   uv run --project src/File_viewer --with pyinstaller pyinstaller src/File_viewer/File_viewer.spec --noconfirm --distpath D:\Tools --workpath "$env:TEMP\fv-build"
# 결과(D:\Tools\File_viewer\): File_viewer.exe(콘솔, 본체) + File_viewer_right.exe(창 없음, prefix+alt+f 칸 나누기).
# 두 exe 는 같은 폴더에 있어야 한다. File_viewer_right 가 옆의 File_viewer.exe 를 띄운다(herdr_right.py).
import os

from PyInstaller.utils.hooks import collect_submodules

# textual 위젯과 pygments 문법 강조기는 실행 중에 불러오므로 빌드가 스스로 찾지 못한다
hidden = collect_submodules("textual") + collect_submodules("pygments")

main = Analysis([os.path.join(SPECPATH, "file_viewer", "__main__.py")], pathex=[SPECPATH], hiddenimports=hidden)
right = Analysis([os.path.join(SPECPATH, "file_viewer", "herdr_right.py")], pathex=[SPECPATH])

main_exe = EXE(PYZ(main.pure), main.scripts, exclude_binaries=True, name="File_viewer", console=True)
right_exe = EXE(PYZ(right.pure), right.scripts, exclude_binaries=True, name="File_viewer_right", console=False)

COLLECT(main_exe, main.binaries, main.datas, right_exe, right.binaries, right.datas, name="File_viewer")
