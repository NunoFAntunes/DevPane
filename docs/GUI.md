# DevPane — GUI

The drop-down pane is built with **GTK 4 + libadwaita** via PyGObject. M3
delivers the minimum viable pane: a window that appears and disappears on
command. True top-edge anchoring (layer-shell on wlroots/KDE, dock-style on
X11) lands in M4; the markdown editor lands in M5.

## Threading model

GTK is strictly single-threaded — all widget calls must run on the GLib main
thread. DevPane's IPC server runs on asyncio. We bridge them like this:

```
┌─────────────────── main thread ───────────────────┐  ┌──── worker thread ────┐
│ Adw.Application.run()                              │  │ asyncio event loop    │
│   └─ GLib main loop                                │  │   ├─ IPCServer        │
│       └─ idle_add callbacks ◀──── GLib.idle_add ───┤◀─┤   └─ command handlers │
│             (mutate DropDownWindow)                │  │       └─ await future │
│             call_soon_threadsafe ───────────────── ┼──┤────▶ resolve future   │
└────────────────────────────────────────────────────┘  └───────────────────────┘
```

Implementation in [`ui/gtk_app.py`](../src/devpane/ui/gtk_app.py):

1. `Adw.Application.run()` runs on the main thread.
2. On `activate`, it spawns a daemon thread (`devpane-asyncio`) that creates
   its own `asyncio` event loop and runs the IPC server in it.
3. `GtkController` (in [`ui/window.py`](../src/devpane/ui/window.py)) is the
   bridge: every async method posts the real work to the GLib main thread
   via `GLib.idle_add` and awaits a `Future` resolved with
   `loop.call_soon_threadsafe`.
4. On shutdown, the asyncio loop signals completion, the thread schedules
   `app.quit()` on the main thread via `GLib.idle_add`. `on_shutdown`
   joins the thread so the process exits clean.

This pattern is robust under both directions of shutdown:

- **`quit` over IPC** → asyncio's stop event fires → handler returns → loop
  closes → `GLib.idle_add(app.quit)` → main loop exits → `on_shutdown`
  notices the loop is already closed and skips re-signalling it → join.
- **SIGINT / `app.quit()` from main thread** → `on_shutdown` runs while the
  asyncio loop is still live → signals the stop event → join → done.

## Mode selection (gtk vs headless)

The daemon supports a `--headless` mode that drops GTK entirely and uses an
in-memory `HeadlessController`. This is what the test suite and CI use, and
is also what the daemon auto-selects when no display is detected.

| CLI flag / env | Effective mode |
|----------------|----------------|
| `--gtk` | GTK (errors if unavailable) |
| `--headless` | Headless |
| `DEVPANE_HEADLESS=1` | Headless |
| neither, and `WAYLAND_DISPLAY` or `DISPLAY` set | GTK |
| neither, and no display | Headless |

Resolution lives in `daemon.app._resolve_mode`.

## Platform detection

[`platform/detect.py`](../src/devpane/platform/detect.py) is environment-only
(no subprocesses, no D-Bus). It returns a `PlatformInfo` with:

- `session` — `wayland` / `x11` / `none`
- `compositor` — `hyprland` / `sway` / `kde` / `gnome` / `wlroots` / `unknown`
- `has_layer_shell` — whether `gtk4-layer-shell` can be imported via gi

`devpaned --check` prints all three. M4 uses these to pick the right window
adapter.

## Window strategy

Implemented via `PlatformAdapter` (`platform/adapter.py`). One adapter per
session type:

| Session | Adapter | Behavior |
|---------|---------|----------|
| Wayland + `gtk4-layer-shell` available (Sway, Hyprland, KDE Plasma 6) | `wayland-layer-shell` | True top-anchored layer surface. `LAYER_TOP`, anchored to top/left/right edges, `exclusive_zone=0` (overlay, no reserved space), `ON_DEMAND` keyboard mode. |
| Wayland without `gtk4-layer-shell` (typically GNOME/Mutter) | `wayland-plain` | Plain borderless toplevel. The compositor decides placement. |
| X11 | `x11` | Plain toplevel with `_NET_WM_WINDOW_TYPE_DOCK`, `_NET_WM_STATE_ABOVE`, `SKIP_TASKBAR`, `SKIP_PAGER` hints set via `python-xlib`. |
| No display | `noop` | No-op. |

The window is always decoration-less (`set_decorated(False)`), full screen
width, 60% of monitor height.

## Editor (M5)

The pane body is a `GtkSourceView` with markdown highlighting, monospace
font, word wrap, no line numbers. Implemented in
[`ui/editor.py`](../src/devpane/ui/editor.py).

