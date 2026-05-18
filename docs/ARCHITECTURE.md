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

- **Filesystem of record.** Each note is one `.md` file under
  `$XDG_DATA_HOME/devpane/notes/`. Writes go via `os.replace` for atomicity.
- **Derived index.** `index.sqlite` holds an FTS5 virtual table plus recency
  and pinned flags. It is rebuildable from disk at any time — never the only
  copy of anything.
- **Autosave.** 2-second debounce on `buffer.changed` plus a forced flush on
  `hide()`.
- **External edits.** The daemon re-reads the active note's file on `show()`
  so changes made by other tools (editor, `git pull`, Syncthing) are visible.

## IPC

A Unix domain socket at `$XDG_RUNTIME_DIR/devpane.sock` carries
line-delimited JSON:

```
{"cmd":"toggle"}
{"cmd":"show"}
{"cmd":"hide"}
{"cmd":"new-note"}
{"cmd":"status"}
```

The daemon also exposes an optional D-Bus name `com.devpane.Daemon` with the
same surface, so scripts and tray indicators can drive it without the socket.

## Single-instance behaviour

On startup, `devpaned` checks for an existing socket. If a daemon is already
running, the second invocation acts as a toggle and exits. This lets users
bind `devpaned` itself as the hotkey if they prefer not to install the CLI.

## Failure modes and recovery

- **Daemon killed mid-edit.** Atomic writes mean the on-disk file is never
  half-written. The 2-second autosave bounds data loss.
- **Corrupt index.** `reindex_all()` is idempotent; the index is deleted and
  rebuilt from the filesystem.
- **Compositor restart (Wayland).** The daemon reconnects; the window is
  recreated on next `show`.
- **`gtk4-layer-shell` missing.** The Wayland fallback adapter is used
  without warning to the user.
