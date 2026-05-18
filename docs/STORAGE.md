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
└── log                                  # daemon log (M8)

$XDG_RUNTIME_DIR/devpane/                # 0700, ephemeral
└── devpane.sock                         # IPC socket (M2)
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

## Atomic writes

`store.notes.write_atomic` ensures the on-disk file is never partially
written:

1. Create a temp file in the same directory (`.foo.md.XXXXXX.tmp`).
2. Write the body, `flush()`, `fsync()`.
3. `os.replace(tmp, target)` — atomic on POSIX same-filesystem renames.
4. On any exception, the temp file is removed.

Worst-case data loss is bounded by the autosave debounce window (2 seconds).

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
