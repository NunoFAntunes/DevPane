# Changelog

All notable changes to DevPane are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
uses [Semantic Versioning](https://semver.org/).

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
