# File_viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Herdr 오른쪽 칸에 늘 켜 두는 터미널 파일 뷰어를 만든다. 트리 + 탭으로 코드·json·md를 보고, HTML은 브라우저로 넘기고, 우클릭 메뉴와 간단한 편집을 지원한다.

**Architecture:**
- 순수 로직은 세 모듈로 나눈다.
  - `files`: 읽기·저장·종류 판별, 인코딩과 줄 끝 보존
  - `gitstate`: `git status` → `M`/`+`/흐림
  - `shellops`: 탐색기, 클립보드, 기본 프로그램, 브라우저, Herdr 우클릭 설정
- 화면은 Textual 앱 `app`이 맡는다. 트리는 Textual `DirectoryTree`를 상속한 `FileTree`, 탭 한 장은 `viewer.FileTab`이다.
- 자동 새로 고침은 1초마다 열린 탭의 `stat`, 펼친 폴더 목록, git 상태를 비교하는 폴링으로 한다.

**Tech Stack:** Python 3.12, Textual 8.2.8(rich, pygments, markdown-it-py 포함), pytest 9, uv, git 2.53

**Spec:** `docs/design/2026-11-04-file-viewer-design.md`

## Global Constraints

- **의존성:** Python `>=3.12`. 런타임 의존성은 `textual>=8.2,<9` 하나뿐이다. 문법 강조는 rich `Syntax`(pygments)를 쓴다. `textual[syntax]`(tree-sitter)는 더하지 않는다. pytest는 dev 그룹에만 둔다.
- **위치:** 코드는 `src/File_viewer/file_viewer/`, 테스트는 `test/File_viewer/`, 문서는 `docs/design/`에 둔다. 실행 명령은 `File_viewer`다. easy_GIT 코드는 import하지 않는다.
- **git:** git CLI(subprocess)로 **읽기만** 한다. 모든 git 호출에 환경 변수 `GIT_OPTIONAL_LOCKS=0`을 준다. 저장소 상태를 바꾸는 git 명령은 하나도 쓰지 않는다.
- **디스크 쓰기:** 디스크에 쓰는 동작은 편집 저장(`Ctrl+S`) 하나뿐이다. 사용자가 눌렀을 때만 실행한다. 저장할 때 원래 인코딩(UTF-8 / UTF-8 BOM / CP949)과 줄 끝(CRLF / LF)을 지킨다.
- **문구·한글:** 화면 문구는 한국어다. 한글 경로와 내용(UTF-8 / CP949)이 화면, git 표시, 클립보드, 탐색기 인자 모두에서 깨지지 않아야 한다.
- **실행 환경:** Windows 11 기본 콘솔 창(conhost) 안의 Herdr 0.9.5에서 돈다. Ctrl+V 붙여넣기에 기대지 않는다.
- **테스트:** 저장소 최상위에서 `uv run --project src/File_viewer pytest test/File_viewer -q`로 돌린다.
- **git 커밋:** 이 저장소의 git 커밋 메시지는 맨 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 줄을 붙인다. 작업 브랜치는 이 worktree의 `file_viewer`다. master 변경, push, SVN 명령은 하지 않는다.

## Review Focus

1. **큰 무시 폴더(`node_modules`, `.venv`에 파일 수만 개).** 트리, git 상태, 찾기 어느 것도 그 안을 미리 다 읽지 않아야 한다. git은 무시 폴더를 `dir/` 한 줄로만 돌려줘야 한다. → Task 2 `test_ignored_dir_is_one_entry`, Task 6 `test_find_skips_ignored_dirs`
2. **에이전트가 쓰는 도중에 읽기.** 파일이 잠겨 있거나(`PermissionError`) 반쯤 쓰여 있어도 앱이 살아 있어야 한다. 이전 내용을 유지하고 다음 주기에 다시 읽는다. → Task 7 `test_poll_survives_unreadable_file`
3. **저장이 파일을 망가뜨림.** CP949 + CRLF 파일과 UTF-8 BOM 파일을 고쳐 저장해도 바이트 형식이 그대로여야 한다. → Task 1 `test_save_round_trip_keeps_format`, Task 8 `test_edit_save_keeps_cp949_and_crlf`
4. **한글 경로 전 구간.** `한글/설정.txt`가 트리 표시, `+` 표시, 경로 복사 결과까지 그대로여야 한다. → Task 2 `test_korean_path`, Task 3 `test_copy_text_round_trip_korean`
5. **아주 큰 파일.** 수 MB짜리 로그를 열어도 화면이 멈추지 않아야 한다. 일정 크기를 넘으면 강조 없이 보여준다. → Task 4 `test_big_file_shown_without_highlight`

---

## File Structure

| 파일 | 책임 |
|---|---|
| `src/File_viewer/pyproject.toml` | 패키지 `file-viewer`, 스크립트 `File_viewer = "file_viewer.__main__:main"` |
| `src/File_viewer/file_viewer/__init__.py` | 빈 파일 |
| `src/File_viewer/file_viewer/files.py` | `Loaded`, `load`, `save`, `kind_of`, `stat_key`, `md_for_view`, `find_candidates` (순수) |
| `src/File_viewer/file_viewer/gitstate.py` | `GitState`, `read_state`, `mark`, `dimmed`, `GitError` |
| `src/File_viewer/file_viewer/shellops.py` | `reveal`, `copy_text`, `open_default`, `open_browser`, `set_right_click` |
| `src/File_viewer/file_viewer/viewer.py` | `FileTab(TabPane)`: 보기(코드/md/안내), 편집 상태 |
| `src/File_viewer/file_viewer/app.py` | `FileViewerApp`, `FileTree`, `MenuScreen`, `ConfirmScreen`, `FileProvider`, 배치·키·폴링 |
| `src/File_viewer/file_viewer/__main__.py` | 실행 진입점, 시작 폴더 확인, Herdr 우클릭 설정 |
| `test/File_viewer/conftest.py` | 격리된 임시 git 저장소 fixture `repo`, 헬퍼 `write`, `git`, `settle`, `wait_until` |
| `test/File_viewer/test_files.py`, `test_gitstate.py`, `test_shellops.py`, `test_app.py`, `test_main.py` | 테스트 |

---

### Task 1: 프로젝트 뼈대 + 우클릭 확인 + 파일 읽기·저장

**Files:**
- Create: `src/File_viewer/pyproject.toml`, `src/File_viewer/file_viewer/__init__.py`, `src/File_viewer/file_viewer/files.py`, `test/File_viewer/conftest.py`
- Test: `test/File_viewer/test_files.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Loaded: text: str; encoding: Literal["utf-8","utf-8-sig","cp949"]; newline: Literal["\r\n","\n"]; editable: bool; binary: bool`
    - `text`의 줄 끝은 `\n`으로 통일한다. 바이너리면 `text == ""`다.
  - `Kind = Literal["code","md","html","binary"]`
  - `load(path: Path) -> Loaded` — `OSError`는 그대로 올린다.
  - `save(path: Path, text: str, like: Loaded) -> None`
  - `kind_of(path: Path, loaded: Loaded) -> Kind`
  - `stat_key(path: Path) -> tuple[int, int] | None` — `(st_mtime_ns, st_size)`. 파일이 없으면 `None`.
  - `md_for_view(text: str) -> str`
  - `BIG_FILE = 2_000_000` (바이트)
  - conftest: fixture `repo -> Path`, `write(root: Path, rel: str, data: str | bytes) -> Path`, `git(root: Path, *args: str) -> str`, `async settle(app, pilot)`, `async wait_until(pred: Callable[[], bool], app, pilot, timeout: float = 3.0) -> None`

