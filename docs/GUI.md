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

## Task list + layout

The pane uses an `Adw.OverlaySplitView` for the sidebar, and a
`Gtk.Paned` (`HORIZONTAL`) inside the content area to split the
**subtask panel** from the markdown editor:

- **Left sidebar** — a sprint bar above a task list:
  - [`ui/sprint_bar.py`](../src/devpane/ui/sprint_bar.py) — previous /
    next arrow buttons flanking the current sprint's display name.
    A dim subtitle under the name shows non-zero status counts
    (`3 doing · 5 todo · 2 blocked`); `done` is omitted because the
    show-completed switch already addresses it. Clicking the name
    opens a rename dialog.
  - [`ui/task_list.py`](../src/devpane/ui/task_list.py) — one row per
    `.md` file belonging to the current sprint. Each row has a
    **status pill** ([`ui/status_pill.py`](../src/devpane/ui/status_pill.py))
    showing one of `todo` / `doing` / `blocked` / `done` (click to
    open a four-button popover and pick another), the task title
    (`meta['title']` from frontmatter, falling back to the filename
    stem), and up to three **tag chips** with a `+N` overflow chip.
    Rows are sorted `doing → todo → blocked → done`, then by mtime
    descending. Selecting a row opens that file in the editor.
  - **Header `+`** is a toggle button. Pressing it reveals an inline
    `Gtk.Revealer` form between header and list with name + tags
    (comma-separated) entries and Cancel / Add buttons; Enter in
    either field submits, Escape closes (capture-phase so the pane
    stays open). `Ctrl+N` toggles the same form.
  - **Footer** has a tag-filter `Gtk.DropDown` (populated from the
    union of tags across the current sprint, plus a leading "All
    tags" entry) and a compact, neutral `Gtk.Switch` (`.muted-switch`
    CSS class) for show-completed.
- **Right pane** — slim header with a sidebar-toggle button and the
  current task's title, then a horizontal `Gtk.Paned`:
  - **Middle: subtask panel** ([`ui/subtask_panel.py`](../src/devpane/ui/subtask_panel.py))
    — owned by the currently selected task. One row per subtask, with a
    checkbox, a click-to-edit `GtkEditableLabel` for the text, and a
    hover-visible 🗑 delete button. Rows are draggable for reordering
    (the drop indicator is a 2px accent-color underline / overline on
    the target row). A permanently-visible **phantom row** at the
    bottom of the list ("Add subtask…") is the entry point for new
    subtasks — click it (or any empty area below the rows) to start
    editing; press Enter with non-empty text to promote it to a real
    subtask, at which point focus jumps to a fresh phantom below for
    chained entry. Empty commits are discarded. The whole list is
    persisted to a JSON sidecar at
    `$XDG_DATA_HOME/devpane/subtasks/<task-stem>.json` on every
    mutation. Existing rows still follow the same rule: empty-string
    commit removes the row.
  - **Right: editor** — the existing `GtkSourceView`. Notes belong to
    the parent task only; subtasks don't have their own notes.

The paned position is persisted in `Prefs.subtask_panel_width` and
clamped to `[120, 600]` on load.

| Control | Shortcut | Action |
|---------|----------|--------|
| ＋ new-task toggle | `Ctrl+N` | Reveal the inline new-task form under the sidebar header. Enter in either field creates `note-YYYYMMDD-HHMM.md` (auto-suffixed on collisions) with `status: todo`, the typed `title` (omitted if blank), the typed `tags` (omitted if blank), and the current sprint stamped into frontmatter, then selects it and collapses the form. Escape closes the form without creating. If no sprint exists yet, a new one is minted with the current timestamp. |
| Sidebar toggle | `Ctrl+B` | Show/hide the task list. Visibility is persisted in prefs. |
| Previous / next sprint | `Alt+Left` / `Alt+Right` | Navigate to the adjacent sprint. Disabled at the chronological ends — sprints exist only when at least one task references them. Shortcuts are installed in capture phase so the editor's word-jump bindings don't swallow them. |
| Status pill (on each row) | — | Click to open a popover and pick `todo` / `doing` / `blocked` / `done`. Updates the frontmatter, re-sorts the list, refreshes the sprint-bar counts, and applies strikethrough on `done`. |
| Tag-filter dropdown | — | Footer dropdown listing the union of tags across the current sprint plus "All tags". Filters the visible rows; persisted across sessions in `Prefs.tag_filter`. |
| Show-completed switch | — | Compact neutral switch (no accent colour). Hide done tasks (default) or list them at the bottom, dimmed and struck through. |
| Row right-click | — | Context menu: **Rename** (frontmatter title only — the file is not renamed), **Move to next sprint** / **Move to previous sprint** (creates a new sprint dated now if migrating past the last existing one; "previous" is disabled at sprint 1), and **Delete** (`Adw.AlertDialog` confirmation; falls back to another task in the same sprint, then to an adjacent sprint, then to `scratch.md`. The task's subtask sidecar is removed in the same step). |
| Task row progress | — | Tasks with subtasks show a dim `n/m` suffix next to the title (completed/total). Refreshed automatically whenever any subtask is mutated. |
| (Escape key) | `Escape` | Hide the pane (flushing autosave first). Inside the new-task form, Escape closes the form instead. |

Switching tasks always flushes the previous task's autosave before
loading the new one. Picking a new status from a row's pill writes
`status: <value>` into the task's frontmatter (dropping any legacy
`done:` key in the process) and re-sorts the list
(`doing → todo → blocked → done`, then by mtime desc).

### Sprint lifecycle

Sprints are **emergent**: a sprint exists when at least one task's
frontmatter carries its id (an ISO timestamp). The sidebar's sprint list
is recomputed by scanning frontmatter every `show_pane` and every
mutation. There is no separate "sprints database" — only an optional
rename registry at `$XDG_DATA_HOME/devpane/sprints.json` mapping
`{sprint_id: display_name}`. Default display name = the date portion of
the id (`YYYY-MM-DD`).

On daemon startup, [`store/sprints.py`](../src/devpane/store/sprints.py)
runs `bootstrap_existing()`: if any tasks lack a `sprint:` field
(pre-existing notes or external file drops), they're all assigned to a
single sprint id — the most recent existing one, or a freshly-minted one
if no sprint exists at all. This keeps the rule "tasks are always in
exactly one sprint" without forcing the user to think about migration
on upgrade.

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

**Last-open note + sprint.** `hide_pane()` persists the currently-loaded
note name, the currently-viewed sprint id, the sidebar visibility, the
show-completed switch state, the active tag filter, and the subtask
paned position into `$XDG_CONFIG_HOME/devpane/prefs.json`. On next startup the daemon picks
the last-viewed sprint (if it still has any tasks); otherwise it falls
back to the newest existing sprint. The last note is loaded only if it
still exists *and* belongs to the chosen sprint; otherwise the first
visible task in that sprint is loaded, and as a final resort
`scratch.md` is created and selected. Implementation:
[`ui/prefs.py`](../src/devpane/ui/prefs.py) and
[`ui/window.py`](../src/devpane/ui/window.py) (`_choose_initial_sprint`
and the startup block in `__init__`).

**Height ratio is also persisted** (default 0.6 of monitor height, clamped
to 0.2–0.95). A future milestone can wire a resize handle to mutate it.

**Subtask panel width** is persisted as `subtask_panel_width` (default
240px, clamped 120–600). The Gtk.Paned separator between the subtask
panel and the editor is dragged by the user; the value is read off
`Paned.get_position()` on `hide_pane()`.

### Multi-monitor

M6 picks the first reported monitor. Following the
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
