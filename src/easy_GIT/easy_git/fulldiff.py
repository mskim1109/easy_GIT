"""git full-context diff 텍스트를 화면용 행 목록으로 바꾸는 순수 함수."""

import re
from dataclasses import dataclass
from itertools import zip_longest
from typing import Literal

HUNK = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class Row:
    kind: Literal["same", "add", "del"]
    old_no: int | None
    new_no: int | None
    text: str


@dataclass(frozen=True)
class SideRow:
    left_no: int | None
    left: str | None
    right_no: int | None
    right: str | None
    kind: Literal["same", "add", "del", "change"]


def parse_unified(diff_text: str) -> list[Row]:
    rows: list[Row] = []
    old = new = None
    for line in diff_text.split("\n"):
        if line.startswith("@@"):
            m = HUNK.match(line)
            old, new = int(m[1]), int(m[2])
            continue
        if old is None or not line:
            continue
        mark, text = line[0], line[1:].removesuffix("\r")
        if mark == " ":
            rows.append(Row("same", old, new, text))
            old += 1
            new += 1
        elif mark == "-":
            rows.append(Row("del", old, None, text))
            old += 1
        elif mark == "+":
            rows.append(Row("add", None, new, text))
            new += 1
    return rows


def side_rows(rows: list[Row]) -> list[SideRow]:
    out: list[SideRow] = []
    dels: list[Row] = []
    adds: list[Row] = []

    def flush() -> None:
        for d, a in zip_longest(dels, adds):
            if d is not None and a is not None:
                out.append(SideRow(d.old_no, d.text, a.new_no, a.text, "change"))
            elif d is not None:
                out.append(SideRow(d.old_no, d.text, None, None, "del"))
            else:
                out.append(SideRow(None, None, a.new_no, a.text, "add"))
        dels.clear()
        adds.clear()

    for r in rows:
        if r.kind == "same":
            flush()
            out.append(SideRow(r.old_no, r.text, r.new_no, r.text, "same"))
        else:
            (dels if r.kind == "del" else adds).append(r)
    flush()
    return out


def change_starts(changed: list[bool]) -> list[int]:
    return [i for i, c in enumerate(changed) if c and (i == 0 or not changed[i - 1])]