- [ ] **Step 1: 뼈대를 두고 의존성을 설치한다**

  `pyproject.toml`은 `src/easy_GIT/pyproject.toml`과 같은 형식이다. 바꾸는 값은 `name = "file-viewer"`와 `[project.scripts] File_viewer = "file_viewer.__main__:main"` 둘뿐이다.

  `uv sync --project src/File_viewer`를 돌린다.
  기대 결과: `src/File_viewer/.venv`가 생기고 `uv.lock`이 만들어진다. `__main__.py`는 Task 9에서 만든다.

- [ ] **Step 2: Herdr에서 우클릭이 넘어오는지 확인한다** (사용자와 함께. 설계 §4.5 "구현 맨 처음에 확인")

  scratchpad에 아래 확인용 스크립트를 둔다. 저장소에는 넣지 않는다.

  ```python
  from textual.app import App
  from textual.widgets import Static

  class Probe(App):
      BINDINGS = [("q", "quit")]
      def compose(self):
          yield Static("여기서 왼쪽·오른쪽 클릭 (q 종료)", id="s")
      def on_mouse_down(self, e):
          self.query_one("#s").update(f"button={e.button} x={e.x} y={e.y}")

  Probe().run()
  ```

  사용자에게 Herdr에서 오른쪽 칸을 하나 열어 달라고 한다. 그 칸에서 다음 두 명령을 차례로 돌린다.
  - `herdr pane input --current --right-click pane`
  - `uv run --project D:\WorkTrees\ADE_sub\file-viewer\src\File_viewer python <스크립트>`

  왼쪽 클릭과 오른쪽 클릭을 한 번씩 하게 하고 화면에 나온 결과를 받는다.
  - 기대 결과: 왼쪽 클릭은 `button=1`, 오른쪽 클릭은 `button=3`.
  - `button=3`이 안 나오면 여기서 멈추지 않는다. 결과를 사용자에게 알리고 계속 진행한다. 메뉴는 Task 6의 `m` 키로 쓸 수 있다.

- [ ] **Step 3: 실패하는 테스트를 쓴다** (`test/File_viewer/test_files.py`)

  ```python
  def test_load_utf8_cp949_bom_and_newline(tmp_path):
      a = write(tmp_path, "a.txt", "가\r\n나\r\n".encode("cp949"))
      b = write(tmp_path, "b.txt", "\ufeff# 제목\n".encode("utf-8"))
      c = write(tmp_path, "c.txt", "x = 1\n".encode("utf-8"))
      assert load(a) == Loaded("가\n나\n", "cp949", "\r\n", True, False)
      assert load(b) == Loaded("# 제목\n", "utf-8-sig", "\n", True, False)
      assert load(c) == Loaded("x = 1\n", "utf-8", "\n", True, False)

  def test_undecodable_is_shown_but_not_editable(tmp_path):
      p = write(tmp_path, "x.txt", b"ok \xff\xfe\xfa end\n")
      got = load(p)
      assert got.editable is False and got.binary is False and "ok" in got.text

  def test_binary_by_nul_or_extension(tmp_path):
      assert load(write(tmp_path, "a.bin", b"ab\x00cd")).binary is True
      assert load(write(tmp_path, "b.pdf", b"%PDF-1.7 text only")).binary is True

  def test_save_round_trip_keeps_format(tmp_path):
      p = write(tmp_path, "a.txt", "가\r\n나\r\n".encode("cp949"))
      save(p, "가\n다\n", load(p))
      assert p.read_bytes() == "가\r\n다\r\n".encode("cp949")
      q = write(tmp_path, "b.md", "\ufeff# 제목\n".encode("utf-8"))
      save(q, "# 새 제목\n", load(q))
      assert q.read_bytes() == "\ufeff# 새 제목\n".encode("utf-8")

  def test_kind_of(tmp_path):
      kinds = {n: kind_of(p := write(tmp_path, n, "x\n"), load(p)) for n in ["a.py", "b.json", "c.md", "d.html", "e.htm", "f.txt"]}
      assert kinds == {"a.py": "code", "b.json": "code", "c.md": "md", "d.html": "html", "e.htm": "html", "f.txt": "code"}
      assert kind_of(p := write(tmp_path, "g.png", b"\x89PNG\x00"), load(p)) == "binary"

  def test_stat_key_and_md_for_view(tmp_path):
      assert stat_key(tmp_path / "없음.txt") is None
      assert md_for_view("앞 ![구조도](a.png) 뒤\n![](b.png)") == "앞 [그림: 구조도] 뒤\n[그림]"
  ```

- [ ] **Step 4: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_files.py -q`
  기대 결과: `ModuleNotFoundError: file_viewer.files`

- [ ] **Step 5: `conftest.py`와 `files.py`를 구현한다**

  **conftest**
  - `repo`: `tmp_path/"repo"`에 `git init -b main`을 돌리고 `user.name`, `user.email`, `core.autocrlf=false`를 설정한다.
  - 이 fixture는 monkeypatch로 `GIT_CONFIG_GLOBAL=os.devnull`, `GIT_CONFIG_NOSYSTEM=1`을 걸어 사용자 git 설정의 영향을 막는다.
  - `write`는 부모 폴더를 만들고, `str`이면 UTF-8로, `bytes`이면 그대로 쓴다.
  - `settle`은 `await app.workers.wait_for_complete(); await pilot.pause()`를 두 번 실행한다.
  - `wait_until`은 `pred()`가 참이 될 때까지 `settle`을 반복한다. `timeout`이 지나면 `AssertionError`를 낸다.

  **load**
  1. 확장자가 `BINARY_EXT = {".png",".jpg",".jpeg",".gif",".bmp",".ico",".webp",".pdf",".zip",".7z",".exe",".dll",".pyd",".so"}`에 있거나, 처음 8192바이트에 `\x00`이 있으면 바이너리다. 이때 `Loaded("", "utf-8", "\n", False, True)`를 돌려준다.
  2. 그 밖에는 `utf-8-sig`(BOM이 있을 때만) → `utf-8` → `cp949` 순서로 strict 디코딩을 시도한다.
  3. 셋 다 실패하면 `utf-8`에 `errors="replace"`로 디코딩하고 `editable=False`로 둔다.
  4. `newline`은 원본에 `\r\n`이 있으면 `"\r\n"`이다. `text`는 `\r\n`을 `\n`으로 바꾼 것이다.
  5. 줄 끝이 섞인 파일은 저장할 때 전부 한 가지로 바뀐다. `# ponytail: 섞인 줄 끝은 첫 판단으로 통일, 섞인 파일이 문제 되면 줄별 보존` 주석을 단다.

  **save:** `text.replace("\n", like.newline).encode(like.encoding)`을 쓴다.

  **kind_of:** binary → `"binary"`, `.md`/`.markdown` → `"md"`, `.html`/`.htm` → `"html"`, 나머지는 `"code"`.

  **md_for_view:** 정규식 `!\[([^\]]*)\]\([^)]*\)`를 쓴다. 설명이 있으면 `[그림: 설명]`, 비어 있으면 `[그림]`으로 바꾼다.

- [ ] **Step 6: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_files.py -q`
  기대 결과: `6 passed`

- [ ] **Step 7: 커밋한다**

  `git add src/File_viewer test/File_viewer docs/design/2026-11-04-file-viewer-design.md docs/design/2026-11-04-file-viewer-plan.md`
  `git commit -m "feat(File_viewer): 프로젝트 뼈대와 파일 읽기·저장" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 2: git 상태 — `M` / `+` / 흐림

**Files:**
- Create: `src/File_viewer/file_viewer/gitstate.py`
- Test: `test/File_viewer/test_gitstate.py`

