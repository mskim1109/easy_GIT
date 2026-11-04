# easy_GIT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Herdr 칸에 띄워 두고, 작업 중인 변경과 커밋을 "파일 전체 + 변경 표시"로 보고, stage·커밋까지 하는 터미널 Git 보기 도구를 만든다.

**Architecture:** git CLI를 subprocess로 부르는 `gitio`(읽기·쓰기·변경 감지)가 있다. 그 위에 git이 내놓는 full-context diff(`-U1000000`)를 행 목록으로 바꾸는 순수 함수 `fulldiff`를 둔다. 화면은 Textual 앱 `app`과 본문 위젯 `diffview`가 맡는다. 자동 새로 고침은 1초마다 `gitio.snapshot()`을 비교하는 폴링으로 한다.

**Tech Stack:** Python 3.12, Textual 8.2(rich 포함), pytest 9, uv, git 2.53

**Spec:** `docs/design/2026-11-04-easy-git-design.md`

## Global Constraints

- Python `>=3.12`. 런타임 의존성은 `textual>=8.2,<9` 하나뿐이다. pytest는 dev 그룹에만 둔다.
- 코드는 `src/easy_GIT/easy_git/`, 테스트는 `test/easy_GIT/`, 문서는 `docs/design/`에 둔다.
- git은 git CLI(subprocess)로만 다룬다. GitPython 같은 라이브러리는 쓰지 않는다.
- 저장소를 바꾸는 동작은 stage, unstage, commit 셋뿐이다. 사용자가 키를 눌렀을 때만 실행한다. `--no-verify`, discard, amend, push는 쓰지 않는다.
- 화면 문구는 영어다 (2026-11-04 사용자 결정으로 한국어에서 바꿈). 한글 경로, 커밋 메시지, 파일 내용(UTF-8 / CP949)은 깨지지 않아야 한다.
- Windows 11 기본 콘솔 창(conhost) 안의 Herdr 0.9.5에서 돌아가야 한다. Ctrl+V 붙여넣기에 의존하지 않는다.
- 테스트는 저장소 최상위에서 `uv run --project src/easy_GIT pytest test/easy_GIT -q`로 돌린다.
- 이 저장소의 git 커밋 메시지는 맨 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 줄을 붙인다.

## Review Focus

1. **한글 경로 + CP949 파일 내용.** `한글/설정.txt`가 CP949로 저장돼 있어도 경로와 내용이 그대로 보여야 한다. → Task 2 `test_korean_path_and_cp949_content`
2. **이미 수정된 파일을 에이전트가 또 고침.** `git status` 출력은 그대로라도 자동 새로 고침이 알아채야 한다. → Task 3 `test_snapshot_changes_when_modified_file_is_edited_again`
3. **커밋이 하나도 없는 새 저장소, 첫 커밋.** 목록이 비어도 죽지 않고, 첫 커밋은 전부 추가된 줄로 보여야 한다. → Task 2 `test_empty_repo`, `test_commit_changes_root_and_rename`
4. **읽는 도중 자동 새로 고침.** 다른 파일이 바뀌어도 지금 보던 파일 선택과 스크롤 위치가 유지돼야 한다. → Task 6 `test_refresh_keeps_selection_and_scroll`
5. **에이전트가 동시에 git을 돌림.** 폴링 중 git 명령이 실패해도(index.lock 등) 앱이 살아 있고 이전 화면을 유지해야 한다. 폴링은 `GIT_OPTIONAL_LOCKS=0`으로 lock을 만들지 않는다. → Task 6 `test_poll_survives_git_error`

## 실행 구성 (2026-11-04 사용자 결정: 워크트리 2개 병렬)

- **master 첫 커밋(기준점):** `.gitignore`, `docs/design/`, `src/easy_GIT/pyproject.toml`, `src/easy_GIT/uv.lock`, `src/easy_GIT/easy_git/__init__.py`. 그래서 Task 1 Step 1의 브랜치 만들기와 뼈대는 이미 되어 있다. 각 워크트리에서는 `uv sync --project src/easy_GIT`만 돌린다.
- **core 워크트리** `D:/WorkTrees/ADE_sub/easy-git-core` (브랜치 `feat/easy-git-core`): Task 1 → 2 → 3.
- **ui 워크트리** `D:/WorkTrees/ADE_sub/easy-git-ui` (브랜치 `feat/easy-git-ui`): Task 4 → 5.
  - `fulldiff.py`와 `gitio.py`는 직접 만들지 않는다. 각 Task의 Interfaces에 적힌 이름·타입대로 가져다 쓴다.
  - core가 끝났다는 알림을 받으면 `git merge feat/easy-git-core`를 하고 테스트를 통과시킨다.
- **Task 6 · 7:** 둘을 합친 뒤 지휘 칸이 진행한다.
- 각 워크트리는 자기 브랜치에만 git 커밋한다. master 변경, 다른 워크트리 수정, push는 하지 않는다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `.gitignore` | `.superpowers/`, `graft/.cache/`, `.venv/`, `__pycache__/`, `.pytest_cache/` |
| `src/easy_GIT/pyproject.toml` | 패키지 `easy-git`, 스크립트 `easy_GIT = "easy_git.__main__:main"` (설계 §5의 `easy_GIT [경로]`) |
| `src/easy_GIT/easy_git/__init__.py` | 빈 파일 |
| `src/easy_GIT/easy_git/fulldiff.py` | diff 텍스트 → `Row` / `SideRow` 목록, 변경 시작 위치 (순수 함수) |
| `src/easy_GIT/easy_git/gitio.py` | git 실행, 커밋·변경 목록, 파일별 행, stage/unstage/commit, snapshot |
| `src/easy_GIT/easy_git/diffview.py` | 본문 위젯 `DiffView` (합쳐/좌우 렌더링, n/p 이동) |
| `src/easy_GIT/easy_git/app.py` | `EasyGitApp`, 세 칸·반응형 배치, 키, 커밋 화면, 자동 새로 고침 |
| `src/easy_GIT/easy_git/__main__.py` | 실행 진입점, 저장소 찾기, 저장소가 아닐 때 안내 |
| `test/easy_GIT/conftest.py` | 격리된 임시 git 저장소 fixture와 헬퍼 |
| `test/easy_GIT/test_fulldiff.py`, `test_gitio.py`, `test_app.py`, `test_main.py` | 테스트 |

