# DevPane — Implementation Plan

## Context

DevPane is a Linux-native quick-access notetaking app for developers, modeled on
Guake's drop-down ergonomics: bind a key, the pane slides down from the top
edge, you type, bind again, it hides and persists. The repo is currently empty
(README + `.git` only), so this plan is the global blueprint for v1.

**Goals confirmed with user**
- Target **all major DEs from day 1**: GNOME/Wayland, Sway/Hyprland/KDE/Wayland,
  and any X11 session.
- **v1 scope: notes only** — markdown scratchpad. Structured TODOs deferred.
- Distribute via **Flatpak (Flathub) and AUR/source** from the first release.

**Stack** (justified in the prior conversation turn): GTK4 + Python (PyGObject)
+ libadwaita + GtkSourceView + `gtk4-layer-shell` (where supported) + SQLite
index over plain markdown files.

---

## Architecture

Two-process model:

```
 ┌─────────────────────┐         ┌──────────────────────────┐
 │ devpane-toggle      │ ──UDS──▶│ devpaned (daemon)        │
 │ (tiny CLI, ~no deps)│         │  ├─ IPC server           │
 └─────────────────────┘         │  ├─ Hidden GTK4 window   │
        ▲                       │  │  (drop-down pane)     │
        │ bound to F12 in DE    │  ├─ GtkSourceView editor  │
        │                       │  ├─ Notes store (FS+SQLite)│
        │                       │  └─ D-Bus service (opt.)  │
        │                       └──────────────────────────┘
 user's keyboard shortcut                    │
                                             ▼
                            ~/.local/share/devpane/notes/*.md
                            ~/.local/share/devpane/index.sqlite
```

**Why two processes**
- Daemon stays resident so toggling is instant (no Python cold start).
- CLI is trivial and lets the user bind it through their DE's native keyboard
  settings — which sidesteps the Wayland global-hotkey problem entirely and
  works identically on every compositor.

**Window strategy per session type** (auto-detected at runtime)
- **Wayland + layer-shell available** (Sway, Hyprland, KDE Plasma 6,
  wlroots-based): use `gtk4-layer-shell` anchored to top edge, `TOP` layer,
  exclusive keyboard, animated slide.
- **Wayland without layer-shell** (GNOME/Mutter): regular `Adw.Window`
  positioned at top via compositor hints; accept slightly less polish.
- **X11**: override-redirect window with `_NET_WM_WINDOW_TYPE_DOCK` + strut,
  `XGrabKeyboard` for focus-stealing.

**Persistence**
- Each note is a plain `.md` file in `~/.local/share/devpane/notes/`.
  Files-first → users can `grep`, sync (git/Syncthing), open in their editor.
- `index.sqlite` holds FTS5 full-text index, recency, pinned flag. Rebuildable
  from filesystem.
- Default note: `scratch.md` — opens on every toggle unless another note is
  pinned. Autosave on hide and every 2s while editing.

**IPC**
- Unix domain socket at `$XDG_RUNTIME_DIR/devpane.sock`.
- Line-delimited JSON: `{"cmd":"toggle"}`, `{"cmd":"show"}`, `{"cmd":"hide"}`,
  `{"cmd":"new-note"}`, `{"cmd":"status"}`.
- Optional D-Bus name `com.devpane.Daemon` exposing the same surface, for
  scripting and AppIndicator integrations.

---

## Repository Layout