**Interfaces:**
- Produces:
  - `class GitError(Exception)` — git 실행 실패(lock 등). 폴링이 삼킨다.
  - `@dataclass(frozen=True) class GitState: modified: frozenset[str]; untracked: frozenset[str]; ignored: frozenset[str]; changed_dirs: frozenset[str]`
    - 경로는 모두 시작 폴더 기준 상대 경로이고 `/`로 구분한다.
    - 폴더 항목은 끝에 `/`가 붙는다(`"d/"`).
    - `changed_dirs`는 modified·untracked 항목의 모든 조상 폴더다(끝 `/` 없음).
  - `read_state(root: Path) -> GitState | None` — git 저장소가 아니거나 git이 없으면 `None`, 그 밖의 실패는 `GitError`.
  - `mark(state: GitState | None, rel: str, is_dir: bool) -> Literal["M", "+", "•", ""]`
  - `dimmed(state: GitState | None, rel: str) -> bool`

- [ ] **Step 1: 실패하는 테스트를 쓴다** (`test/File_viewer/test_gitstate.py`)

  ```python
  def _base(repo):
      write(repo, "a/b.txt", "1\n"); write(repo, "c.txt", "1\n")
      write(repo, ".gitignore", ".venv/\n*.log\n")
      git(repo, "add", "."); git(repo, "commit", "-m", "init")

  def test_modified_untracked_and_folder_mark(repo):
      _base(repo)
      write(repo, "a/b.txt", "2\n"); write(repo, "d/e.txt", "new\n"); write(repo, "f.txt", "new\n")
      s = read_state(repo)
      assert [mark(s, "a/b.txt", False), mark(s, "a", True), mark(s, "d", True), mark(s, "d/e.txt", False),
              mark(s, "f.txt", False), mark(s, "c.txt", False)] == ["M", "•", "•", "+", "+", ""]

  def test_staged_and_renamed_count_as_modified(repo):
      _base(repo)
      write(repo, "c.txt", "2\n"); git(repo, "add", "c.txt")
      git(repo, "mv", "a/b.txt", "a/g.txt")
      s = read_state(repo)
      assert mark(s, "c.txt", False) == "M" and mark(s, "a/g.txt", False) == "M"

  def test_ignored_dir_is_one_entry(repo):
      _base(repo)
      for i in range(50): write(repo, f".venv/lib/m{i}.py", "x\n")
      write(repo, "x.log", "x\n")
      s = read_state(repo)
      assert ".venv/" in s.ignored and not any(p.startswith(".venv/lib") for p in s.ignored)
      assert dimmed(s, ".venv") and dimmed(s, ".venv/lib/m1.py") and dimmed(s, "x.log")
      assert dimmed(s, ".git") and dimmed(s, ".git/config") and not dimmed(s, "c.txt")
      assert mark(s, ".venv", True) == ""

  def test_subdir_root_sees_only_its_files(repo):
      _base(repo)
      write(repo, "a/b.txt", "2\n"); write(repo, "c.txt", "2\n")
      assert read_state(repo / "a").modified == {"b.txt"}

  def test_korean_path(repo):
      _base(repo)
      write(repo, "한글/설정.txt", "가\n".encode("cp949"))
      s = read_state(repo)
      assert mark(s, "한글/설정.txt", False) == "+" and mark(s, "한글", True) == "•"

  def test_not_a_repo_and_no_locks(tmp_path, monkeypatch, repo):
      (tmp_path / "plain").mkdir()
      assert read_state(tmp_path / "plain") is None
      assert dimmed(None, ".git") and mark(None, "x", False) == ""
      seen = []
      real = subprocess.run
      monkeypatch.setattr(subprocess, "run", lambda *a, **k: seen.append(k.get("env", {})) or real(*a, **k))
      read_state(repo)
      assert seen and all(e.get("GIT_OPTIONAL_LOCKS") == "0" for e in seen)
  ```

  `tmp_path/"plain"`은 `repo` fixture(`tmp_path/"repo"`)와 형제 폴더다. 그래서 git 저장소가 아니다.

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_gitstate.py -q`
  기대 결과: `ModuleNotFoundError: file_viewer.gitstate`

- [ ] **Step 3: `gitstate.py`를 구현한다**

  **git 호출**
  - 모두 `subprocess.run([...], capture_output=True, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})`로 부른다.
  - 콘솔 창이 뜨지 않게 `creationflags=subprocess.CREATE_NO_WINDOW`를 준다.

  **읽는 순서**
  1. `git -C root rev-parse --show-prefix`
     - 0이 아닌 코드로 끝나거나 `FileNotFoundError`(git 없음)이면 `None`을 돌려준다.
     - 성공하면 출력이 prefix다(예: `"a/"`, 최상위면 `""`).
  2. `git -C root status --porcelain=v1 -z --untracked-files=normal --ignored=matching -- .`
     - 실패하면 `GitError(stderr)`를 낸다.
     - 출력은 UTF-8로 디코딩하고 `\0`으로 나눈다.

  **항목 해석**
  - 각 항목은 `XY 경로`다.
  - X나 Y에 `R`/`C`가 있으면 다음 필드(원래 경로)를 하나 건너뛴다.
  - `??` → untracked, `!!` → ignored, 나머지는 modified다.
  - 경로는 저장소 최상위 기준이다. prefix로 시작하지 않는 것은 버리고, prefix를 떼어 낸다.
  - `changed_dirs`는 modified와 untracked 각 경로의 모든 조상 폴더다. untracked 폴더(`"d/"`) 자신의 이름도 넣는다.

  **mark**
  - 폴더(`is_dir`)면 `rel in changed_dirs` → `"•"`.
  - 파일이면 다음 순서로 판단한다.
    1. `rel in modified` → `"M"`
    2. `rel in untracked`이거나 조상 폴더 중 하나가 `untracked`에 `"폴더/"`로 있으면 → `"+"`
    3. 그 밖에는 `""`

  **dimmed**
  - `rel == ".git"`이거나 `rel.startswith(".git/")`이면 참이다. `state`가 `None`이어도 그렇다.
  - 그 밖에는 `rel`(파일), `rel + "/"`(폴더), 또는 조상 `"폴더/"` 중 하나가 `ignored`에 있으면 참이다.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_gitstate.py -q`
  기대 결과: `6 passed`

- [ ] **Step 5: 커밋한다**

  `git add src/File_viewer/file_viewer/gitstate.py test/File_viewer/test_gitstate.py`
  `git commit -m "feat(File_viewer): git 상태로 M·+·흐림 계산" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 3: 바깥으로 넘기기 — 탐색기, 클립보드, 기본 프로그램, 브라우저, Herdr 우클릭

**Files:**
- Create: `src/File_viewer/file_viewer/shellops.py`
- Test: `test/File_viewer/test_shellops.py`

**Interfaces:**
- Produces:
  - `reveal(path: Path) -> None` — 파일이면 그 파일을 선택한 탐색기, 폴더면 그 폴더
  - `copy_text(text: str) -> None`
  - `open_default(path: Path) -> None`
  - `open_browser(path: Path) -> None`
  - `set_right_click(target: Literal["pane", "herdr"]) -> None` — Herdr 안(`HERDR_ENV == "1"`이고 `HERDR_PANE_ID`가 있을 때)이 아니면 아무것도 하지 않는다. 실패해도 예외를 내지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다** (`test/File_viewer/test_shellops.py`)

  ```python
  def test_reveal_file_and_dir(tmp_path, monkeypatch):
      calls = []; monkeypatch.setattr(subprocess, "Popen", lambda args, **k: calls.append(args))
      f = write(tmp_path, "한글/설정.txt", "x")
      reveal(f); reveal(f.parent)
      assert calls == [["explorer", f"/select,{f}"], ["explorer", str(f.parent)]]

  @pytest.mark.skipif(sys.platform != "win32", reason="Windows 클립보드")
  def test_copy_text_round_trip_korean():
      # 사용자 클립보드를 덮어쓴다. 테스트가 끝나면 원래 값으로 되돌린다.
      old = _get_clipboard()
      try:
          copy_text("D:\\한글\\설정.txt")
          assert _get_clipboard() == "D:\\한글\\설정.txt"
      finally:
          copy_text(old)

  def test_open_browser_uses_http_default_not_file_association(tmp_path, monkeypatch):
      calls = []; monkeypatch.setattr(subprocess, "Popen", lambda args, **k: calls.append(args))
      monkeypatch.setattr(shellops, "_browser_command", lambda: '"C:\\Edge\\msedge.exe" --single-argument %1')
      p = write(tmp_path, "보기.html", "<p>x</p>")
      open_browser(p)
      assert calls == ['"C:\\Edge\\msedge.exe" --single-argument ' + p.as_uri()]

  def test_set_right_click_only_inside_herdr(monkeypatch):
      calls = []; monkeypatch.setattr(subprocess, "run", lambda args, **k: calls.append(args))
      monkeypatch.delenv("HERDR_ENV", raising=False)
      set_right_click("pane"); assert calls == []
      monkeypatch.setenv("HERDR_ENV", "1"); monkeypatch.setenv("HERDR_PANE_ID", "w1:p2"); monkeypatch.setenv("HERDR_BIN_PATH", "C:\\h\\herdr.exe")
      set_right_click("pane")
      assert calls == [["C:\\h\\herdr.exe", "pane", "input", "--pane", "w1:p2", "--right-click", "pane"]]
  ```

  `_get_clipboard()`는 테스트 파일 안의 헬퍼다. `powershell -NoProfile -Command "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"`를 돌려 UTF-8로 읽고, 끝의 `\r\n`을 떼어 낸다.

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_shellops.py -q`
  기대 결과: `ModuleNotFoundError: file_viewer.shellops`