---

### Task 1: 프로젝트 뼈대 + full-context diff 파서

**Files:**
- Create: `.gitignore`, `src/easy_GIT/pyproject.toml`, `src/easy_GIT/easy_git/__init__.py`, `src/easy_GIT/easy_git/fulldiff.py`
- Test: `test/easy_GIT/test_fulldiff.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Row: kind: Literal["same","add","del"]; old_no: int | None; new_no: int | None; text: str`
  - `@dataclass(frozen=True) class SideRow: left_no: int | None; left: str | None; right_no: int | None; right: str | None; kind: Literal["same","add","del","change"]`
  - `parse_unified(diff_text: str) -> list[Row]`
  - `side_rows(rows: list[Row]) -> list[SideRow]`
  - `change_starts(changed: list[bool]) -> list[int]`

- [ ] **Step 1: 브랜치를 만들고 뼈대를 둔다**

  `git switch -c feat/easy-git`. 아직 커밋이 없는 저장소라 이름만 바뀐다. `.gitignore`는 File Structure 표대로 만든다. `pyproject.toml`은 아래와 같다.

  ```toml
  [project]
  name = "easy-git"
  version = "0.1.0"
  requires-python = ">=3.12"
  dependencies = ["textual>=8.2,<9"]

  [project.scripts]
  easy_GIT = "easy_git.__main__:main"

  [dependency-groups]
  dev = ["pytest>=9"]

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"
  ```

  `uv sync --project src/easy_GIT`를 돌린다. 기대 결과: `src/easy_GIT/.venv`가 생기고 textual과 pytest가 설치된다. `__main__.py`는 Task 7에서 만든다.

- [ ] **Step 2: 실패하는 테스트를 쓴다** (`test/easy_GIT/test_fulldiff.py`)

  ```python
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
  ```

- [ ] **Step 3: 실패를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT/test_fulldiff.py -q`
  기대 결과: `ModuleNotFoundError: easy_git.fulldiff`

- [ ] **Step 4: `fulldiff.py`를 구현한다**

  - `parse_unified`: 첫 `@@` 줄 앞의 헤더는 건너뛴다. `@@ -a[,b] +c[,d] @@`에서 시작 번호를 읽는다. 각 줄의 첫 글자로 종류를 정한다: `' '`는 same(이전·이후 번호 둘 다 +1), `'-'`는 del, `'+'`는 add, `'\'`는 무시. 텍스트는 `line[1:]`에서 끝의 `\r` 하나를 떼어 낸 것이다. 새 `@@`가 나오면 번호를 다시 읽는다.
  - `side_rows`: same 행은 그대로 짝짓는다. 연속된 del/add 묶음은 del 목록과 add 목록을 `itertools.zip_longest`로 짝짓는다. 양쪽이 다 있으면 `change`, 한쪽만 있으면 `del` 또는 `add`다.
  - `change_starts`: `changed[i]`가 참이고 `i == 0`이거나 `changed[i-1]`이 거짓인 `i`의 목록.

- [ ] **Step 5: 통과를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT/test_fulldiff.py -q`
  기대 결과: `4 passed`

- [ ] **Step 6: 커밋한다**

  `git add .gitignore src/easy_GIT/pyproject.toml src/easy_GIT/uv.lock src/easy_GIT/easy_git test/easy_GIT docs/design`
  `git commit -m "feat(easy_GIT): 프로젝트 뼈대와 full-context diff 파서" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 2: git 읽기 — 커밋, 변경 목록, 파일별 행

**Files:**
- Create: `src/easy_GIT/easy_git/gitio.py`, `test/easy_GIT/conftest.py`
- Test: `test/easy_GIT/test_gitio.py`

**Interfaces:**
- Consumes: `Row`, `parse_unified` (Task 1)
- Produces:
  - `class GitError(Exception)`: 속성 `output: str`(git stderr+stdout 해독본)
  - `run_git(repo: Path, *args: str, input: bytes | None = None, check: bool = True) -> bytes`
  - `repo_root(path: Path) -> Path | None`
  - `decode_text(data: bytes) -> str`
  - `@dataclass(frozen=True) class Commit: sha: str; short: str; parents: tuple[str, ...]; author: str; when: int; subject: str; body: str`
  - `@dataclass(frozen=True) class FileChange: group: Literal["commit","staged","unstaged"]; status: str; path: str; old_path: str | None = None; added: int | None = None; deleted: int | None = None; binary: bool = False; base: str = ""; target: str = ""`
  - `commits(repo: Path, limit: int = 200) -> list[Commit]`
  - `commit_changes(repo: Path, commit: Commit) -> list[FileChange]`
  - `working_changes(repo: Path) -> tuple[list[FileChange], list[FileChange]]` — 반환값은 `(staged, unstaged)`
  - `file_rows(repo: Path, change: FileChange) -> list[Row] | None` — 바이너리면 `None`
  - conftest: fixture `repo -> Path`, 헬퍼 `git(repo, *args) -> str`, `write(repo, rel, text, encoding="utf-8") -> None`