```
DevPane/
├── README.md
├── LICENSE                         # GPL-3.0 (matches GNOME ecosystem)
├── pyproject.toml                  # Hatchling, declares both entry points
├── .gitignore
├── .editorconfig
├── ruff.toml                       # lint + format
├── mypy.ini
│
├── src/
│   └── devpane/
│       ├── __init__.py
│       ├── __main__.py             # `python -m devpane` → daemon
│       ├── version.py
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   └── toggle.py           # entry: devpane-toggle
│       │
│       ├── daemon/
│       │   ├── __init__.py
│       │   ├── app.py              # Adw.Application subclass, lifecycle
│       │   ├── ipc.py              # UDS server (asyncio)
│       │   ├── dbus.py             # optional D-Bus surface
│       │   └── single_instance.py  # lockfile + socket check
│       │
│       ├── ui/
│       │   ├── __init__.py
│       │   ├── window.py           # DropDownWindow (mode-aware)
│       │   ├── editor.py           # GtkSourceView wrapper, md syntax
│       │   ├── header.py           # title bar / note switcher
│       │   ├── animations.py       # slide-in/out helpers
│       │   └── styles.css          # libadwaita theming overrides
│       │
│       ├── platform/
│       │   ├── __init__.py
│       │   ├── detect.py           # X11 vs Wayland, compositor probe
│       │   ├── wayland_layer.py    # gtk4-layer-shell binding wrapper
│       │   ├── wayland_plain.py    # GNOME-style fallback positioning
│       │   └── x11.py              # override-redirect + strut + grab
│       │
│       ├── store/
│       │   ├── __init__.py
│       │   ├── paths.py            # XDG dir resolution
│       │   ├── notes.py            # FS read/write, atomic save
│       │   ├── index.py            # SQLite + FTS5
│       │   └── migrations/
│       │       └── 0001_init.sql
│       │
│       └── util/
│           ├── __init__.py
│           ├── logging.py
│           └── debounce.py
│
├── data/
│   ├── com.devpane.Daemon.desktop          # autostart
│   ├── com.devpane.Daemon.service          # D-Bus service file
│   ├── com.devpane.Daemon.metainfo.xml     # AppStream for Flathub
│   ├── icons/
│   │   └── hicolor/scalable/apps/com.devpane.Daemon.svg
│   └── gschemas/
│       └── com.devpane.Daemon.gschema.xml  # GSettings: hotkey hint, theme
│
├── packaging/
│   ├── flatpak/
│   │   └── com.devpane.Daemon.yml
│   ├── arch/
│   │   └── PKGBUILD
│   └── systemd/
│       └── devpane.service                 # user unit
│
├── tests/
│   ├── conftest.py
│   ├── test_ipc.py
│   ├── test_notes_store.py
│   ├── test_index_fts.py
│   ├── test_platform_detect.py
│   └── ui/
│       └── test_window_smoke.py            # gtk headless via Xvfb
│
├── scripts/
│   ├── dev-run.sh                          # run daemon from source
│   └── reset-state.sh                      # wipe ~/.local/share/devpane
│
└── docs/
    ├── ARCHITECTURE.md
    ├── HOTKEY-SETUP.md                     # per-DE binding instructions
    └── CONTRIBUTING.md
```

**Modularity rules**
- `ui/` knows nothing about IPC or storage; takes callbacks in its constructor.
- `platform/` is the only place that imports compositor-specific libs; the rest
  of the code talks to a `WindowMode` enum and a `PlatformAdapter` protocol.
- `store/` is filesystem-of-record; `index/` is a derived cache and can be
  rebuilt from disk at any time.
- `daemon/app.py` is the only file that wires everything together.

---

## Dependencies

Runtime:
- `PyGObject >= 3.50`
- GTK 4 ≥ 4.14, libadwaita ≥ 1.5, GtkSourceView 5
- `gtk4-layer-shell` (system lib + gi bindings) — optional, gracefully skipped
- `python-xlib` — X11 path only, lazy-imported
- Python 3.11+