- [ ] **Step 3: `shellops.py`를 구현한다**

  - **`reveal`:** `subprocess.Popen(["explorer", f"/select,{path}"])`, 폴더면 `["explorer", str(path)]`를 부른다. explorer는 늘 종료 코드 1을 내므로 결과를 보지 않는다.
  - **`copy_text`:** `subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True)`.
    - **BOM을 붙이지 않는다.** 붙이면 클립보드에 U+FEFF가 남는다(2026-11-04 이 PC에서 확인).
  - **`open_default`:** `os.startfile(path)`.
  - **`open_browser`**
    - `_browser_command()`로 실행 줄을 얻는다. 이 함수는 `winreg`로 다음 두 값을 읽는다.
      - `HKCU\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice`의 `ProgId`
      - `HKEY_CLASSES_ROOT\{ProgId}\shell\open\command`의 기본값
      - 이 PC에서는 `"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --single-argument %1`이다.
    - 실행 줄의 `%1`을 `path.as_uri()`로 바꿔 `subprocess.Popen(문자열)`로 실행한다.
    - 레지스트리를 못 읽으면 `webbrowser.open(path.as_uri())`로 대신한다.
  - **`set_right_click`:** `subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), "pane", "input", "--pane", pane_id, "--right-click", target], capture_output=True, timeout=5)`. 예외는 모두 삼킨다.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_shellops.py -q`
  기대 결과: `4 passed`

- [ ] **Step 5: 커밋한다**

  `git add src/File_viewer/file_viewer/shellops.py test/File_viewer/test_shellops.py`
  `git commit -m "feat(File_viewer): 탐색기·클립보드·브라우저로 넘기기" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 4: 트리 + 탭 화면, 파일 종류별 보기

**Files:**
- Create: `src/File_viewer/file_viewer/viewer.py`, `src/File_viewer/file_viewer/app.py`
- Test: `test/File_viewer/test_app.py`

**Interfaces:**
- Consumes: `load`, `kind_of`, `stat_key`, `md_for_view`, `BIG_FILE`, `Loaded` (Task 1), `read_state`, `mark`, `dimmed`, `GitState` (Task 2), `open_default`, `open_browser` (Task 3)
- Produces:
  - `class FileTab(TabPane)` (`viewer.py`)
    - 생성: `__init__(self, path: Path, pane_id: str)`. 제목은 파일 이름이고, html이면 끝에 ` ↗`를 붙인다.
    - 속성:
      - `path: Path`
      - `loaded: Loaded | None`
      - `kind: Kind`
      - `key: tuple[int, int] | None` (마지막으로 읽은 `stat_key`)
      - `md_rendered: bool` (md면 처음에 `True`)
      - `deleted: bool`
      - `editing: bool` (Task 8)
      - `highlighted: bool`: 지금 문법 강조로 그렸는지
      - `notice: str | None`: `#notice`에 띄운 문구
      - `shown_text: str`: `#code`/`#md`에 넘긴 글 (md면 `md_for_view` 결과)
      - 이 세 속성은 위젯 내부를 들여다보지 않고 시험하기 위한 것이다.
    - 위젯: 내용 컨테이너 `#body`(`VerticalScroll`). 그 안에 다음 중 하나를 둔다.
      - `Static#code`: rich `Syntax` 또는 큰 파일용 `Text`
      - `Markdown#md`
      - `Static#notice`: 안내 문구
    - 메서드:
      - `refresh_content(keep_scroll: bool = False) -> None`: 디스크에서 다시 읽어 그린다.
      - `toggle_md() -> None`
  - `class FileTree(DirectoryTree)` (`app.py`)
    - 생성: `__init__(self, root: Path, id: str = "tree")`
    - 속성: `state: GitState | None`
    - 메서드: `set_state(state: GitState | None) -> None` (라벨을 다시 그린다)
  - `class FileViewerApp(App)`
    - 생성: `__init__(self, root: Path, poll_interval: float = 1.0)`. 인자는 `self.root`, `self.poll_interval`로 보관한다.
    - 위젯 id: `#tree`(FileTree), `#tabs`(TabbedContent), 그리고 `Footer`
    - 메서드:
      - `open_file(path: Path) -> None`: 이미 열려 있으면 그 탭으로 가고, 없으면 새 탭을 연다.
      - `open_external(path: Path) -> None`: html이면 `open_browser`, 아니면 `open_default`를 부른다.
    - 속성:
      - `current_tab -> FileTab | None`
      - `tab_ids: dict[Path, str]`: pane id는 `f"t{n}"`이고, n은 1부터 늘어나는 번호다.

