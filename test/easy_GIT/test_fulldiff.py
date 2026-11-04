from easy_git.fulldiff import Row, SideRow, parse_unified, side_rows, change_starts

SAMPLE = (
    "diff --git a/app/config.py b/app/config.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/app/config.py\n"
    "+++ b/app/config.py\n"
    "@@ -1,6 +1,6 @@\n"
    " import os\n"
    "-import sys\n"
    " import json\n"
    " \n"
    "-DEFAULT_PORT = 8080\n"
    "+DEFAULT_PORT = 9090\n"
    "+# 포트 설명\n"
    " def main():\n"
    "\\ No newline at end of file\n"
)

ROWS = [
    Row("same", 1, 1, "import os"),
    Row("del", 2, None, "import sys"),
    Row("same", 3, 2, "import json"),
    Row("same", 4, 3, ""),
    Row("del", 5, None, "DEFAULT_PORT = 8080"),
    Row("add", None, 4, "DEFAULT_PORT = 9090"),
    Row("add", None, 5, "# 포트 설명"),
    Row("same", 6, 6, "def main():"),
]

def test_parse_unified_full_file():
    assert parse_unified(SAMPLE) == ROWS

def test_parse_unified_strips_cr_and_handles_empty():
    assert parse_unified("@@ -1 +1 @@\n-a\r\n+b\r\n") == [Row("del", 1, None, "a"), Row("add", None, 1, "b")]
    assert parse_unified("") == []

def test_side_rows_pairs_del_and_add_runs():
    assert side_rows(ROWS) == [
        SideRow(1, "import os", 1, "import os", "same"),
        SideRow(2, "import sys", None, None, "del"),
        SideRow(3, "import json", 2, "import json", "same"),
        SideRow(4, "", 3, "", "same"),
        SideRow(5, "DEFAULT_PORT = 8080", 4, "DEFAULT_PORT = 9090", "change"),
        SideRow(None, None, 5, "# 포트 설명", "add"),
        SideRow(6, "def main():", 6, "def main():", "same"),
    ]

def test_change_starts():
    assert change_starts([r.kind != "same" for r in ROWS]) == [1, 4]
    assert change_starts([s.kind != "same" for s in side_rows(ROWS)]) == [1, 4]
    assert change_starts([]) == []
