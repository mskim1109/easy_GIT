"""파일 읽기·저장·종류 판별. 원래 인코딩과 줄 끝을 지킨다."""
import codecs
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Kind = Literal["code", "md", "html", "binary"]

BIG_FILE = 2_000_000  # 바이트. 넘으면 강조 없이 보여준다.
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".pdf",
              ".zip", ".7z", ".exe", ".dll", ".pyd", ".so"}
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")


@dataclass(frozen=True)
class Loaded:
    text: str  # 줄 끝은 \n 으로 통일. 바이너리면 "".
    encoding: Literal["utf-8", "utf-8-sig", "cp949"]
    newline: Literal["\r\n", "\n"]
    editable: bool
    binary: bool


def load(path: Path) -> Loaded:
    data = path.read_bytes()
    if path.suffix.lower() in BINARY_EXT or b"\x00" in data[:8192]:
        return Loaded("", "utf-8", "\n", False, True)
    tries = (["utf-8-sig"] if data.startswith(codecs.BOM_UTF8) else []) + ["utf-8", "cp949"]
    for enc in tries:
        try:
            text, editable = data.decode(enc), True
            break
        except UnicodeDecodeError:
            pass
    else:
        enc, text, editable = "utf-8", data.decode("utf-8", errors="replace"), False
    # ponytail: 섞인 줄 끝은 첫 판단으로 통일, 섞인 파일이 문제 되면 줄별 보존
    newline = "\r\n" if "\r\n" in text else "\n"
    return Loaded(text.replace("\r\n", "\n"), enc, newline, editable, False)


def save(path: Path, text: str, like: Loaded) -> None:
    path.write_bytes(text.replace("\n", like.newline).encode(like.encoding))


def kind_of(path: Path, loaded: Loaded) -> Kind:
    if loaded.binary:
        return "binary"
    ext = path.suffix.lower()
    if ext in (".md", ".markdown"):
        return "md"
    if ext in (".html", ".htm"):
        return "html"
    return "code"


def stat_key(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return st.st_mtime_ns, st.st_size


def md_for_view(text: str) -> str:
    return _IMAGE.sub(lambda m: f"[그림: {m[1]}]" if m[1] else "[그림]", text)