- [ ] **Step 1: conftest를 쓴다**

  fixture `repo(tmp_path, monkeypatch)`는 아래처럼 git 환경을 격리한 뒤 `tmp_path / "r"`에 `git init -b main`을 하고 그 경로를 돌려준다.
  - `GIT_CONFIG_GLOBAL`: 빈 파일 `tmp_path/"gitconfig"`
  - `GIT_CONFIG_NOSYSTEM=1`
  - `GIT_AUTHOR_NAME` / `GIT_COMMITTER_NAME`: `tester`
  - `GIT_AUTHOR_EMAIL` / `GIT_COMMITTER_EMAIL`: `t@example.com`

  `git()`은 `subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)`의 stdout을 UTF-8로 해독해 돌려준다. `write()`는 상위 폴더를 만들고 `newline=""`로 쓴다.

- [ ] **Step 2: 실패하는 테스트를 쓴다** (`test/easy_GIT/test_gitio.py`)

  ```python
  def test_repo_root_from_subdir(repo, tmp_path):
      sub = repo / "a" / "b"; sub.mkdir(parents=True)
      assert repo_root(sub) == repo.resolve()
      (tmp_path / "plain").mkdir()
      assert repo_root(tmp_path / "plain") is None

  def test_commits_korean_message(repo):
      write(repo, "a.txt", "1\n"); git(repo, "add", "."); git(repo, "commit", "-m", "설정 로더 보강\n\n설정 파일이 없을 때 빈 설정으로 시작.")
      [c] = commits(repo)
      assert (c.subject, c.body.strip(), c.author, c.parents) == ("설정 로더 보강", "설정 파일이 없을 때 빈 설정으로 시작.", "tester", ())
      assert len(c.short) >= 7 and c.sha.startswith(c.short)

  def test_empty_repo(repo):
      assert commits(repo) == []
      write(repo, "new.txt", "a\nb\n"); git(repo, "add", ".")
      staged, unstaged = working_changes(repo)
      assert unstaged == []
      assert [(f.group, f.status, f.path, f.added, f.deleted) for f in staged] == [("staged", "A", "new.txt", 2, 0)]
      assert [r.kind for r in file_rows(repo, staged[0])] == ["add", "add"]

  def test_commit_changes_root_and_rename(repo):
      write(repo, "a.txt", "1\n2\n3\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
      git(repo, "mv", "a.txt", "b.txt"); git(repo, "commit", "-m", "c2")
      second, first = commits(repo)
      [r] = commit_changes(repo, second)
      assert (r.status, r.old_path, r.path) == ("R", "a.txt", "b.txt")
      [a] = commit_changes(repo, first)
      assert (a.status, a.path, a.added, a.deleted) == ("A", "a.txt", 3, 0)
      assert [x.kind for x in file_rows(repo, a)] == ["add"] * 3

  def test_merge_commit_compares_first_parent(repo):
      write(repo, "a.txt", "1\n"); git(repo, "add", "."); git(repo, "commit", "-m", "base")
      git(repo, "switch", "-c", "side"); write(repo, "b.txt", "x\n"); git(repo, "add", "."); git(repo, "commit", "-m", "side")
      git(repo, "switch", "main"); git(repo, "merge", "--no-ff", "-m", "merge", "side")
      assert [f.path for f in commit_changes(repo, commits(repo)[0])] == ["b.txt"]

  def test_partly_staged_file_appears_in_both_groups(repo):
      write(repo, "a.txt", "x\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
      write(repo, "a.txt", "x\ny\n"); git(repo, "add", "a.txt")
      write(repo, "a.txt", "x\ny\nz\n")
      staged, unstaged = working_changes(repo)
      assert [(f.path, f.added) for f in staged] == [("a.txt", 1)]
      assert [(f.path, f.added) for f in unstaged] == [("a.txt", 1)]
      assert file_rows(repo, staged[0]) == [Row("same", 1, 1, "x"), Row("add", None, 2, "y")]
      assert file_rows(repo, unstaged[0]) == [Row("same", 1, 1, "x"), Row("same", 2, 2, "y"), Row("add", None, 3, "z")]

  def test_untracked_and_binary(repo):
      write(repo, "new.txt", "a\nb\n"); (repo / "img.bin").write_bytes(b"\x00\x01")
      _, unstaged = working_changes(repo)
      by = {f.path: f for f in unstaged}
      assert (by["new.txt"].status, by["new.txt"].added, by["new.txt"].binary) == ("A", 2, False)
      assert by["img.bin"].binary is True and file_rows(repo, by["img.bin"]) is None

  def test_korean_path_and_cp949_content(repo):
      write(repo, "한글/설정.txt", "포트=8080\n", encoding="cp949"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
      write(repo, "한글/설정.txt", "포트=9090\n", encoding="cp949")
      _, [f] = working_changes(repo)
      assert f.path == "한글/설정.txt"
      assert file_rows(repo, f) == [Row("del", 1, None, "포트=8080"), Row("add", None, 1, "포트=9090")]

  def test_decode_text():
      assert decode_text("한글".encode("cp949")) == "한글"
      assert decode_text("\ufeffabc".encode("utf-8")) == "abc"
  ```

