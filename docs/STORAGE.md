# DevPane — Storage

DevPane is **files-first**: every note lives as a plain markdown file on disk.
The SQLite index is a derived cache and can be deleted at any time — the
filesystem is the source of truth.

## On-disk layout

```
$XDG_DATA_HOME/devpane/                  # default: ~/.local/share/devpane/
├── notes/
│   ├── scratch.md                       # default note, auto-created on first use
│   ├── meeting-2026-05-18.md
│   └── ...
└── index.sqlite                         # derived; rebuildable

$XDG_STATE_HOME/devpane/                 # default: ~/.local/state/devpane/
├── devpane.log                          # current daemon log
└── devpane.log.{1,2,3}                  # rotated logs (1 MB each)

$XDG_RUNTIME_DIR/devpane/                # 0700, ephemeral
├── devpane.sock                         # IPC socket
└── devpane.pid                          # single-instance flock target

$XDG_CONFIG_HOME/devpane/                # default: ~/.config/devpane/
└── prefs.json                           # height ratio, last-open note, animate
```

Path resolution lives in [`store/paths.py`](../src/devpane/store/paths.py)
and honors all standard `XDG_*` env vars. Tests redirect these via the
`xdg_tmp` fixture in [`tests/conftest.py`](../tests/conftest.py) so the suite
never touches your real state.

## Note name rules

Implemented in `store.notes.canonical_name`:

- The `.md` suffix is appended automatically if missing.
- The stem must match `^[A-Za-z0-9_][A-Za-z0-9._-]*$`.
- Rejected: directory separators (`foo/bar`), leading dots (`.hidden`), empty
  strings, whitespace, parent references (`../escape`).
- Rejection raises `InvalidNoteName` (a `ValueError`).

These rules apply at the API boundary — callers can pass either `"foo"` or
`"foo.md"` interchangeably.

## Task frontmatter

Each note doubles as a task. Task metadata lives in an optional
frontmatter block at the top of the file, delimited by `---` lines:

```markdown
---
title: Buy milk
done: false
created: 2026-05-22T18:30:00
---
note body goes here
```

Recognized fields (all optional, string-valued):

| Key | Meaning |
|-----|---------|
| `title` | Display name in the task sidebar. Defaults to the filename stem. |
| `done` | `"true"` if the task is completed, `"false"` otherwise. Defaults to `"false"`. |
| `created` | ISO-ish timestamp written when a task is created from the UI. Informational. |
| `sprint` | ISO timestamp identifying the sprint this task belongs to. See **Sprints** below. |

The parser (`store.notes._parse_frontmatter`) is deliberately minimal —
flat `key: value` scalars only, with optional surrounding single or
double quotes. A missing or malformed block is treated as no
frontmatter, so plain pre-existing `.md` files keep working as undone
tasks titled by their filename stem.

Helper functions in `store.notes`:

- `read_task(name) -> (meta, body)` — parse on read.
- `write_task(name, meta, body)` — atomic write with header.
- `is_done(name)`, `get_title(name)` — convenience readers.
- `set_done(name, bool)`, `set_title(name, str)` — preserve existing
  fields and body.

The editor only ever sees `body`; the autosave path reads the existing
`meta` from disk and writes it back unchanged on every save, so manual
edits to frontmatter are not destroyed by typing.

## Sprints

Tasks are grouped into **sprints**. A sprint is identified by an ISO
timestamp written when the sprint first comes into existence (typically:
a task is migrated past the last existing sprint, or the first task is
created on a fresh install). The id is stored in each task's
`sprint:` frontmatter field; sprints are therefore **emergent** —
`store.sprints.list_existing()` rebuilds the list by scanning every
task on disk.

Display names default to the date portion of the id (`YYYY-MM-DD`).
Renames are persisted in:

```
$XDG_DATA_HOME/devpane/sprints.json   # {sprint_id: display_name}
```

The registry contains rename overrides only — deleting it loses names
but not sprint membership. Empty / whitespace / default-equal names
remove the override.

API in [`store/sprints.py`](../src/devpane/store/sprints.py):

- `Sprint(id, name)` — materialized for the UI.
- `list_existing() -> list[Sprint]` — sorted chronologically.
- `next_of(id, sprints)`, `prev_of(id, sprints)` — navigation helpers.
- `new_sprint_id(now?) -> str` — mint a fresh id from the clock.
- `rename_sprint(id, name)` — persist a name override.
- `bootstrap_existing()` — one-shot: assign a sprint id to any
  un-sprinted task on disk (reuses the most recent existing id, or
  mints a new one if none exists). Called by the daemon at startup.

On `store.notes`:

- `get_sprint(name) -> str | None`
- `set_sprint(name, id)` — atomic write, preserves body and other meta.

## Atomic writes

`store.notes.write_atomic` ensures the on-disk file is never partially
written:

1. Create a temp file in the same directory (`.foo.md.XXXXXX.tmp`).
2. Write the body, `flush()`, `fsync()`.
3. `os.replace(tmp, target)` — atomic on POSIX same-filesystem renames.
4. On any exception, the temp file is removed.

Worst-case data loss is bounded by the autosave debounce window (2 seconds).

If the daemon is killed between step 2 and step 3, the `.tmp` file is left
behind but the original note (if any) is untouched. On next startup,
`notes.cleanup_orphans()` (M8) sweeps the notes directory and removes any
`.<name>.<rand>.tmp` files. The orphan content is discarded — the original
write didn't complete, so its body is partial / not durable.

## Index schema

Defined in [`store/migrations/0001_init.sql`](../src/devpane/store/migrations/0001_init.sql):

| Table / virtual table | Purpose |
|-----------------------|---------|
| `notes(name, body, updated_at, pinned, cursor_offset)` | Denormalized copy of disk; primary key on `name`. `cursor_offset` added by migration 0002 to remember the editor's cursor position per note. |
| `notes_fts` (FTS5, `content='notes'`) | Full-text search; tokenizer `unicode61 remove_diacritics 2` |
| `schema_migrations(name, applied_at)` | Tracks applied migrations by filename |

Three triggers (`notes_ai`, `notes_au`, `notes_ad`) keep `notes_fts` in sync
with `notes` on insert/update/delete. The index opens in WAL journal mode for
concurrent reader compatibility.

## Inspecting state

```sh
# List all notes
ls -1 ~/.local/share/devpane/notes/

# Grep across all notes
grep -rn "TODO" ~/.local/share/devpane/notes/

# Inspect the index
sqlite3 ~/.local/share/devpane/index.sqlite '.tables'
sqlite3 ~/.local/share/devpane/index.sqlite 'SELECT name, updated_at, pinned FROM notes ORDER BY updated_at DESC;'
sqlite3 ~/.local/share/devpane/index.sqlite \
    "SELECT name, snippet(notes_fts, 1, '[', ']', '…', 12) FROM notes_fts WHERE notes_fts MATCH 'TODO';"
```

## Backup and sync

Because notes are plain files, any standard tool works:

- **Git**: `cd ~/.local/share/devpane/notes && git init`
- **Syncthing / Dropbox / rclone**: point them at the notes dir
- **Tar**: `tar czf devpane-notes-backup.tgz -C ~/.local/share/devpane notes`

The index (`index.sqlite`) does *not* need to be backed up — it's rebuilt
from the filesystem on next daemon start (or call
`index.reindex_all(conn)`).

## Resetting state

```sh
./scripts/reset-state.sh
```

This removes both `$XDG_DATA_HOME/devpane` and `$XDG_STATE_HOME/devpane`
after a confirmation prompt.