- [ ] **Step 1: 실패하는 테스트를 쓴다** (`test/File_viewer/test_app.py`)

  **공통 규칙**
  - 모든 앱 테스트는 `asyncio.run()` 안에서 `async with FileViewerApp(repo).run_test(size=(120, 40)) as pilot`을 쓴다.
  - 비동기 테스트 플러그인은 쓰지 않는다.
  - 일을 시킨 뒤에는 `settle(app, pilot)`으로 기다린다.

  ```python
  def _files(repo):
      write(repo, "config.json", '{\n  "name": "easy-git"\n}\n')
      write(repo, "notes.md", "# 제목\n\n![구조](a.png)\n")
      write(repo, "page.html", "<p>안녕</p>\n")
      write(repo, "logo.png", b"\x89PNG\x00\x00")
      git(repo, "add", "config.json"); git(repo, "commit", "-m", "init")
      write(repo, "config.json", '{\n  "name": "file-viewer"\n}\n')

  def test_open_file_reuses_tab(repo):
      # open_file(repo/"config.json") 두 번 → len(app.tab_ids) == 1, current_tab.kind == "code", '"file-viewer"' in current_tab.loaded.text
      # current_tab.query_one("#code") 가 있다

  def test_enter_in_tree_opens_file(repo):
      # #tree 포커스, config.json 노드로 커서 이동(tree.move_cursor(node)), press("enter") → current_tab.path == repo/"config.json"

  def test_tab_and_w(repo):
      # config.json, page.html 열기 → current_tab.path.name == "page.html"
      # press("tab") → "config.json"; press("shift+tab") → "page.html"; press("w") → len(app.tab_ids) == 1

  def test_md_rendered_then_raw(repo):
      # notes.md 열기 → md_rendered and query_one("#md") 있음, "[그림: 구조]" in current_tab.shown_text
      # press("v") → not md_rendered and query_one("#code") 있음

  def test_html_title_and_o(repo, monkeypatch):
      # monkeypatch shellops.open_browser / open_default 를 기록 함수로
      # page.html 열기 → 탭 제목이 "page.html ↗"; press("o") → open_browser 에 repo/"page.html"
      # notes.md 열기 → press("o") → open_default 에 repo/"notes.md"

  def test_binary_shows_notice(repo):
      # logo.png 열기 → kind == "binary", "미리 볼 수 없는 파일" in current_tab.notice

  def test_big_file_shown_without_highlight(repo, monkeypatch):
      # 기본: config.json 열기 → current_tab.highlighted is True
      # monkeypatch.setattr(files, "BIG_FILE", 10) 뒤 다시 열기(새 탭) → current_tab.highlighted is False

  def test_tree_labels_mark_and_dim(repo):
      # .gitignore 에 ".venv/", .venv/x 생성. 앱이 뜬 뒤
      # config.json 노드 라벨: tree.render_label(node, Style(), Style()).plain.endswith(" M")
      # .venv 노드 라벨의 spans 중 하나가 dim 스타일
  ```

  (노드는 `tree.root.children`에서 `node.data.path.name`으로 찾는다. 단언은 주석에 적힌 그대로 쓴다.)

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_app.py -q`
  기대 결과: `ModuleNotFoundError: file_viewer.app`

- [ ] **Step 3: `viewer.py`를 구현한다**

  - **모듈 함수 부르는 법:** `files`, `gitstate`, `shellops`의 함수와 `files.BIG_FILE`은 `import file_viewer.files as files`처럼 모듈을 가져와 `files.load(...)` 형태로 부른다. 그래야 테스트의 monkeypatch가 먹힌다. `app.py`도 같다.
  - **`refresh_content`**
    - `files.load`가 `OSError`를 내면 그대로 올린다. 폴링이 처리한다(Task 7).
    - 읽기에 성공하면 `key`, `loaded`, `kind`를 갱신하고 `#body` 안을 다음 규칙으로 갈아 끼운다.
  - **binary:** `Static#notice`에 `"미리 볼 수 없는 파일입니다 — o 로 기본 프로그램에서 엽니다"`를 넣는다.
  - **md이고 `md_rendered`:** `Markdown#md`에 `md_for_view(text)`를 넣는다.
  - **그 밖(코드, html, md 원문)**
    - 파일 크기가 `files.BIG_FILE` 이하면 `Static#code`에 `Syntax(text, Syntax.guess_lexer(str(path), text), line_numbers=True, word_wrap=False, theme="monokai")`를 넣고 `highlighted = True`로 둔다.
    - 크면 `Text(text)`를 넣고 `highlighted = False`로 둔다.
    - `#notice`를 쓸 때는 그 문구를 `notice`에, `#code`/`#md`를 쓸 때는 넘긴 글을 `shown_text`에 담는다.
    - `#code`는 CSS `width: auto`로 두어 긴 줄을 가로 스크롤한다.
    - `# ponytail: Static 전체 렌더링. 수만 줄에서 느리면 render_line 기반 ScrollView로` 주석을 단다.
  - **`keep_scroll`:** 참이면 갈아 끼우기 전의 `#body.scroll_y`를 `call_after_refresh`로 되돌린다.
  - **`toggle_md`:** md일 때만 동작한다. `md_rendered`를 뒤집고 다시 그린다.

- [ ] **Step 4: `app.py`를 구현한다**

  - **배치:** `Horizontal(FileTree#tree, TabbedContent#tabs)`에 `Footer`를 더한다. `theme = "nord"`.
    - `#tree`의 너비는 `self.tree_width = 32`(열)이다.
    - 탭이 없을 때 `#tabs`에는 안내 `"왼쪽 트리에서 파일을 고르세요"`를 보여준다.
  - **`FileTree`**
    - `render_label`은 `super()` 결과에 두 가지를 더한다.
      - `dimmed`이면 `stylize("dim")`.
      - `mark`가 있으면 `f" {mark}"`를 덧붙인다. 색은 `M`/`•` `#e2c08d`, `+` `#73c991`이다.
    - 노드의 rel은 `node.data.path.relative_to(root).as_posix()`이고, 루트는 `""`다.
    - `set_state`는 `state`를 바꾸고 줄 캐시를 비운 뒤 `refresh()`한다.
  - **시작할 때:** `read_state(root)`를 thread worker에서 불러 `set_state`한다. `GitError`면 `None`으로 둔다.
  - **트리에서 파일 고르기:** `DirectoryTree.FileSelected`가 오면 `open_file(event.path)`를 부른다.
  - **키 (`BINDINGS`, Footer에 한국어 설명)**

    | 키 | 동작 | Footer 설명 |
    |---|---|---|
    | `tab` / `shift+tab` | 다음/이전 탭 (`priority=True`. Screen의 포커스 이동보다 앞서야 함) | |
    | `w` | 탭 닫기 | |
    | `v` | md 보기 전환 | |
    | `o` | 열기 (`open_external`) | |
    | `q` | 종료 | |

    다음/이전 탭은 `#tabs`의 `Tabs` 위젯의 `action_next_tab` / `action_previous_tab`을 부른다.

- [ ] **Step 5: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer -q`
  기대 결과: 전부 통과

- [ ] **Step 6: 커밋한다**

  `git add src/File_viewer/file_viewer/viewer.py src/File_viewer/file_viewer/app.py test/File_viewer/test_app.py`
  `git commit -m "feat(File_viewer): 트리와 탭, 파일 종류별 보기" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 5: 칸 폭에 따른 배치, 트리 폭 조절

**Files:**
- Modify: `src/File_viewer/file_viewer/app.py`
- Test: `test/File_viewer/test_app.py`

**Interfaces:**
- Consumes: `FileViewerApp` (Task 4)
- Produces:
  - 상수 `NARROW_BELOW = 80`(열), `TREE_MIN = 16`, `TREE_STEP = 4`, `CONTENT_MIN = 30`
  - `FileViewerApp` 속성:
    - `narrow: bool`
    - `tree_shown: bool` (넓을 때 사용자가 고른 값. 처음엔 `True`)
    - `tree_screen: bool` (좁을 때 트리 화면을 보고 있는지)
    - `tree_width: int`

- [ ] **Step 1: 실패하는 테스트를 덧붙인다**

  ```python
  def test_narrow_hides_tree_and_t_switches(repo):
      # size=(60, 30) → app.narrow, not tree.display, tabs.display
      # press("t") → tree.display and not tabs.display; open_file(repo/"config.json") → not tree.display, tabs.display

  def test_resize_switches_layout(repo):
      # size=(120, 40) 에서 tree.display; await pilot.resize_terminal(60, 30); settle → not tree.display
      # await pilot.resize_terminal(120, 40); settle → tree.display

  def test_t_and_brackets_in_wide(repo):
      # press("]") → tree_width == 36; press("[") ×6 → tree_width == 16 (TREE_MIN 에서 멈춤)
      # press("t") → not tree.display (tree_shown False); press("t") → tree.display
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_app.py -q`
  기대 결과: 새 테스트 3개 실패