- [ ] **Step 3: 실패를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT/test_gitio.py -q`
  기대 결과: `ModuleNotFoundError: easy_git.gitio`

- [ ] **Step 4: `gitio.py`를 구현한다**

  - **`run_git`**
    - `subprocess.run(["git", *args], cwd=repo, capture_output=True)`로 부른다. 환경은 `os.environ`에 `GIT_OPTIONAL_LOCKS=0`을 더한 것이다.
    - `input`이 없으면 `stdin=DEVNULL`로 둔다. 콘솔 키 입력을 빼앗지 않기 위해서다.
    - `check`가 참이고 종료 코드가 0이 아니면 `GitError(decode_text(stderr + stdout))`를 던진다.
  - **`decode_text`**: `utf-8-sig`로 시도하고, 실패하면 `cp949`, 그것도 실패하면 `utf-8`에 `errors="replace"`로 해독한다.
  - **`repo_root`**: `git rev-parse --show-toplevel`을 실행한다. 실패하면 `None`, 성공하면 `Path(...).resolve()`를 돌려준다.
  - **`commits`**
    - `git log -n{limit} --format=%H%x1f%h%x1f%P%x1f%an%x1f%at%x1f%s%x1f%b%x1e`의 출력을 `\x1e`로 나누고, 각 항목을 `\x1f`로 나눈다.
    - HEAD가 없으면(git 오류) `[]`를 돌려준다.
    - 한 번에 200개만 읽는다. 해당 줄에 `# ponytail: 200개 고정, 더 보기는 필요해지면` 주석을 단다.
  - **변경 목록**
    - 같은 diff 인자로 `--name-status -z -M`과 `--numstat -z -M`을 각각 실행하고, 결과를 새 경로 기준으로 합친다. 공통 헬퍼로 만든다.
    - `-z` 형식에서 이름 변경은 `R100\0old\0new\0` / `a\td\t\0old\0new\0`로 나온다.
    - numstat이 `-\t-`면 `binary=True`이고 `added` / `deleted`는 `None`이다.
    - status는 첫 글자만 쓴다(`R100` → `R`).
  - **`commit_changes`**
    - `base`는 `parents[0]`이다. 부모가 없으면 `git hash-object -t tree --stdin`에 빈 입력을 넣어 얻은 빈 트리다.
    - `target`은 `commit.sha`이고, 인자는 `diff base target`이다.
  - **`working_changes`**
    - staged는 `diff --cached`다.
    - unstaged는 `diff`(index → 작업 폴더)에 `ls-files --others --exclude-standard -z`로 얻은 새 파일을 더한 것이다.
    - 새 파일은 `status="A"`, `deleted=0`이다. `added`는 줄 수다. 앞 8000바이트에 NUL이 있으면 `binary=True`로 표시한다.
  - **`file_rows`**
    - 바이너리면 `None`이다.
    - unstaged의 새 파일은 디스크에서 읽어 모든 줄을 `add`로 만든다.
    - 나머지는 `git diff --no-color --no-ext-diff -M -U1000000`에 그룹별 인자를 더한다: commit은 `base target`, staged는 `--cached`, unstaged는 없음. 뒤에 `-- [old_path] path`를 붙인다.
    - 출력 첫 부분에 `Binary files`가 있으면 `None`이고, 아니면 `parse_unified(decode_text(out))`이다.
    - 모든 diff 호출에 `-c core.quotepath=false`를 붙인다.

- [ ] **Step 5: 통과를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT -q`
  기대 결과: 전부 통과 (`13 passed`)

- [ ] **Step 6: 커밋한다**

  `git add src/easy_GIT/easy_git/gitio.py test/easy_GIT`
  `git commit -m "feat(easy_GIT): git 커밋·변경 목록과 파일 전체 행 읽기" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 3: git 쓰기 — stage, unstage, commit, 변경 감지

**Files:**
- Modify: `src/easy_GIT/easy_git/gitio.py`
- Test: `test/easy_GIT/test_gitio.py`

**Interfaces:**
- Consumes: `run_git`, `working_changes`, `FileChange` (Task 2)
- Produces:
  - `stage(repo: Path, change: FileChange) -> None`
  - `unstage(repo: Path, change: FileChange) -> None`
  - `commit(repo: Path, message: str) -> tuple[bool, str]` — `(성공 여부, 화면에 보여줄 문구)`
  - `snapshot(repo: Path) -> str`

- [ ] **Step 1: 실패하는 테스트를 덧붙인다**

  ```python
  def _partly_staged(repo):
      write(repo, "a.txt", "x\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
      write(repo, "a.txt", "x\ny\n"); git(repo, "add", "a.txt"); write(repo, "a.txt", "x\ny\nz\n")

  def test_stage_and_unstage_whole_file(repo):
      _partly_staged(repo)
      stage(repo, working_changes(repo)[1][0])
      staged, unstaged = working_changes(repo)
      assert ([f.added for f in staged], unstaged) == ([2], [])
      unstage(repo, staged[0])
      staged, unstaged = working_changes(repo)
      assert (staged, [f.path for f in unstaged]) == ([], ["a.txt"])

  def test_unstage_in_empty_repo(repo):
      write(repo, "n.txt", "a\n"); git(repo, "add", ".")
      unstage(repo, working_changes(repo)[0][0])
      staged, unstaged = working_changes(repo)
      assert (staged, [(f.path, f.status) for f in unstaged]) == ([], [("n.txt", "A")])

  def test_commit_success_with_korean_message(repo):
      write(repo, "a.txt", "1\n"); git(repo, "add", ".")
      ok, _ = commit(repo, "첫 커밋")
      assert ok and commits(repo)[0].subject == "첫 커밋"

  def test_commit_refuses_empty_message_or_nothing_staged(repo):
      write(repo, "a.txt", "1\n"); git(repo, "add", ".")
      assert commit(repo, "   ") == (False, "커밋 메시지가 비어 있습니다.")
      git(repo, "commit", "-m", "c1")
      assert commit(repo, "x") == (False, "Stage된 파일이 없습니다.")

  def test_commit_runs_pre_commit_hook_and_shows_output(repo):
      hook = repo / ".git" / "hooks" / "pre-commit"
      hook.write_text("#!/bin/sh\necho hook says no >&2\nexit 1\n", newline="\n")
      write(repo, "a.txt", "1\n"); git(repo, "add", ".")
      ok, out = commit(repo, "x")
      assert not ok and "hook says no" in out and commits(repo) == []

  def test_snapshot_changes_when_modified_file_is_edited_again(repo):
      write(repo, "a.txt", "1\n"); git(repo, "add", "."); git(repo, "commit", "-m", "c1")
      write(repo, "a.txt", "2\n")
      s1 = snapshot(repo)
      assert snapshot(repo) == s1
      write(repo, "a.txt", "22\n")
      assert snapshot(repo) != s1

  def test_snapshot_changes_on_new_commit(repo):
      write(repo, "a.txt", "1\n"); git(repo, "add", ".")
      s1 = snapshot(repo); git(repo, "commit", "-m", "c1")
      assert snapshot(repo) != s1
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT/test_gitio.py -q`
  기대 결과: `ImportError: cannot import name 'stage'`