**Autosave.** Every change to the buffer schedules a save 2 seconds later
via [`ui/autosave.py`](../src/devpane/ui/autosave.py) (a GLib-main-thread
debouncer — distinct from the threading-based one in `util/debounce.py`
because the save touches the buffer and the SQLite connection, both
main-thread-only). `hide_pane()` always flushes the pending save, so no
keystroke is ever lost when the pane disappears.

**Source of truth on show.** Every `show_pane()` re-reads the current
note from disk before presenting. This means external edits (your editor,
`git pull`, Syncthing) are picked up the next time the pane opens.
Last-writer-wins if you edit in two places at the same time; collision
detection is out of scope for v1.

**Style scheme.** Tracks `Adw.StyleManager`'s `notify::dark` so the editor
follows the system light/dark setting automatically.

## Header + note switching

The pane's header bar (composition-wraps `Adw.HeaderBar` because that
class is `final` in libadwaita) shows the current note name as a subtitle
under "DevPane". Two controls:

| Control | Shortcut | Action |
|---------|----------|--------|
| 📄 new-note button | `Ctrl+N` | Create `note-YYYYMMDD-HHMM.md` (auto-suffixed on collisions) and switch to it. |
| ☰ switcher button | `Ctrl+K` | Popover lists every `.md` in the notes dir, ordered by filename. Click to switch. |
| (Escape key) | `Escape` | Hide the pane (flushing autosave first). |

Switching notes always flushes the previous note's autosave before
loading the new one.

## Index integration

A SQLite connection (`store.index`) is opened on the main thread during
`Adw.Application.activate` and handed to the editor. Every save calls
`index.touch()` so the FTS5 search index and recency ordering stay in
sync with the filesystem. The connection is closed in `on_shutdown`.

## Polish (M6)

**Slide-down on show.** When the pane is presented, the window's height
animates from 1px to its target via `Adw.TimedAnimation` over 180ms with
an ease-out-cubic curve. With layer-shell anchored to the top edge the
height growth reads as a drawer sliding down. The animation is disabled
when `prefs.animate` is false.

**Per-note cursor position.** Each save stamps the buffer's cursor
offset into the SQLite `notes.cursor_offset` column (migration
`0002_cursor.sql`). On load, the cursor is restored — clamped to the
current buffer length in case the file was truncated externally. The
position survives hide/show *and* daemon restart.

**Last-open note.** `hide_pane()` persists the currently-loaded note name
into `$XDG_CONFIG_HOME/devpane/prefs.json`. On next startup the daemon
opens that note if it still exists, falling back to `scratch.md`
otherwise. Implementation: [`ui/prefs.py`](../src/devpane/ui/prefs.py).

**Height ratio is also persisted** (default 0.6 of monitor height, clamped
to 0.2–0.95). A future milestone can wire a resize handle to mutate it.

**Multi-monitor.** M6 picks the first reported monitor. Following the
cursor across monitors is not generally possible on Wayland without
compositor-specific extensions; users on multi-monitor setups can
configure their compositor to place DevPane on a specific output.

### Layer-shell linker requirement

`gtk4-layer-shell` must be **linked before** `libwayland-client`. Python
imports alone cannot guarantee this, so the daemon's `_run_gtk` path
calls `platform.layer_shell_preload.ensure_preloaded()` before any GTK
import. If the library is present and `LD_PRELOAD` doesn't already cover
it, the daemon **re-execs itself** with the right environment.

Opt out (e.g. to debug the plain-Wayland adapter on a layer-shell
system): set `DEVPANE_SKIP_LAYER_SHELL_PRELOAD=1`.

Reference: <https://github.com/wmww/gtk4-layer-shell/blob/main/linking.md>.

## Trying it locally

```sh
# Optional — keep your real notes dir untouched
export XDG_DATA_HOME=/tmp/devpane-dev
mkdir -p $XDG_DATA_HOME

# Start the daemon in the background
PYTHONPATH=src /usr/bin/python3 -m devpane --gtk --log-level INFO &

# Drive it
PYTHONPATH=src /usr/bin/python3 -m devpane.cli.toggle toggle   # show
PYTHONPATH=src /usr/bin/python3 -m devpane.cli.toggle toggle   # hide
PYTHONPATH=src /usr/bin/python3 -m devpane.cli.toggle status

# Stop
PYTHONPATH=src /usr/bin/python3 -m devpane.cli.toggle quit
```

Use `/usr/bin/python3` (or any Python that can see your distro's PyGObject)
rather than a pyenv-managed interpreter — PyGObject needs the system GI
bindings.
