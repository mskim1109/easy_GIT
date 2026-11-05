# easy_GIT & File_viewer

Two terminal tools for [Herdr](https://github.com/herdrdev/herdr) (a terminal multiplexer for coding agents). Keep them in a pane next to an agent and see what it is changing without leaving Herdr.

| Tool | What it is |
|---|---|
| [**easy_GIT**](#easy_git) | Git viewer. Shows changed files **in full** with the changes marked inline, plus stage and commit. |
| [**File_viewer**](#file_viewer) | File browser. File tree + tabs: code with syntax highlighting, rendered Markdown, quick edits; HTML opens in the browser. |

Both are built with Python and [Textual](https://textual.textualize.io), and developed and tested on **Windows 11** inside Herdr 0.9.5 (classic console window). They are separate projects in one repository: install, run and build each one on its own.

```
src/easy_GIT/      easy_GIT project   (pyproject.toml, uv.lock, easy_GIT.spec)
src/File_viewer/   File_viewer project (pyproject.toml, uv.lock, File_viewer.spec)
test/<tool>/       tests
docs/design/       design notes and plans (Korean)
```

## Requirements

- Windows 11. File_viewer uses Windows APIs (Explorer, clipboard, registry) and runs only on Windows.
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- git on `PATH`
- Optional: [Herdr](https://github.com/herdrdev/herdr) for the pane key bindings and `--follow`
- Optional (File_viewer): [`mermaid-ascii`](https://github.com/AlexanderGrooff/mermaid-ascii) 1.6.1+ on `PATH` to draw Mermaid diagrams in Markdown

## Install

```sh
git clone https://github.com/mskim1109/easy_GIT.git
cd easy_GIT
uv sync --project src/easy_GIT
uv sync --project src/File_viewer
```

Each `uv sync` creates the project's own `.venv` with a launcher:

- `src\easy_GIT\.venv\Scripts\easy_GIT.exe`
- `src\File_viewer\.venv\Scripts\File_viewer.exe`

## Run

```sh
uv run --project src/easy_GIT easy_GIT [--follow] [path]
uv run --project src/File_viewer File_viewer [--follow] [path]
```

- Without `path`, the current directory is used.
  - easy_GIT opens the git repository that contains it (it walks up to the repository root).
  - File_viewer shows that folder as the top of the tree (it does **not** walk up to the repository root).
- `--follow` is for a separate window (e.g. on another monitor). It starts at the folder of the pane focused in Herdr, checks every second, and switches when you focus another pane. Needs Herdr to be running.

## Build the .exe (optional, recommended for Herdr)

A folder build with PyInstaller starts faster and does not depend on the source checkout. Run from the repository root in PowerShell; change `--distpath` to wherever you keep tools:

```powershell
uv run --project src/easy_GIT --with pyinstaller pyinstaller src/easy_GIT/easy_GIT.spec --noconfirm --distpath D:\Tools --workpath "$env:TEMP\eg-build"
uv run --project src/File_viewer --with pyinstaller pyinstaller src/File_viewer/File_viewer.spec --noconfirm --distpath D:\Tools --workpath "$env:TEMP\fv-build"
```

Result:

| Folder | Files |
|---|---|
| `D:\Tools\easy_GIT\` | `easy_GIT.exe` |
| `D:\Tools\File_viewer\` | `File_viewer.exe` (the viewer) and `File_viewer_right.exe` (no window; splits a Herdr pane and starts the viewer in it) |

Keep the two File_viewer exes in the same folder: `File_viewer_right.exe` starts the `File_viewer.exe` next to it. git still has to be on the PC's `PATH`. Rebuild after changing the code.

## Herdr setup

Add key bindings to Herdr's config, `%APPDATA%\herdr\config.toml`. The example uses the exes built above in `D:\Tools`; adjust the paths.

```toml
# prefix+alt+e: easy_GIT for the current pane's repository (q closes it)
[[keys.command]]
key = "prefix+alt+e"
type = "pane"
command = 'D:\Tools\easy_GIT\easy_GIT.exe'
description = "git viewer (easy_GIT)"

# prefix+alt+shift+e: easy_GIT in its own window that follows the focused pane
[[keys.command]]
key = "prefix+alt+shift+e"
type = "shell"
command = 'start "easy_GIT" "D:\Tools\easy_GIT\easy_GIT.exe" --follow'
description = "git viewer (easy_GIT, separate window)"

# prefix+alt+f: split the pane to the right and open File_viewer at its folder
# (q closes File_viewer and the new pane)
[[keys.command]]
key = "prefix+alt+f"
type = "shell"
command = 'D:\Tools\File_viewer\File_viewer_right.exe'
description = "file viewer (File_viewer, right pane)"

# prefix+alt+shift+f: File_viewer in its own window that follows the focused pane
[[keys.command]]
key = "prefix+alt+shift+f"
type = "shell"
command = 'start "File_viewer" "D:\Tools\File_viewer\File_viewer.exe" --follow'
description = "file viewer (File_viewer, separate window)"
```

Then reload the config:

```sh
herdr server reload-config
```

Notes:

- `prefix+alt+f` uses `type = "shell"` because in Herdr 0.9.5 `type = "pane"` opens a temporary pane over the whole tab. `File_viewer_right.exe` asks Herdr to split the pane you pressed the key in, then runs File_viewer in the new pane. It assumes the new pane's shell is PowerShell.
- Without building exes, point the commands at the source launchers instead: `...\src\easy_GIT\.venv\Scripts\easy_GIT.exe`, `...\src\File_viewer\.venv\Scripts\File_viewer.exe`, and for the right split `...\src\File_viewer\.venv\Scripts\pythonw.exe -m file_viewer.herdr_right`.
- Herdr runs custom commands with `cmd.exe /d /c`, so `start` opens a new console window.
- If a pane opens on a folder that is not a git repository (easy_GIT) or not a folder (File_viewer), the tool prints why and waits for Enter so you can read it before the pane closes.

---

## easy_GIT

Shows every changed file from top to bottom with the changes marked, so you read a diff in the context of the whole file instead of isolated hunks.

### Features

- **Full-file diffs**: added (`+`) and removed (`-`) lines marked in place.
- **Unified or side-by-side**: press `v` to switch (side-by-side needs a wide pane).
- **Syntax highlighting**: VS Code Dark+ colors, language picked from the file extension.
- **Working changes and history**: uncommitted changes (split into *Staged* / *Unstaged*) at the top, then the commit list with full commit messages.
- **File tree**: folders collapse and expand; status letters are colored (M yellow, A green, D red, R teal).
- **Stage and commit**: stage or unstage a file or a whole folder with `space`, commit with `c`. Pre-commit hooks run as usual.
- **Auto refresh**: keeps up with files an agent is editing next to it. Reads git without taking its lock (`GIT_OPTIONAL_LOCKS=0`), so it does not get in the agent's way.
- **Responsive layout**: three panes when there is room, one pane at a time in a narrow split (under 90 columns). Drag the borders with the mouse to resize.

### Keys

| Key | Action |
|---|---|
| `↑` `↓` | Move in lists, scroll the diff |
| `Tab` / `Shift+Tab` | Move between panes |
| `Enter` | Expand/collapse a folder; in a narrow pane, open the file |
| `←` / `→` | Collapse / expand a folder |
| `Esc` | Back to the list (narrow pane) |
| `v` | Unified ↔ side-by-side |
| `n` / `p` | Next / previous change |
| `space` | Stage ↔ unstage the file or folder |
| `c` | Commit staged changes (one-line message) |
| `r` | Refresh |
| `q` | Quit |

Mouse: click to select, wheel to scroll, drag the pane borders to resize (the size is applied when you release).

### What it does not do

Only stage, unstage and commit change the repository. There is no discard, amend, push or pull.

---

## File_viewer

A file tree on the left and tabs on the right, meant to stay open in the pane next to an agent. The on-screen labels are in Korean.

### Features

- **Tree + tabs**: pick a file in the tree and it opens in a tab; open several and switch between them.
- **Shows everything**: nothing is hidden. `.git` and files matched by `.gitignore` are shown dimmed. Folders are read only when you expand them, so large folders like `node_modules` stay fast.
- **git marks**: `M` = changed since the last commit (staged or not), `+` = untracked, `•` on a collapsed folder = something inside changed. Marks stay until you commit. Outside a git repository files still show, without marks.
- **Auto refresh** (every second): open tabs, expanded folders and git marks follow the agent's edits. It never moves you: the current tab, tree selection and scroll stay where they are. A deleted file keeps its tab, marked as deleted.
- **Responsive layout**: under 80 columns the tree hides and `t` switches between the tree and the content.
- **Encodings**: UTF-8 (with or without BOM) and CP949 display correctly. Anything else is shown with replacement characters and can't be edited.

### File types

| Type | In the tab | `o` |
|---|---|---|
| Code, config, text, JSON | Source with line numbers and syntax highlighting | Default program |
| Markdown | Rendered (headings, lists, tables, code blocks); `v` toggles source. Mermaid blocks get a text drawing below them (flowchart, sequence, ER; needs `mermaid-ascii`). Images show as `[그림: alt]` text | Default program (e.g. Obsidian) |
| HTML | Source with highlighting | Always the default **browser**, even if `.html` is associated with something else |
| Images, PDF, binary, files over 20 MB | A note to open it with `o` | Default program |

### Keys

| Key | Action |
|---|---|
| `↑` `↓` / `Enter` | Move in the tree / open a file, expand a folder |
| `/` | Find a file by name, open it in a tab |
| `Tab` / `Shift+Tab` | Next / previous tab |
| `w` | Close the tab |
| `t` | Hide/show the tree (narrow: tree ↔ content) |
| `[` / `]` | Narrower / wider tree |
| `v` | Markdown: rendered ↔ source |
| `o` | Open in the default program (HTML: browser) |
| `m` | Menu (same as right-click) |
| `e` or `Ctrl+E` | Edit the current tab (`Ctrl+E` also works while the Korean IME is on) |
| `Ctrl+S` | Save (while editing) |
| `Esc` | Stop editing |
| `q` | Quit |

Mouse: click a tree item to open it, click a tab to switch, wheel to scroll. **Right-click** a tree item (or press `m`) for a menu: *Reveal in Explorer*, *Copy path* (full path to the clipboard), *Open with default program*. Inside a Herdr pane, File_viewer takes over right-click while it runs and gives it back to Herdr when it quits.

### Editing

- Edit, then `Ctrl+S` to save and `Esc` to go back to viewing. Leaving or closing a tab with unsaved edits asks first.
- If the file changed on disk after you started editing (an agent wrote to it), saving asks before overwriting.
- Saving keeps the original encoding (UTF-8 / CP949, BOM or not) and line endings (CRLF / LF).
- Markdown is edited as source.
- A tab being edited is not auto-refreshed.

### What it does not do

The tree is view-only: no create, delete, rename or move. Find matches file names, not contents. No git actions (use easy_GIT). No image or PDF preview. To look at another folder, start another File_viewer with that path.

---

## Tests

```sh
uv run --project src/easy_GIT pytest test/easy_GIT -q
uv run --project src/File_viewer pytest test/File_viewer -q
```

## License

[MIT](LICENSE)