- [ ] **Step 3: 구현한다**

  - **`stage`**: `git add -- <path>`를 실행한다. 삭제된 파일도 이것으로 stage된다. 이름 변경이면 `old_path`도 함께 넘긴다.
  - **`unstage`**: HEAD가 있으면 `git restore --staged -- [old_path] path`, 없으면 `git rm --cached -q -- path`를 실행한다.
  - **`commit`**
    - 메시지가 공백뿐이면 `(False, "커밋 메시지가 비어 있습니다.")`를 돌려준다.
    - `git diff --cached --quiet`의 종료 코드가 0이면(stage된 것이 없으면) `(False, "Stage된 파일이 없습니다.")`를 돌려준다. 이 호출은 `check=False`로 한다.
    - 그 밖에는 `git commit -F -`에 메시지를 UTF-8로 넣는다. 성공하면 `(True, 출력)`, `GitError`가 나면 `(False, e.output)`이다. `--no-verify`는 절대 쓰지 않는다.
  - **`snapshot`**
    - 다음 셋을 이어 붙여 sha1 해시한다.
      - `git rev-parse -q --verify HEAD`의 결과(`check=False`)
      - `git status --porcelain=v1 -z --untracked-files=all`의 출력
      - 그 출력에 나온 각 경로의 `(st_mtime_ns, st_size)`. 없는 파일은 `-`로 쓴다.
    - `# ponytail: 1초마다 git status 전체 실행. 큰 저장소에서 느리면 파일 감시로` 주석을 단다.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT -q`
  기대 결과: 전부 통과 (`20 passed`)

- [ ] **Step 5: 커밋한다**

  `git add src/easy_GIT/easy_git/gitio.py test/easy_GIT/test_gitio.py`
  `git commit -m "feat(easy_GIT): stage·unstage·commit과 변경 감지" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 4: 세 칸 화면 + 본문 위젯 (합쳐/좌우 보기, n/p)

**Files:**
- Create: `src/easy_GIT/easy_git/diffview.py`, `src/easy_GIT/easy_git/app.py`
- Test: `test/easy_GIT/test_app.py`

**Interfaces:**
- Consumes: `Row`, `side_rows`, `change_starts` (Task 1), `commits`, `commit_changes`, `working_changes`, `file_rows`, `Commit`, `FileChange` (Task 2)
- Produces:
  - `class DiffView(ScrollableContainer)`
    - 속성: `source: list[Row] | None`, `rows: list[Row] | list[SideRow] | None`, `mode: Literal["unified","side"]`, `cursor_row: int`
    - 메서드: `show(rows: list[Row] | None, mode: str, keep_scroll: bool = False) -> None`, `set_mode(mode: str) -> None`, `next_change() -> None`, `prev_change() -> None`
  - `class EasyGitApp(App)`: `__init__(self, repo: Path, poll_interval: float = 1.0)`. 인자는 `self.repo`, `self.poll_interval`로 보관한다.
    - 위젯 id: `#left`(`#commits` OptionList, `#files` OptionList), `#right`(`#message` Static, `#diff` DiffView), 그리고 `Footer`
    - 속성: `view_mode: Literal["unified","side"]`(사용자가 고른 보기, 처음엔 `"unified"`), `message_text: str`
    - 옵션 id: 커밋 목록은 `"WORKING"` 또는 커밋 sha, 파일 목록은 `f"{group}:{path}"`. 묶음 제목은 id 없는 비활성 옵션이다.
  - `rel_time(epoch: int, now: int) -> str`

