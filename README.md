# easy_GIT

A terminal Git viewer for Herdr (a terminal multiplexer for coding agents). It shows changed files **in full** with the changes marked inline, so you read a diff in the context of the whole file instead of isolated hunks.

Built with Python and [Textual](https://textual.textualize.io). Developed and tested on Windows 11 inside Herdr; it is a regular terminal app, so it runs outside Herdr too.

## Features

- **Full-file diffs** — every changed file is shown from top to bottom with added (`+`) and removed (`-`) lines marked.
- **Unified or side-by-side** — press `v` to switch (side-by-side needs a wide pane).
- **Syntax highlighting** — VS Code Dark+ colors, language picked from the file extension.
- **Working changes and history** — uncommitted changes (split into *Staged* / *Unstaged*) at the top, then the commit list with full commit messages.
- **File tree** — folders can be collapsed and expanded; status letters are colored (M yellow, A green, D red, R teal).
- **Stage and commit** — stage or unstage a file or a whole folder with `space`, commit with `c`. Pre-commit hooks run as usual.
- **Auto refresh** — keeps up with files an agent is editing next to it.
- **Responsive layout** — three panes when there is room, one pane at a time in a narrow split. Drag the borders with the mouse to resize.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- git

## Install

```sh
git clone https://github.com/mskim1109/easy_GIT.git
cd easy_GIT
uv sync --project src/easy_GIT
```

## Run

```sh
uv run --project src/easy_GIT easy_GIT [path-to-repo]
```

Without a path it opens the repository of the current directory. The installed launcher is also available at `src/easy_GIT/.venv/Scripts/easy_GIT.exe` (Windows) or `src/easy_GIT/.venv/bin/easy_GIT`.

### Herdr

Open it in a pane next to the current one with a key binding in Herdr's `config.toml`:

```toml
[[keys.command]]
key = "prefix+alt+e"
type = "pane"
command = 'C:\path\to\easy_GIT\src\easy_GIT\.venv\Scripts\easy_GIT.exe'
description = "git viewer (easy_GIT)"
```

Then reload the config with `herdr server reload-config`.

## Keys

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

## What it does not do

Only stage, unstage and commit change the repository. There is no discard, amend, push or pull.

## Tests

```sh
uv run --project src/easy_GIT pytest test/easy_GIT -q
```

## License

[MIT](LICENSE)