- [ ] **Step 3: 구현한다**

  - **`apply_layout()`:** `on_resize`와 `t`, `[`, `]`, `open_file` 뒤에 부른다.
    - `narrow = size.width < NARROW_BELOW`
    - 넓을 때
      - `tree.display = tree_shown`, `tabs.display = True`
      - `#tree` 너비 = `tree_width`
    - 좁을 때
      - `tree.display = tree_screen`, `tabs.display = not tree_screen`
      - 트리를 보여줄 때는 `#tree` 너비가 `1fr`이다.
  - **`t`:** 넓으면 `tree_shown`을, 좁으면 `tree_screen`을 뒤집는다. 트리가 보이게 되면 트리에 포커스를 준다.
  - **`[` / `]`:** `tree_width`를 `TREE_STEP`씩 줄이거나 늘린다. 범위는 `[TREE_MIN, size.width - CONTENT_MIN]`이다. 좁을 때는 아무 일도 하지 않는다.
  - **`open_file`:** 좁을 때 열면 `tree_screen = False`로 둔다.
  - `# ponytail: 기준 80열은 짐작. 실제 Herdr 칸에서 보고 조정` 주석을 단다.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer -q`
  기대 결과: 전부 통과

- [ ] **Step 5: 커밋한다**

  `git commit -am "feat(File_viewer): 칸 폭에 따른 배치와 트리 폭 조절" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 6: 파일 이름 찾기(`/`), 우클릭·`m` 메뉴

**Files:**
- Modify: `src/File_viewer/file_viewer/files.py`, `src/File_viewer/file_viewer/app.py`
- Test: `test/File_viewer/test_files.py`, `test/File_viewer/test_app.py`

**Interfaces:**
- Consumes: `reveal`, `copy_text` (Task 3), `FileViewerApp.open_file`, `open_external` (Task 4)
- Produces:
  - `find_candidates(root: Path) -> list[str]` (`files.py`): 시작 폴더 기준 상대 경로이고 `/`로 구분한다.
  - `class FileProvider(Provider)`: Textual 명령 팔레트용
  - `class MenuScreen(ModalScreen[str | None])`
    - 생성: `__init__(self, path: Path)`. 속성 `path`.
    - 옵션 id와 문구: `"reveal"` 탐색기에서 열기, `"copy"` 경로 복사, `"open"` 기본 프로그램으로 열기.
  - `FileViewerApp.open_menu(path: Path) -> None`

- [ ] **Step 1: 실패하는 테스트를 덧붙인다**

  ```python
  # test_files.py
  def test_find_skips_ignored_dirs(repo):
      write(repo, ".gitignore", "node_modules/\n"); write(repo, "docs/design.md", "x")
      write(repo, "node_modules/p/index.js", "x"); write(repo, "새파일.txt", "x")
      got = find_candidates(repo)
      assert "docs/design.md" in got and "새파일.txt" in got and ".gitignore" in got
      assert not any(p.startswith("node_modules/") for p in got)

  def test_find_candidates_without_git(tmp_path):
      write(tmp_path, "plain/a.txt", "x"); write(tmp_path, "plain/.git/HEAD", "x")
      assert find_candidates(tmp_path / "plain") == ["a.txt"]
  ```

  ```python
  # test_app.py
  def test_slash_finds_and_opens(repo):
      # docs/design.md 생성. press("slash") → CommandPalette 화면; 입력 "desi" 를 press 로 한 글자씩
      # wait_until(하이라이트된 결과가 생김) → press("enter") → current_tab.path == repo/"docs"/"design.md"

  def test_m_menu_copy_path(repo, monkeypatch):
      # monkeypatch shellops.copy_text 기록. config.json 열고 app.current_tab.query_one("#body").focus(), press("m") → isinstance(app.screen, MenuScreen)
      # app.screen.path == repo/"config.json"; "copy" 옵션 고르고 enter → 기록 == [str(repo/"config.json")]

  def test_m_on_tree_uses_tree_cursor(repo, monkeypatch):
      # monkeypatch shellops.reveal 기록. #tree 포커스, 커서를 "config.json" 노드로, press("m"), "reveal" 고르고 enter → 기록 == [repo/"config.json"]

  def test_right_click_on_tree_opens_menu_for_that_row(repo):
      # 루트에 .git, a.txt, b.txt 만 있게 함 → 줄 0 루트, 1 .git, 2 a.txt
      # await pilot.click(FileTree, offset=(4, 2), button=3) → isinstance(app.screen, MenuScreen) and app.screen.path == repo/"a.txt"
      # press("escape") → 메뉴 닫힘
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer -q`
  기대 결과: 새 테스트들 실패 (`ImportError: cannot import name 'find_candidates'` 등)

- [ ] **Step 3: 구현한다**

  - **`find_candidates`**
    - `gitstate.read_state(root)`가 `None`이 아니면 `git -C root ls-files -co --exclude-standard -z`를 쓴다. `GIT_OPTIONAL_LOCKS=0`, `CREATE_NO_WINDOW`를 준다.
    - 아니면 `os.walk`로 모은다. 이름이 `.git`인 폴더는 건너뛴다.
    - 결과는 정렬해서 돌려준다.
  - **`FileProvider`**
    - `startup`에서 `find_candidates(app.root)`를 thread로 한 번 부른다.
    - `search(query)`에서는 각 경로를 `self.matcher(query)`로 점수 매긴다. 점수가 0보다 크면 `Hit(score, matcher.highlight(rel), partial(app.open_file, app.root / rel))`를 낸다.
  - **`/` 키 (`action_find`)**
    - `CommandPalette(providers=[FileProvider], placeholder="파일 이름으로 찾기")`를 띄운다.
    - 기본 `ctrl+p` 팔레트는 `ENABLE_COMMAND_PALETTE = False`로 끈다.
    - 이 생성자 인자가 Textual 8.2.8에 없으면 같은 효과가 나는 방법을 쓰되, 테스트는 그대로 통과해야 한다.
    - `# ponytail: 열 때마다 전체 목록을 다시 모음. 파일 수십만 개면 캐시` 주석을 단다.
  - **`m` 키:** 트리에 포커스가 있으면 트리 커서 노드의 경로로, 아니면 `current_tab.path`로 `open_menu`를 부른다. 둘 다 없으면 아무 일도 하지 않는다.
  - **`open_menu`:** `MenuScreen`을 띄운다. 결과가 오면 다음처럼 처리한다.
    - `"reveal"` → `shellops.reveal(path)`
    - `"copy"` → `shellops.copy_text(str(path))` 후 `notify("경로를 복사했습니다")`
    - `"open"` → `open_external(path)`
    - shellops 함수는 `shellops.X` 형태로 불러서 monkeypatch가 먹히게 한다.
  - **우클릭**
    - `FileTree.on_mouse_down`에서 `event.button == 3`이면 그 줄의 노드를 찾는다. 줄 번호는 `event.y + scroll_offset.y`이고, 노드는 `get_node_at_line`로 얻는다.
    - 커서를 그 노드로 옮기고 `app.open_menu(노드 경로)`를 부른 뒤 `event.stop()`한다.
    - 탭 머리(`Tab`)에서 우클릭하면 그 탭의 파일로 `open_menu`를 부른다.
  - **`MenuScreen`:** `OptionList` 하나로 만든다. Enter로 고르면 그 id로 닫히고, Esc를 누르면 `None`으로 닫힌다.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer -q`
  기대 결과: 전부 통과

- [ ] **Step 5: 커밋한다**

  `git commit -am "feat(File_viewer): 파일 이름 찾기와 우클릭 메뉴" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 7: 자동 새로 고침

**Files:**
- Modify: `src/File_viewer/file_viewer/app.py`, `src/File_viewer/file_viewer/viewer.py`
- Test: `test/File_viewer/test_app.py`

**Interfaces:**
- Consumes: `stat_key` (Task 1), `read_state`, `GitError` (Task 2), `FileTab.refresh_content` (Task 4)
- Produces: `FileViewerApp.poll_once() -> None` — 한 번 확인한다. 테스트와 타이머가 함께 쓴다.