- [ ] **Step 1: 실패하는 테스트를 쓴다** (`test/easy_GIT/test_app.py`)

  모든 테스트는 `asyncio.run()` 안에서 `async with app.run_test(size=...) as pilot`을 쓴다. 비동기 테스트 플러그인은 쓰지 않는다. 일을 시킨 뒤에는 헬퍼 `settle(app, pilot)`로 기다린다. 이 헬퍼는 `await app.workers.wait_for_complete(); await pilot.pause()`를 두 번 실행한다.

  ```python
  def _repo_with_change(repo):
      write(repo, "config.py", "".join(f"line{i}\n" for i in range(1, 11)))
      git(repo, "add", "."); git(repo, "commit", "-m", "설정 추가\n\n본문 설명")
      write(repo, "config.py", "".join(("CHANGED\n" if i == 5 else f"line{i}\n") for i in range(1, 11)))

  def test_wide_opens_working_changes_with_full_file(repo):
      # 200x50: 커밋 목록 첫 줄 "● 작업 중인 변경 (1)", 파일 목록에 "Stage 안 된 변경 (1)" 제목과 "unstaged:config.py",
      # 본문은 합쳐 보기로 11행 (10줄 + 수정 1건의 del/add), 커서는 첫 변경 행(4).
      ...
      assert str(commits_list.get_option_at_index(0).prompt).startswith("● 작업 중인 변경 (1)")
      assert diff.mode == "unified" and len(diff.rows) == 11 and diff.cursor_row == 4

  def test_v_toggles_side_by_side(repo):
      # press("v") → diff.mode == "side" and len(diff.rows) == 10; 한 번 더 → "unified"

  def test_selecting_commit_shows_full_message(repo):
      # #commits 에서 index 1 (커밋) 로 이동 → "설정 추가" in app.message_text and "본문 설명" in app.message_text
      # 파일 목록 id 는 "commit:config.py"

  def test_n_and_p_move_between_changes(repo):
      # 줄 2와 8을 바꾼 파일 → 합쳐 보기 change_starts == [1, 8] → 처음 cursor_row == 1, n → 8, n → 8(끝에서 멈춤), p → 1

  def test_rel_time():
      assert [rel_time(1000, 1030), rel_time(0, 120), rel_time(0, 7200), rel_time(0, 3 * 86400)] == ["방금", "2분 전", "2시간 전", "3일 전"]
      assert rel_time(0, 40 * 86400) == "1970-01-01"
  ```

  (`...` 부분은 `EasyGitApp(repo)`를 띄워 `app.query_one("#commits")`, `app.query_one(DiffView)`를 꺼내는 준비 코드다. 단언문은 위에 적힌 그대로 쓴다.)

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT/test_app.py -q`
  기대 결과: `ModuleNotFoundError: easy_git.app`

- [ ] **Step 3: `diffview.py`를 구현한다**

  - **렌더링**
    - 합쳐 보기는 `Static` 한 개다. CSS `width: auto`로 두어 긴 줄은 가로 스크롤한다.
    - 좌우 보기는 `Horizontal` 안에 `Static` 두 개(`width: 1fr`)를 넣고 넘치는 부분은 자른다.
    - 둘 다 `rich.text.Text`에 `no_wrap=True`로 한 행 = 한 줄이 되게 한다. 그래서 행 번호가 곧 스크롤 y가 된다.
  - **줄 형식**
    - 합쳐 보기: `f"{new_no or '':>5} {mark} {text}"`. mark는 `+`, `-`, 공백이다. 지워진 줄에는 새 번호를 붙이지 않는다.
    - 좌우 보기: `f"{no or '':>5} {text}"`. 한쪽이 없으면 빈 줄을 `FILL` 스타일로 채운다.
  - **스타일 상수**: `ADD = "on #2f4030"`, `DEL = "on #4a2c31"`, `FILL = "on #3b4252"`. `change` 행은 왼쪽 DEL, 오른쪽 ADD다. 커서 행의 번호 칸은 `reverse`다.
  - **빈 경우**: `rows`가 `None`이면 "바이너리 파일", `[]`이면 "내용 변경 없음" 한 줄을 보여준다.
  - **`show`**
    - `source`를 저장하고, mode가 `"side"`면 `side_rows(source)`를 `rows`로 쓴다.
    - `keep_scroll`이 거짓이면 `cursor_row`를 첫 변경(없으면 0)에 두고, 그 행이 화면 위에서 1/3쯤 오게 스크롤한다.
    - `keep_scroll`이 참이면 현재 `scroll_y`를 유지한다.
  - **`set_mode`**: 같은 `source`로 다시 그린다.
  - **`next_change` / `prev_change`**: 현재 `rows`의 `change_starts` 중 `cursor_row`보다 큰(작은) 첫 값으로 옮기고 그 행을 보이게 한다. 더 없으면 그대로 둔다.
  - 큰 `Static`이 느려지는 경우를 대비해 `# ponytail: Static 전체 렌더링. 수만 줄에서 느리면 render_line 기반 ScrollView로` 주석을 단다.

- [ ] **Step 4: `app.py`를 구현한다**

  - `theme = "nord"`.
  - 배치: `Horizontal(#left: Vertical(#commits, #files), #right: Vertical(#message, #diff))`에 `Footer`를 더한다. `#left` 너비는 40%다.
  - **커밋 목록**: 첫 옵션은 `"● 작업 중인 변경 ({len(staged)+len(unstaged)})"`이고, 그 뒤로 `f"{short}  {subject}  {rel_time(when, now)}"`를 나열한다.
  - **파일 목록**
    - 작업 중인 변경이면 `Stage된 변경 (k)` 제목과 그 파일들, `Stage 안 된 변경 (m)` 제목과 그 파일들을 둔다.
    - 커밋이면 파일만 나열한다.
    - 한 줄 형식은 `f"{status} {path}  +{added} -{deleted}"`다. 이름 변경은 `f"R {old_path} → {path}"`, 바이너리는 숫자 대신 `바이너리`라고 쓴다.
  - **`message_text`**
    - 커밋: `f"{short}  {subject}\n{author} · {YYYY-MM-DD HH:MM}"`에, body가 있으면 `"\n\n" + body`를 붙인다.
    - 작업 중인 변경: `"작업 중인 변경 (커밋 전)"`.
    - 이 값을 `#message`에 넣는다.
  - **흐름**
    - `#commits`에서 `OptionHighlighted`가 오면 파일 목록을 채우고 첫 파일(제목 옵션 제외)을 highlight한다.
    - `#files`에서 `OptionHighlighted`가 오면 `file_rows`를 `@work(thread=True, exclusive=True)`로 불러와 `diff.show`를 호출한다.
    - git 호출은 전부 스레드 worker에서 한다.
  - **키 (`BINDINGS`, Footer에 한국어 설명)**: `v` 보기 전환, `n` 다음 변경, `p` 이전 변경, `q` 닫기. `v`는 `view_mode`를 뒤집고 `diff.set_mode`를 호출한다.
  - **`rel_time`**: 60초 미만 `"방금"`, 1시간 미만 `"{분}분 전"`, 하루 미만 `"{시}시간 전"`, 30일 미만 `"{일}일 전"`, 그 이상은 로컬 날짜 `YYYY-MM-DD`.

- [ ] **Step 5: 통과를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT -q`
  기대 결과: 전부 통과

- [ ] **Step 6: 커밋한다**

  `git add src/easy_GIT/easy_git/diffview.py src/easy_GIT/easy_git/app.py test/easy_GIT/test_app.py`
  `git commit -m "feat(easy_GIT): 세 칸 화면과 파일 전체 diff 보기" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 5: 칸 크기에 따른 배치

**Files:**
- Modify: `src/easy_GIT/easy_git/app.py`
- Test: `test/easy_GIT/test_app.py`

