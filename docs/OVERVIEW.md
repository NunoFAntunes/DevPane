# DevPane — Project Overview

DevPane is a Linux-native drop-down notetaking app for developers. Press a
key, the pane slides down from the top of the screen; press it again, the pane
hides and your notes are persisted to disk as plain markdown. It is modeled on
[Guake](http://guake-project.org/)'s ergonomics — but for notes instead of a
terminal — and built on a modern GTK4 + libadwaita stack.

## Why it exists

Developers constantly need to capture small fragments — a command they just
figured out, a TODO they don't want to lose, a snippet from a code review, a
thought they need to come back to. The friction of opening an editor,
choosing a file name, and saving is high enough that those fragments end up in
chat scratch buffers or get lost. DevPane removes that friction: one
keystroke, always in the same place, always saved.

## Design goals

1. **Instant access.** A single hotkey opens and closes the pane. The daemon
   stays resident so toggling has no perceptible latency.
2. **Native Linux feel.** GTK4 + libadwaita on GNOME, layer-shell on
   wlroots/KDE, dock-style on X11 — whichever the user's session supports.
3. **Files first.** Notes are plain `.md` files under
   `~/.local/share/devpane/notes/`. Users can `grep`, version with `git`, sync
   with Syncthing, or open them in any editor.
4. **Works on every major DE from day one.** GNOME (Wayland), Sway, Hyprland,
   KDE Plasma, and X11 sessions are all supported.
5. **No background magic.** The user binds `devpane-toggle` to a key in their
   own DE's keyboard settings. No portal dances, no compositor-specific
   hotkey daemons.

## How it's built

Two processes:

- **`devpaned`** — a small Python daemon (PyGObject / GTK4 / libadwaita /
  GtkSourceView) that owns the hidden window, an IPC socket, and the notes
  store. Stays resident across toggles.
- **`devpane-toggle`** — a tiny CLI that sends a command over a Unix socket
  to the daemon. Bind this to a key in your DE.

Notes are stored as plain markdown files; a SQLite + FTS5 index alongside
them provides search and recency. The index is rebuildable from disk at any
time, so the filesystem is always source of truth.

A platform-detection layer picks the right window strategy at startup:
`gtk4-layer-shell` where the compositor supports it, a top-anchored toplevel
on GNOME, override-redirect on X11.

For the full architecture, milestones, and verification steps, see
[PLAN.md](PLAN.md). For per-DE hotkey binding, see
[HOTKEY-SETUP.md](HOTKEY-SETUP.md).

## Project status

Pre-alpha. Implementation follows the milestones in [PLAN.md](PLAN.md).

| Milestone | Status |
|-----------|--------|
| M0 — Project skeleton | ✅ done |
| M1 — Storage layer (notes, index, debounce) | ✅ done |
| M2 — IPC + single-instance daemon | ✅ done |
| M3 — Platform detection + minimal window | ✅ done |
| M4 — Platform adapters (layer-shell, X11) | ⏳ next |
| M5 — Editor UX | ⏳ |
| M6 — Polish + animations | ⏳ |
| M7 — Distribution (Flatpak, AUR) | ⏳ |
| M8 — Hardening + release | ⏳ |

For the storage layer's on-disk format and inspection commands, see
[STORAGE.md](STORAGE.md). For the IPC protocol the CLI speaks to the daemon,
see [IPC.md](IPC.md). For the GTK window and asyncio↔GLib bridge, see
[GUI.md](GUI.md).

## Repository map

| Path | Contents |
|------|----------|
| `src/devpane/` | Python package — daemon, CLI, UI, platform adapters, storage |
| `data/` | Desktop integration files (`.desktop`, D-Bus service, GSettings schema, icons) |
| `packaging/` | Flatpak, Arch PKGBUILD, systemd user unit |
| `tests/` | Pytest suite (unit + headless GTK smoke) |
| `scripts/` | `dev-run.sh`, `reset-state.sh` |
| `docs/` | This file, plan, architecture, storage, hotkey setup, contributing |

## License

GPL-3.0-or-later. See [LICENSE](../LICENSE).