Dev:
- `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `xvfb-run` (CI)

---

## Implementation Milestones

Each milestone ends with a concrete validation step. Don't proceed until the
validation passes.

### M0 — Project skeleton (½ day)
1. Create `pyproject.toml` with two entry points: `devpaned` → `devpane.daemon.app:main`,
   `devpane-toggle` → `devpane.cli.toggle:main`.
2. Add `ruff.toml`, `mypy.ini`, `.editorconfig`, `LICENSE` (GPL-3.0).
3. Stub package tree per layout above with empty `__init__.py` files.
4. Add `scripts/dev-run.sh` that runs `python -m devpane` with `G_MESSAGES_DEBUG=devpane`.
5. CI workflow: `ruff check`, `mypy src`, `pytest` under `xvfb-run`.

**Validate**: `pipx install -e .` succeeds; `devpaned --version` and
`devpane-toggle --help` both print.

### M1 — Storage layer (1 day)
1. `store/paths.py`: resolve `$XDG_DATA_HOME/devpane/{notes,index.sqlite}`.
2. `store/notes.py`: `list_notes()`, `read(name)`, `write_atomic(name, body)`
   using `os.replace`. Default note `scratch.md` auto-created.
3. `store/index.py`: SQLite with FTS5 virtual table; `reindex_all()`, `search(q)`,
   `touch(name)`. Run migrations from `migrations/0001_init.sql`.
4. Debounced writer in `util/debounce.py` (2s).

**Validate**: `pytest tests/test_notes_store.py tests/test_index_fts.py` — covers
round-trip write/read, atomic crash-safety, FTS search hits.

### M2 — IPC + single-instance daemon (1 day)
1. `daemon/single_instance.py`: lockfile + try to connect to existing socket; if
   alive, send `{"cmd":"toggle"}` and exit 0 (so running `devpaned` twice acts
   as a toggle).
2. `daemon/ipc.py`: asyncio UDS server, JSON line protocol, dispatch table.
3. `cli/toggle.py`: 30-line script — connect to socket, send command, exit. If
   socket missing, spawn `devpaned` detached.
4. Wire `Adw.Application` with no window yet; just log commands received.

**Validate**: in two terminals, run `devpaned` and `devpane-toggle` — daemon
logs each toggle. `devpane-toggle` works even when daemon isn't running yet
(spawns it).

### M3 — Platform detection + minimal window (1.5 days)
1. `platform/detect.py`: `XDG_SESSION_TYPE`, env probe for `WAYLAND_DISPLAY`,
   compositor sniff (`HYPRLAND_INSTANCE_SIGNATURE`, `SWAYSOCK`,
   `KDE_FULL_SESSION`, `GNOME_SHELL_SESSION_MODE`).
2. Probe `gtk4-layer-shell` availability via `gi.require_version` in try/except.
3. `ui/window.py` `DropDownWindow`: plain `Adw.Window` first, top-anchored,
   60% screen height, full screen width. `show()` / `hide()` methods.
4. `daemon/app.py`: on `toggle`, flip visibility.

**Validate**: on each session you have access to (X11, GNOME-Wayland,
Sway/Hyprland or KDE-Wayland), `devpane-toggle` pops a blank window from the
top and hides it on second press. Log line reports detected platform.

### M4 — Platform adapters (2 days)
1. `platform/wayland_layer.py`: wrap `gtk4-layer-shell`, set `LAYER_TOP`,
   anchor TOP/LEFT/RIGHT, exclusive zone 0, keyboard interactivity
   `ON_DEMAND`.
2. `platform/wayland_plain.py`: GNOME fallback — top-anchored regular window,
   `set_decorated(False)`, `Gtk.Window.present()`, accept normal stacking.
3. `platform/x11.py`: via `Gdk.Surface` + `python-xlib`, set override-redirect,
   `_NET_WM_WINDOW_TYPE_DOCK`, grab keyboard on show, ungrab on hide.
4. `DropDownWindow` selects adapter via `PlatformAdapter` protocol at init.

**Validate**: manual matrix in `docs/HOTKEY-SETUP.md` checked off — true
drop-down on Sway/Hyprland/KDE, acceptable behavior on GNOME, dock-style on
X11.

### M5 — Editor UX (1.5 days)
1. `ui/editor.py`: `GtkSourceView` with markdown language, `monospace` font,
   line wrap, no line numbers by default.
2. `ui/header.py`: title bar showing current note name, `Ctrl+N` new note,
   `Ctrl+K` switcher (popover listing notes from store).
3. `ui/styles.css`: subtle backdrop blur, rounded bottom corners, libadwaita
   accent.
4. Autosave hookup: `buffer.connect("changed", debounced_save)`; also save on
   `hide()`.
5. `Esc` hides the window.

**Validate**: open pane, type a list, hit Esc, reopen — content is there.
File on disk matches.

### M6 — Polish + animations (1 day)
1. Slide-in animation via `Adw.TimedAnimation` translating Y from `-height` to
   `0` over 150ms ease-out; reverse on hide.
2. Focus the editor on show; restore cursor position per-note.
3. Multi-monitor: open on monitor under cursor (`Gdk.Display.get_monitor_at_surface`).
4. GSettings schema: persist last-open note, window height ratio.

**Validate**: feel test — drop-down is snappy, cursor lands in editor, multi-
monitor works.

### M7 — Distribution (1.5 days)
1. `data/com.devpane.Daemon.desktop` with `X-GNOME-Autostart-enabled=true`;
   install under `~/.config/autostart` via packaging.
2. `packaging/systemd/devpane.service` user unit (alt to autostart).
3. `packaging/arch/PKGBUILD` building from a tagged release tarball.
4. `packaging/flatpak/com.devpane.Daemon.yml`: GNOME runtime 46+, build
   PyGObject deps, include `gtk4-layer-shell` from extension or bundle.
5. `docs/HOTKEY-SETUP.md`: per-DE step-by-step for binding F12 →
   `devpane-toggle`.

**Validate**:
- `makepkg -si` in a clean Arch chroot installs and runs.
- `flatpak-builder --user --install build packaging/flatpak/com.devpane.Daemon.yml`
  produces a working sandboxed install.
- Bind F12 in GNOME Settings → Keyboard, in KDE System Settings, in Sway
  config — each toggles the pane.

### M8 — Hardening (1 day, optional pre-release)
1. Crash recovery: on daemon start, if `scratch.md.tmp` exists, restore.
2. Migration runner ready for future schema bumps.
3. Logging to `$XDG_STATE_HOME/devpane/log` with rotation.
4. README + `docs/ARCHITECTURE.md` finalized.
5. Tag `v0.1.0`, push to AUR, submit to Flathub.

**Validate**: kill -9 the daemon mid-edit, restart, content recovered.
`devpaned --check` returns 0.

---

## End-to-End Verification

Run after M7 on each supported session:

1. **Cold start**: `systemctl --user start devpane` → daemon up, no window.
2. **Toggle**: press bound key → pane drops from top within 200ms.
3. **Edit + hide**: type markdown including `# heading` and `- [ ] todo`, press
   key again → pane slides up, file flushed to disk.