- [ ] **Step 1: 실패하는 테스트를 덧붙인다**

  모든 테스트는 `FileViewerApp(repo, poll_interval=0.1)`로 띄운다.

  ```python
  def test_open_tab_follows_external_edit(repo):
      # a.txt 열기 → write(repo, "a.txt", "AGENT\n") → wait_until(lambda: "AGENT" in app.current_tab.loaded.text)

  def test_refresh_keeps_scroll(repo):
      # 200줄 long.txt 열기, body.scroll_to(y=50, animate=False), settle → 150번 줄 수정
      # wait_until(내용 반영) → body.scroll_y == 50

  def test_new_file_gets_plus_and_does_not_steal_view(repo):
      # a.txt(커밋됨) 열기 → write(repo, "new.txt", "x") → wait_until(트리 루트 자식에 new.txt 가 있고 라벨이 " +" 로 끝남)
      # app.current_tab.path == repo/"a.txt", len(app.tab_ids) == 1

  def test_deleted_open_file_keeps_tab(repo):
      # a.txt 열기 → (repo/"a.txt").unlink() → wait_until(app.current_tab.deleted)
      # "지워진 파일" in app.current_tab.notice, len(app.tab_ids) == 1

  def test_poll_survives_git_error(repo, monkeypatch):
      # 앱이 뜬 뒤 monkeypatch.setattr(gitstate, "read_state", 늘 GitError("index.lock") 를 내는 함수)
      # 0.5초 settle 반복 → app.is_running, 열린 탭 그대로

  def test_poll_survives_unreadable_file(repo, monkeypatch):
      # a.txt 열기 → monkeypatch.setattr(files, "load", 늘 PermissionError 를 내는 함수) → a.txt 의 mtime 을 바꿈
      # 0.5초 settle 반복 → app.is_running, current_tab.loaded.text 는 이전 내용
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_app.py -q`
  기대 결과: 새 테스트들 실패

- [ ] **Step 3: 구현한다**

  - **타이머:** `on_mount`에서 `set_interval(poll_interval, self.poll_once)`를 건다.
  - **`poll_once`:** 메인 스레드에서 확인할 대상을 모은다. 대상은 편집 중이 아닌 탭들의 `(tab, path, key)`와 펼쳐진 폴더 경로 목록이다. 그다음 `@work(thread=True, exclusive=True)` worker에 넘긴다. 트리 노드는 스레드에서 직접 읽지 않는다.
  - **스레드에서 하는 일**
    - **열린 탭:** `editing`이 아닌 탭마다 `stat_key(path)`를 구해 `tab.key`와 비교한다.
      - 다르고 `None`이 아니면 `call_from_thread(tab.refresh_content, True)`를 부른다.
      - `None`이면 `tab.deleted = True`로 두고 `#notice`에 `"지워진 파일입니다: {rel}"`을 보여준다.
      - 다시 생기면 `deleted`를 풀고 다시 읽는다.
    - **트리:** 펼쳐진 폴더마다 `sorted(os.listdir(폴더))`를 구하고 git 상태를 `gitstate.read_state(root)`로 읽는다. 이 호출은 monkeypatch가 먹히도록 이 형태로 한다.
      - 직전 값과 비교한다.
      - 폴더 목록이 바뀌었으면 `call_from_thread(tree.reload)`를 부른다. Textual 8.2.8의 `DirectoryTree.reload`는 펼침 상태와 커서를 유지한다.
      - git 상태가 바뀌었으면 `call_from_thread(tree.set_state, 새 상태)`를 부른다.
  - **실패 처리:** `GitError`와 `OSError`(`PermissionError` 포함)는 조용히 넘기고 이전 화면을 둔다. `refresh_content`에서 난 `OSError`도 같다.
  - **화면을 옮기지 않는다:** 폴링은 `open_file`, 커서 이동, 탭 전환을 하지 않는다(설계 §6, 사용자 결정).

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer -q`
  기대 결과: 전부 통과

- [ ] **Step 5: 커밋한다**

  `git commit -am "feat(File_viewer): 열린 탭·트리·git 표시 자동 새로 고침" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 8: 편집과 저장

**Files:**
- Modify: `src/File_viewer/file_viewer/viewer.py`, `src/File_viewer/file_viewer/app.py`
- Test: `test/File_viewer/test_app.py`

**Interfaces:**
- Consumes: `load`, `save`, `stat_key` (Task 1), `FileTab` (Task 4)
- Produces:
  - `FileTab` 메서드:
    - `start_edit() -> bool`: 편집할 수 없으면 `False`.
    - `is_dirty() -> bool`
    - `write_file() -> None`
    - `stop_edit() -> None`: 보기 상태로 돌아가 디스크 내용을 다시 읽는다.
  - `FileTab` 속성: `edit_key: tuple[int, int] | None`
  - 편집 위젯: `TextArea#editor`
  - `class ConfirmScreen(ModalScreen[bool])` (`app.py`): `__init__(self, message: str)`. `y`/Enter → `True`, `n`/Esc → `False`. 문구 끝에 `"  (y 예 / n 아니요)"`를 붙인다.

- [ ] **Step 1: 실패하는 테스트를 덧붙인다**

  ```python
  def test_edit_save_keeps_cp949_and_crlf(repo):
      # write(repo, "a.txt", "가\r\n나\r\n".encode("cp949")) 열기 → press("e") → editor 가 포커스
      # editor.text = "가\n다\n" → press("ctrl+s"); settle → (repo/"a.txt").read_bytes() == "가\r\n다\r\n".encode("cp949")

  def test_save_asks_before_overwriting_external_change(repo):
      # a.txt 열고 e, editor.text = "MINE\n" → write(repo, "a.txt", "AGENT\n") → ctrl+s → isinstance(app.screen, ConfirmScreen)
      # press("n") → 파일은 "AGENT\n"; ctrl+s → ConfirmScreen → press("y") → 파일은 "MINE\n"

  def test_escape_with_unsaved_changes_asks(repo):
      # e, editor.text 바꿈 → press("escape") → ConfirmScreen → press("y") → not current_tab.editing, 파일은 그대로

  def test_close_tab_and_quit_with_unsaved_changes_ask(repo):
      # 편집 중에는 w·q 가 글자로 들어가므로 액션을 직접 부른다
      # e, editor.text 바꿈 → app.action_close_tab() → ConfirmScreen → press("n") → 탭 그대로
      # await app.action_quit() → ConfirmScreen → press("n") → app.is_running

  def test_editing_keys_go_to_editor(repo):
      # 탭 두 개 열고 두 번째에서 e → press("tab") → current_tab 그대로, editor.text 에 들여쓰기가 들어감
      # press("q") → app.is_running, editor.text 에 "q" 포함

  def test_editing_tab_not_auto_refreshed(repo):
      # poll_interval=0.1. e, editor.text = "MINE\n" → write(repo, "a.txt", "AGENT\n") → 0.5초 settle → editor.text == "MINE\n"

  def test_not_editable_file_refuses(repo):
      # write(repo, "x.txt", b"ok \xff\xfe\xfa\n") 열기 → press("e") → not current_tab.editing
      # logo.png(바이너리)도 같음
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_app.py -q`
  기대 결과: `ImportError: cannot import name 'ConfirmScreen'`