**Interfaces:**
- Consumes: `EasyGitApp`, `DiffView` (Task 4)
- Produces:
  - 상수 `NARROW_BELOW = 90`, `SIDE_FROM = 160`
  - `layout_for(width: int) -> Literal["narrow","medium","wide"]`
  - 속성 `EasyGitApp.layout_name: str`, `EasyGitApp.narrow_page: Literal["list","diff"]`

- [ ] **Step 1: 실패하는 테스트를 덧붙인다**

  ```python
  def test_layout_for():
      assert [layout_for(w) for w in (89, 90, 159, 160)] == ["narrow", "medium", "medium", "wide"]

  def test_medium_forces_unified_and_restores_side(repo):
      # 200x50 에서 v → diff.mode == "side"
      # await pilot.resize_terminal(120, 40); settle → app.layout_name == "medium", diff.mode == "unified", app.view_mode == "side"
      # await pilot.resize_terminal(200, 50); settle → diff.mode == "side"

  def test_narrow_pages_between_list_and_diff(repo):
      # 70x30: app.layout_name == "narrow", app.narrow_page == "list", #right.display is False
      # #files 에 focus 후 press("enter") → narrow_page == "diff", #left.display is False, #right.display is True
      # press("escape") → narrow_page == "list", #files 에 focus
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT/test_app.py -q`
  기대 결과: `ImportError: cannot import name 'layout_for'`

- [ ] **Step 3: 구현한다**

  - App의 `on_resize`(그리고 마운트 시점)에서 `layout_name`을 다시 계산한다. 화면 CSS 클래스 `-narrow`와 `-page-diff`로 `#left` / `#right`의 `display`를 바꾼다.
  - 본문에 실제로 쓰는 보기는 `"side" if view_mode == "side" and layout_name == "wide" else "unified"`다. 이 값이 바뀔 때만 `diff.set_mode`를 호출한다. `view_mode` 자체는 유지한다.
  - 좁음 배치에서 `#files`의 `OptionSelected`(Enter)가 오면 `narrow_page = "diff"`로 바꾸고 본문에 focus한다. `escape` 바인딩은 `narrow_page = "list"`로 바꾸고 `#files`에 focus한다. 다른 배치에서 `escape`는 아무것도 하지 않는다.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT -q`
  기대 결과: 전부 통과

- [ ] **Step 5: 커밋한다**

  `git commit -am "feat(easy_GIT): 칸 크기에 맞춘 반응형 배치" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 6: stage·커밋 화면 + 자동 새로 고침

**Files:**
- Modify: `src/easy_GIT/easy_git/app.py`
- Test: `test/easy_GIT/test_app.py`

**Interfaces:**
- Consumes: `stage`, `unstage`, `commit`, `snapshot`, `GitError` (Task 2·3), `EasyGitApp` (Task 4·5)
- Produces:
  - `class CommitScreen(ModalScreen[str | None])` — `Input` 하나. Enter를 누르면 값으로 닫히고, Esc를 누르면 `None`으로 닫힌다.
  - `class ResultScreen(ModalScreen[None])` — 속성 `text: str`. Esc나 Enter로 닫힌다.
  - `EasyGitApp.reload() -> None` — 선택과 스크롤을 유지하며 다시 읽는다.

- [ ] **Step 1: 실패하는 테스트를 덧붙인다**

  ```python
  def test_space_stages_highlighted_unstaged_file(repo):
      # #files 에서 "unstaged:config.py" 를 highlight, press("space"), settle
      # → working_changes(repo)[0] 의 경로 == ["config.py"], 파일 목록에 "staged:config.py" 존재

  def test_commit_flow_with_korean_message(repo):
      # config.py stage 후 press("c") → isinstance(app.screen, CommitScreen)
      # app.screen.query_one(Input).value = "테스트 커밋"; press("enter"); settle
      # → commits(repo)[0].subject == "테스트 커밋", app.screen 은 메인 화면

  def test_commit_failure_shows_git_output(repo):
      # pre-commit 훅이 "hook says no" 출력 후 exit 1 → c, 메시지 입력, enter
      # → isinstance(app.screen, ResultScreen) and "hook says no" in app.screen.text

  def test_commit_with_nothing_staged_does_not_open_input(repo):
      # stage 안 함 → press("c") → not isinstance(app.screen, CommitScreen)

  def test_auto_refresh_picks_up_external_edit(repo):
      # EasyGitApp(repo, poll_interval=0.1) → 화면이 뜬 뒤 config.py 의 line9 를 "AGENT\n" 으로 바꿈
      # 최대 3초 동안 settle 을 반복 → any(r.text == "AGENT" for r in diff.rows)

  def test_refresh_keeps_selection_and_scroll(repo):
      # 200줄 long.txt(1번 줄 수정)와 other.txt(수정)
      # long.txt 를 highlight, diff.scroll_to(y=50, animate=False)
      # other.txt 를 다시 수정, app.reload(); settle
      # → #files highlighted id == "unstaged:long.txt" and diff.scroll_y == 50

  def test_poll_survives_git_error(repo, monkeypatch):
      # 화면이 뜬 뒤 monkeypatch.setattr(gitio, "snapshot", 항상 GitError("index.lock") 던지는 함수)
      # poll_interval=0.1 로 0.5초 기다림 → app.is_running 이고 diff.rows 가 그대로
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT/test_app.py -q`
  기대 결과: `ImportError: cannot import name 'CommitScreen'`

