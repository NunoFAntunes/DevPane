# DevPane — Architecture

This document explains the runtime architecture in depth. For the
step-by-step build order, see [PLAN.md](PLAN.md). For a high-level pitch, see
[OVERVIEW.md](OVERVIEW.md).

## Two-process model

```
 ┌─────────────────────┐         ┌──────────────────────────┐
 │ devpane-toggle      │ ──UDS──▶│ devpaned (daemon)        │
 │ (tiny CLI)          │         │  ├─ IPC server           │
 └─────────────────────┘         │  ├─ Hidden GTK4 window   │
        ▲                       │  ├─ GtkSourceView editor  │
        │ bound to F12 in DE    │  ├─ Notes store (FS+SQLite)│
        │                       │  └─ D-Bus service (opt.)  │
 user's keyboard shortcut       └──────────────────────────┘
                                             │
                                             ▼
                            ~/.local/share/devpane/notes/*.md
                            ~/.local/share/devpane/index.sqlite
```

**Why two processes.** A resident daemon eliminates Python's cold-start cost,
so toggling is instant. The CLI is dependency-free and trivial to bind in any
DE's keyboard settings — which sidesteps the entire Wayland global-hotkey
problem.

## Module boundaries

| Layer | Knows about | Does not import |
|-------|-------------|-----------------|
| `daemon/app.py` | Everything — the single wire-up point | — |
| `daemon/ipc.py` | Standard library only | UI, store |
| `ui/*` | GTK, libadwaita, GtkSourceView | `platform/*`, `store/*`, `daemon/*` |
| `platform/*` | GTK, compositor-specific libs (`gtk4-layer-shell`, `python-xlib`) | `ui/*`, `store/*`, `daemon/*` |
| `store/*` | Standard library, `sqlite3` | GTK, IPC, UI |
| `util/*` | Standard library only | Anything project-specific |

The `ui/` layer takes callbacks in its constructor — it never imports IPC or
storage directly. The `platform/` layer is the only place that touches
compositor-specific code; everything else talks to a `PlatformAdapter`
protocol and a `WindowMode` enum.

## Window strategy

Detected at startup:

| Session | Strategy | Module |
|---------|----------|--------|
| Wayland + layer-shell (Sway, Hyprland, KDE Plasma 6) | `gtk4-layer-shell`, `LAYER_TOP`, anchor top/left/right | `platform/wayland_layer.py` |
| Wayland without layer-shell (GNOME) | Top-anchored regular `Adw.Window` | `platform/wayland_plain.py` |
| X11 | Override-redirect + `_NET_WM_WINDOW_TYPE_DOCK` + keyboard grab | `platform/x11.py` |

Detection probes (in order): `XDG_SESSION_TYPE`, `WAYLAND_DISPLAY`,
`HYPRLAND_INSTANCE_SIGNATURE`, `SWAYSOCK`, `KDE_FULL_SESSION`,
`GNOME_SHELL_SESSION_MODE`, then a guarded `gi.require_version` import of
`Gtk4LayerShell`.

## Storage

See [STORAGE.md](STORAGE.md) for the on-disk layout, name rules, and how to
inspect / back up DevPane state.

- **Filesystem of record.** Each note is one `.md` file under
  `$XDG_DATA_HOME/devpane/notes/`. Writes use `tempfile.mkstemp` in the same
  directory + `fsync` + `os.replace` so a crashed daemon never leaves a
  half-written file. Implemented in `store/notes.py`.
- **Name validation.** Stems match `^[A-Za-z0-9_][A-Za-z0-9._-]*$` (no path
  separators, no leading dots, no whitespace). The `.md` suffix is appended
  if missing. Canonicalization happens at the storage API boundary so the
  rest of the code can pass either `"foo"` or `"foo.md"`.
- **Derived index.** `index.sqlite` (WAL mode) holds a `notes` table
  (denormalized copy: `name`, `body`, `updated_at`, `pinned`) and a
  `notes_fts` FTS5 virtual table in *external content* mode
  (`content='notes'`). Insert/update/delete triggers keep them in sync.
  Tokenizer is `unicode61 remove_diacritics 2`.
- **Migrations.** SQL files in `store/migrations/` are applied in lexical
  order. The runner records each filename in `schema_migrations` and skips
  applied ones. Rebuildable: the index can be deleted at any time and
  recovered with `index.reindex_all()` from the filesystem.
- **Autosave.** 2-second debounce on `buffer.changed` (via
  `util.debounce.Debouncer`) plus a forced flush on `hide()`.
- **External edits.** The daemon re-reads the active note's file on `show()`
  so changes made by other tools (editor, `git pull`, Syncthing) are visible.

## IPC

A Unix domain socket at `$XDG_RUNTIME_DIR/devpane/devpane.sock` (mode
`0600`) carries one JSON object per connection. Full protocol reference:
[IPC.md](IPC.md).

The server is implemented in `daemon/ipc.py` using `asyncio.start_unix_server`.
Connections are one-shot (request, response, close). M2 commands: `toggle`,
`show`, `hide`, `status`, `quit`.

**Loop integration (M3 plan).** The M2 daemon runs `asyncio` as its only
loop. When M3 introduces a GTK window, asyncio will move to a dedicated
worker thread and command handlers that touch the UI will post their work to
the GLib main thread via `GLib.idle_add`. The wire protocol is unaffected.

A D-Bus surface (`com.devpane.Daemon`) is planned post-M2 for scripting and
tray indicators.

## Single-instance behaviour

`devpaned` takes an exclusive `fcntl.flock` on
`$XDG_RUNTIME_DIR/devpane/devpane.pid`. A second invocation:

1. Fails to acquire the lock.
2. Probes the socket; if a peer answers, forwards a `toggle` and exits 0.
3. If the lock is held but the socket is non-responsive, exits 1.

This lets users bind either `devpaned` or `devpane-toggle` to a hotkey.
Implementation: `daemon/single_instance.py`.

## Failure modes and recovery

- **Daemon killed mid-edit.** Atomic writes mean the on-disk file is never
  half-written. The 2-second autosave bounds data loss.
- **Corrupt index.** `reindex_all()` is idempotent; the index is deleted and
  rebuilt from the filesystem.
- **Compositor restart (Wayland).** The daemon reconnects; the window is
  recreated on next `show`.
- **`gtk4-layer-shell` missing.** The Wayland fallback adapter is used
  without warning to the user.
