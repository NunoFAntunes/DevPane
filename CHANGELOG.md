# Changelog

All notable changes to DevPane are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Notes are tasks.** The old header switcher popover is replaced by a
  persistent, collapsible left-side task list. Each row has a checkbox
  for done state and a title (from optional markdown frontmatter,
  falling back to the filename stem). Selecting a task opens its file
  in the editor on the right. Completed tasks are hidden by default,
  toggleable via a footer switch. Right-clicking a row offers
  **Rename** (frontmatter title; file is not renamed) and **Delete**.
  New shortcut `Ctrl+B` toggles the sidebar; `Ctrl+K` (old switcher)
  is removed.

### Added

- `store.notes.read_task` / `write_task` / `set_done` / `set_title` /
  `get_title` / `is_done` helpers, with a tiny built-in YAML-subset
  frontmatter parser (no PyYAML dependency).
- `Prefs.show_sidebar`, `Prefs.show_completed` — persisted across
  daemon restarts.
- **Subtasks.** Each task can have an ordered list of subtasks stored
  in a JSON sidecar at `$XDG_DATA_HOME/devpane/subtasks/<stem>.json`.
  A new middle pane (sits between the task list and the editor, with
  a draggable separator persisted in `Prefs.subtask_panel_width`)
  shows the current task's subtasks: checkbox + click-to-edit text +
  hover-visible delete button. Rows are reorderable by drag-and-drop
  within the current task. Empty-string commit removes a row.
  Sidecars are cleaned up automatically when the parent task is
  deleted. The task list sidebar shows an `n/m` progress suffix on
  tasks that have subtasks.
- **Sprints.** Tasks are grouped into sprints, identified by an ISO
  timestamp stored in the `sprint:` frontmatter field. A new sprint
  bar above the task list shows the current sprint name with prev/next
  arrows (`Alt+Left` / `Alt+Right`); arrows are disabled at the
  chronological ends since sprints exist only when at least one task
  references them. Clicking the name opens a rename dialog; overrides
  are persisted in `$XDG_DATA_HOME/devpane/sprints.json` and default
  to the date portion of the id. Row context menu gains **Move to
  next sprint** / **Move to previous sprint**; "next" creates a new
  sprint dated now when migrating past the last existing one. New
  tasks inherit the current sprint. On startup, any un-sprinted task
  on disk is bootstrapped into one shared sprint so legacy notes stay
  visible.

## [0.1.0] — 2026-05-18

First functionally complete release. Drop-down pane works end-to-end on
KDE Plasma 6 / Wayland with layer-shell; tested headless on other paths.

### Added

- **Skeleton** (M0): `pyproject.toml` with `devpaned` + `devpane-toggle`
  entry points, ruff/mypy/pytest tooling, CI workflow, GPL-3.0 license.
- **Storage layer** (M1): atomic markdown writes via `tempfile.mkstemp`
  + `fsync` + `os.replace`, SQLite + FTS5 index with migration runner,
  thread-safe 2-second autosave debouncer.
- **IPC daemon** (M2): asyncio Unix-socket server, line-delimited JSON
  protocol (`toggle` / `show` / `hide` / `status` / `quit`),
  single-instance enforcement via `fcntl.flock`, sync IPC client used by
  `devpane-toggle`; running `devpaned` twice forwards a toggle to the
  running instance.
- **GTK window** (M3): `Adw.ApplicationWindow` with asyncio↔GLib bridge
  on a worker thread, `--gtk` / `--headless` mode flags with auto-detect,
  session + compositor + layer-shell platform probe.
- **Platform adapters** (M4): `LayerShellAdapter` (wlroots / KDE), plain
  Wayland fallback (GNOME), X11 adapter setting
  `_NET_WM_WINDOW_TYPE_DOCK` + `ABOVE` / `SKIP_TASKBAR` / `SKIP_PAGER`
  via `python-xlib`. Auto-`LD_PRELOAD` re-exec for `gtk4-layer-shell`
  linker order.
- **Editor** (M5): `GtkSourceView` 5 with markdown highlighting,
  monospace + word-wrap, light/dark scheme tracking; header bar with
  note title, new-note button (`Ctrl+N`), and switcher popover
  (`Ctrl+K`); `Escape` hides the pane.
- **Polish** (M6): slide-down animation via `Adw.TimedAnimation`,
  per-note cursor position persisted via SQLite migration
  `0002_cursor.sql`, last-open note + height ratio persisted to
  `$XDG_CONFIG_HOME/devpane/prefs.json`, restored across daemon
  restart.
- **Hardening** (M8): orphan `.tmp` file cleanup on daemon startup,
  rotating file log at `$XDG_STATE_HOME/devpane/devpane.log` (1 MB ×
  3 rotations), `devpane --check` reports session, compositor,
  layer-shell availability, log path.
- **Distribution** (M7): app ID set to `io.github.nfantunes.DevPane`;
  Arch `PKGBUILD`, Flatpak manifest (skeleton), systemd user unit, XDG
  autostart `.desktop`, AppStream `metainfo.xml`, placeholder app SVG,
  GSettings schema. None pushed to AUR or Flathub yet; build locally
  with `makepkg -si` or `flatpak-builder --user --install`. Layer-shell
  preload now also looks in `/app/lib` for the Flatpak sandbox.

### Known limitations

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md). Headline items:

- Global hotkey is delegated to the DE's keyboard settings; no portal
  registration yet.
- Multi-monitor: opens on the first reported monitor; cursor-following
  not generally possible on Wayland.
- GNOME / Mutter Wayland: pane is centered, not top-anchored
  (workaround: use a layer-shell compositor).
- Prefs are JSON; GSettings deferred to M7 packaging.
- Distribution (Flatpak, AUR) deferred to M7.

### Verified on

- KDE Plasma 6 / Wayland with `gtk4-layer-shell` 1.3.0.
- Headless: CI under xvfb (Ubuntu 24.04, Python 3.12).

[0.1.0]: https://github.com/nfantunes/DevPane/releases/tag/v0.1.0
