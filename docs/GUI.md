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

## Window strategy (current vs planned)

| | M3 (now) | M4 (next) |
|---|---|---|
| Sway / Hyprland / KDE Plasma 6 | Plain Adw.Window, compositor decides position | gtk4-layer-shell, anchored TOP |
| GNOME (Wayland) | Plain Adw.Window | Top-anchored toplevel |
| X11 (any WM) | Plain Adw.Window | Override-redirect + `_NET_WM_WINDOW_TYPE_DOCK` + keyboard grab |

The current M3 window is decoration-less (`set_decorated(False)`), full
screen width, 60% of monitor height, with a minimal placeholder body and a
header bar.

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