- [ ] **Step 3: 구현한다**

  - **`start_edit`**
    - 다음 경우에는 `False`를 돌려준다: `loaded`가 없음, `not loaded.editable`, 바이너리, `deleted`. 앱은 이때 `notify("이 파일은 편집할 수 없습니다")`를 띄운다.
    - 편집할 수 있으면 `#body` 안을 `TextArea(loaded.text, id="editor", show_line_numbers=True, soft_wrap=False, tab_behavior="indent")`로 바꾸고 포커스를 준다.
    - `editing = True`, `edit_key = stat_key(path)`로 둔다.
    - md도 원문으로 편집한다.
  - **`is_dirty`:** `editor.text != loaded.text`.
  - **`write_file`:** `save(path, editor.text, loaded)` 후 `loaded = load(path)`, `key = edit_key = stat_key(path)`로 갱신한다.
  - **키**
    - `ctrl+s`(저장)와 `escape`(편집 끝)는 편집 중일 때만 동작한다.
    - `e`(편집)는 보기 상태일 때만 동작한다.
    - 편집 중에는 TextArea가 포커스를 가지므로 글자 키(`q`, `w`, `v`, `o`, `m`, `t`, `/`, `[`, `]`)는 TextArea로 들어간다.
    - `tab`/`shift+tab`은 `priority=True`다. 그래서 `check_action`이 편집 중에 `False`를 돌려줘야 한다. 그러면 TextArea가 들여쓰기로 받는다.
  - **저장 (`ctrl+s`)**
    - `stat_key(path) != edit_key`이면 `ConfirmScreen("다른 곳에서 파일이 바뀌었습니다. 덮어쓸까요?")`를 띄운다. `True`일 때만 `write_file`한다.
    - 같으면 바로 `write_file`한다.
    - 성공하면 `notify("저장했습니다")`, 실패(`OSError`)하면 `notify(f"저장 실패: {e}", severity="error")`.
  - **편집 끝 (`escape`):** 저장하지 않은 변경이 있으면 `ConfirmScreen("저장하지 않은 변경을 버릴까요?")`를 띄운다. `True`이거나 변경이 없으면 `stop_edit`한다.
  - **탭 닫기·종료:** `action_close_tab`과 `action_quit`도 저장하지 않은 편집 탭이 있으면 같은 확인을 거친다. 종료는 `ctrl+q`(Textual 기본)로도 들어온다.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer -q`
  기대 결과: 전부 통과

- [ ] **Step 5: 커밋한다**

  `git commit -am "feat(File_viewer): 편집·저장과 덮어쓰기 확인" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 9: 실행 진입점 + Herdr에 연결

**Files:**
- Create: `src/File_viewer/file_viewer/__main__.py`
- Test: `test/File_viewer/test_main.py`
- Modify (저장소 밖, 사용자 설정): `%APPDATA%\herdr\config.toml`

**Interfaces:**
- Consumes: `FileViewerApp` (Task 4), `set_right_click` (Task 3)
- Produces: `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

  ```python
  def test_main_missing_dir_waits_for_enter(tmp_path, monkeypatch, capsys):
      calls = []
      monkeypatch.setattr("builtins.input", lambda prompt="": calls.append(prompt) or "")
      assert main([str(tmp_path / "없음")]) == 1
      assert "폴더가 아닙니다" in capsys.readouterr().out and len(calls) == 1

  def test_main_runs_app_on_given_dir_and_routes_right_click(tmp_path, monkeypatch):
      seen, clicks = [], []
      monkeypatch.setattr(FileViewerApp, "run", lambda self, *a, **k: seen.append(self.root))
      monkeypatch.setattr(shellops, "set_right_click", lambda t: clicks.append(t))
      sub = tmp_path / "하위"; sub.mkdir()
      assert main([str(sub)]) == 0
      assert seen == [sub.resolve()] and clicks == ["pane", "herdr"]
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer/test_main.py -q`
  기대 결과: `ModuleNotFoundError: file_viewer.__main__`

- [ ] **Step 3: `main`을 구현한다**

  - **시작 폴더:** 인자가 있으면 그 경로를, 없으면 현재 폴더를 `resolve()`해서 쓴다. 저장소 최상위로 올라가지 않는다(설계 §7).
  - **폴더가 아닐 때:** `폴더가 아닙니다: {경로}`를 출력하고 `input("Enter를 누르면 닫습니다...")` 후 `1`을 돌려준다. Herdr의 `type = "pane"` 칸은 프로그램이 끝나면 바로 닫히므로, 이렇게 해야 안내를 읽을 수 있다.
  - **폴더일 때:**
    1. `shellops.set_right_click("pane")`
    2. `try: FileViewerApp(root).run()`
    3. `finally: shellops.set_right_click("herdr")`
    4. `0`을 돌려준다.
  - `if __name__ == "__main__": raise SystemExit(main())`.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/File_viewer pytest test/File_viewer -q`
  기대 결과: 전부 통과

  그리고 `uv sync --project src/File_viewer`를 다시 돌린 뒤 `src/File_viewer/.venv/Scripts/File_viewer.exe D:/없는폴더`를 실행한다.
  기대 결과: 안내 문구가 나오고 Enter를 기다린다.

- [ ] **Step 5: Herdr에 연결한다**

  `%APPDATA%\herdr\config.toml` 끝, easy_GIT 블록 아래에 다음을 덧붙인다. 기존 내용은 건드리지 않는다. `prefix+alt+f`가 이미 쓰이고 있지 않은지 먼저 `herdr config` 하위 명령이나 설정 파일로 확인한다.

  ```toml
  # prefix+alt+f → 현재 pane 폴더를 File_viewer 칸으로 (q 로 닫기)
  # 코드: D:\WorkTrees\ADE_sub\file-viewer\src\File_viewer (브랜치 file_viewer). master에 합친 뒤에는 D:\ADE_sub\src\File_viewer 로 바꾼다
  [[keys.command]]
  key = "prefix+alt+f"
  type = "pane"
  command = 'D:\WorkTrees\ADE_sub\file-viewer\src\File_viewer\.venv\Scripts\File_viewer.exe'
  description = "파일 보기 (File_viewer)"
  ```

  `herdr server reload-config`를 실행한다. 기대 결과: 오류 없이 끝난다.

- [ ] **Step 6: Herdr 안에서 직접 확인한다** (사용자와 함께)

  - [ ] 에이전트 칸에서 `prefix+alt+f`를 누르면 **오른쪽에** 칸이 열리고, 그 칸의 폴더가 트리에 보인다.
    - 아래쪽에 열리거나 다른 폴더가 열리면 여기서 멈추고 사용자에게 보고한다.
    - 대안은 사용자가 오른쪽 칸을 직접 열고 `File_viewer.exe`를 실행하는 것이다. `herdr pane split --current --direction right --cwd <폴더>`로 칸을 연 뒤 `herdr pane run`으로 실행하는 방법도 있다.
  - [ ] 트리 우클릭으로 메뉴가 뜬다. "경로 복사" 뒤 메모장에서 붙여 넣으면 한글 경로가 그대로 나온다. "탐색기에서 열기"를 누르면 그 파일이 선택된 탐색기가 뜬다.
  - [ ] html에서 `o`를 누르면 Edge가 열린다. md에서 `o`를 누르면 기본 프로그램이 열린다.
    - 이 PC에는 `.md` 기본 프로그램이 지정돼 있지 않다(2026-11-04 확인). 그래서 Windows의 "앱 선택" 창이 뜨는 것이 정상이다. 사용자에게 Obsidian 연결 여부를 묻는다.
  - [ ] 칸 폭을 줄이면 트리가 숨고, 넓히면 다시 보인다. 실제 칸에서 `NARROW_BELOW`가 맞는지 사용자와 본다.
  - [ ] 옆 칸 에이전트가 파일을 고치면 1~2초 안에 열린 탭과 트리 표시에 반영된다.
  - [ ] `e`로 편집을 시작해 한글 IME로 입력하고 `Ctrl+S`로 저장된다. Herdr나 conhost가 `Ctrl+S`를 가로채면 사용자에게 알리고 다른 키를 정한다.
  - [ ] `q`로 닫으면 칸도 닫히고, 그 뒤 Herdr의 우클릭이 원래대로 돌아온다.

- [ ] **Step 7: 커밋한다**

  `git add src/File_viewer/file_viewer/__main__.py test/File_viewer/test_main.py`
  `git commit -m "feat(File_viewer): 실행 진입점과 Herdr 칸 연결" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`
  (Herdr 설정 파일은 저장소 밖이라 커밋하지 않는다.)