- [ ] **Step 3: 구현한다**

  - **`space` (stage 전환)**: 지금 highlight된 파일 id가 `unstaged:`이면 `stage`, `staged:`이면 `unstage`를 호출한 뒤 `reload()`한다. 커밋의 파일에서 누르면 `notify("작업 중인 변경의 파일에서만 됩니다")`.
  - **`c` (커밋)**
    - stage된 것이 없으면 `notify("Stage된 파일이 없습니다.")`만 한다.
    - 있으면 `push_screen(CommitScreen(), callback)`을 연다. callback은 값이 `None`이 아닐 때 worker에서 `commit`을 호출한다.
    - 실패하면 `ResultScreen(out)`을 띄우고, 성공하면 `notify(f"커밋했습니다: {새 HEAD short}")` 후 `reload()`한다.
  - **`r`**: 바로 `reload()`한다.
  - **자동 새로 고침**
    - `set_interval(poll_interval, …)`로 thread worker에서 `gitio.snapshot`을 호출한다. 이 호출은 `gitio.snapshot` 형태로 해서, monkeypatch가 먹히게 한다.
    - 이전 값과 다르면 `call_from_thread(self.reload)`를 호출한다.
    - `GitError`와 `OSError`는 조용히 넘기고 다음 주기에 다시 시도한다.
  - **`reload`**
    - 커밋 목록·파일 목록을 다시 만들되, highlight id(`"WORKING"` / sha, `group:path`)가 남아 있으면 그대로 유지한다. 없으면 커밋은 0번, 파일은 같은 인덱스(범위를 넘으면 마지막)로 둔다.
    - 같은 파일이면 `diff.show(..., keep_scroll=True)`로 다시 그린다.
    - 목록을 다시 만드는 동안 생기는 highlight 이벤트로 본문이 처음 위치로 돌아가지 않게 막는다.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT -q`
  기대 결과: 전부 통과

- [ ] **Step 5: 커밋한다**

  `git commit -am "feat(easy_GIT): stage·커밋 화면과 자동 새로 고침" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

---

### Task 7: 실행 진입점 + Herdr에 연결

**Files:**
- Create: `src/easy_GIT/easy_git/__main__.py`
- Test: `test/easy_GIT/test_main.py`
- Modify (저장소 밖, 사용자 설정): `%APPDATA%\herdr\config.toml`

**Interfaces:**
- Consumes: `repo_root` (Task 2), `EasyGitApp` (Task 4)
- Produces: `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

  ```python
  def test_main_not_a_repo_waits_for_enter(tmp_path, monkeypatch, capsys):
      calls = []
      monkeypatch.setattr("builtins.input", lambda prompt="": calls.append(prompt) or "")
      assert main([str(tmp_path)]) == 1
      assert "git 저장소가 아닙니다" in capsys.readouterr().out and len(calls) == 1

  def test_main_opens_repo_root_from_subdir(repo, monkeypatch):
      seen = []
      monkeypatch.setattr(EasyGitApp, "run", lambda self, *a, **k: seen.append(self.repo))
      sub = repo / "x"; sub.mkdir()
      assert main([str(sub)]) == 0 and seen == [repo.resolve()]
  ```

- [ ] **Step 2: 실패를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT/test_main.py -q`
  기대 결과: `ModuleNotFoundError: easy_git.__main__`

- [ ] **Step 3: `main`을 구현한다**

  - 인자가 있으면 그 경로를, 없으면 현재 폴더를 쓴다.
  - `repo_root`가 `None`이면 `git 저장소가 아닙니다: {경로}`를 출력하고 `input("Enter를 누르면 닫습니다...")` 후 `1`을 돌려준다. Herdr의 `type = "pane"` 칸은 프로그램이 끝나면 바로 닫히기 때문에, 이렇게 해야 안내를 읽을 수 있다.
  - 저장소면 `EasyGitApp(root).run()` 후 `0`을 돌려준다.
  - `if __name__ == "__main__": raise SystemExit(main())`.

- [ ] **Step 4: 통과를 확인한다**

  실행: `uv run --project src/easy_GIT pytest test/easy_GIT -q`
  기대 결과: 전부 통과
  그리고 `uv sync --project src/easy_GIT`를 다시 돌린 뒤 `src/easy_GIT/.venv/Scripts/easy_GIT.exe D:/`를 실행한다(git 저장소가 아닌 폴더). 기대 결과: 안내 문구가 나오고 Enter를 기다린다.

- [ ] **Step 5: Herdr에 연결한다**

  `%APPDATA%\herdr\config.toml` 끝, 기존 lazygit 블록 아래에 다음을 덧붙인다. 기존 내용은 건드리지 않는다.

  ```toml
  # prefix+alt+e → 현재 pane 폴더의 git 변경·커밋을 easy_GIT 칸으로 (q 로 닫기)
  [[keys.command]]
  key = "prefix+alt+e"
  type = "pane"
  command = 'D:\ADE_sub\src\easy_GIT\.venv\Scripts\easy_GIT.exe'
  description = "git 보기 (easy_GIT)"
  ```

  `herdr server reload-config`를 실행한다. 기대 결과: 오류 없이 끝난다.

- [ ] **Step 6: Herdr 안에서 직접 확인한다** (사용자와 함께)

  - [ ] git 저장소 칸에서 `prefix+alt+e` → 새 칸이 열리고 **그 칸의 폴더** 저장소가 보인다. 다른 폴더가 열리면 여기서 멈추고 사용자에게 보고한다. Herdr가 `type = "pane"` 명령을 어느 폴더에서 실행하는지는 설계 §5에서 확인이 필요하다고 한 부분이다.
  - [ ] `prefix+z`로 키우면 `v`로 좌우 보기가 된다. 칸을 줄이면 합쳐 보기로, 아주 좁히면 한 칸씩 넘겨 보기로 바뀐다.
  - [ ] 커밋 메시지 입력에 한글 IME로 "한글 커밋"을 쳐서 커밋하면 커밋 목록에 그대로 보인다.
  - [ ] 옆 칸에서 파일을 고치면 1~2초 안에 화면에 반영된다.
  - [ ] `q`로 닫으면 칸도 닫힌다.

- [ ] **Step 7: 커밋한다**

  `git add src/easy_GIT/easy_git/__main__.py test/easy_GIT/test_main.py`
  `git commit -m "feat(easy_GIT): 실행 진입점과 Herdr 칸 연결" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`
  (Herdr 설정 파일은 저장소 밖이라 커밋하지 않는다.)