4. **Reopen**: press key → content restored, cursor at last position.
5. **External edit**: `echo "external" >> ~/.local/share/devpane/notes/scratch.md`
   while pane is hidden → next open shows the appended line (file is source of
   truth).
6. **Crash resilience**: `kill -9 $(pgrep devpaned)` mid-edit → restart →
   content from last 2s autosave is present.
7. **Multi-monitor**: move cursor to second monitor → toggle → pane opens on
   that monitor.
8. **Search** (CLI smoke): `devpane-toggle status` reports notes count matching
   `find ~/.local/share/devpane/notes -name '*.md' | wc -l`.

---

## Critical Files (modify/create order matches milestones)

- [pyproject.toml](pyproject.toml) — M0
- [src/devpane/store/notes.py](src/devpane/store/notes.py) — M1
- [src/devpane/store/index.py](src/devpane/store/index.py) — M1
- [src/devpane/daemon/ipc.py](src/devpane/daemon/ipc.py) — M2
- [src/devpane/cli/toggle.py](src/devpane/cli/toggle.py) — M2
- [src/devpane/daemon/app.py](src/devpane/daemon/app.py) — M2/M3
- [src/devpane/platform/detect.py](src/devpane/platform/detect.py) — M3
- [src/devpane/ui/window.py](src/devpane/ui/window.py) — M3/M4
- [src/devpane/platform/wayland_layer.py](src/devpane/platform/wayland_layer.py) — M4
- [src/devpane/platform/x11.py](src/devpane/platform/x11.py) — M4
- [src/devpane/ui/editor.py](src/devpane/ui/editor.py) — M5
- [packaging/flatpak/com.devpane.Daemon.yml](packaging/flatpak/com.devpane.Daemon.yml) — M7
- [packaging/arch/PKGBUILD](packaging/arch/PKGBUILD) — M7
- [docs/HOTKEY-SETUP.md](docs/HOTKEY-SETUP.md) — M7

---

## Out of Scope for v1 (tracked for v2)

- Structured TODOs with due dates / priorities (v1 uses `- [ ]` checkboxes
  rendered by the markdown view, no separate model).
- Encryption at rest.
- Cloud sync (users can `git init` the notes dir today).
- Plugin system.
- Wayland portal-based global hotkey registration (delegating to DE shortcut
  settings is sufficient and more reliable for v1).
