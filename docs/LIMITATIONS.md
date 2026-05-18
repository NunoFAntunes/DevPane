# DevPane — Known Limitations

A single source of truth for what DevPane *doesn't* do yet, why, and what
the workaround is. Each item links to the milestone where it was scoped
out and, where applicable, the milestone that might address it.

## Display + windowing

### Drop-down position on GNOME / Mutter (Wayland)

**What.** On GNOME and other Wayland compositors without
`gtk4-layer-shell`, DevPane cannot anchor the pane to the top edge — the
compositor decides placement, and most center the window.

**Why.** Wayland does not let regular toplevels position themselves.
`gtk4-layer-shell` is the standard escape hatch, but Mutter does not
implement the protocol. GNOME extensions exist but are not safe to
depend on.

**Workaround.** Install `gtk4-layer-shell` on Sway / Hyprland / KDE
Plasma 6 and DevPane will pick the layer-shell adapter automatically.
On GNOME, accept the centered window.

**Scoped:** M4. **Could be revisited if:** Mutter adds layer-shell or
the freedesktop layer-shell becomes standard.

### Multi-monitor: cursor-following

**What.** DevPane always opens on the first reported monitor. It does
not follow the cursor or the focused window across outputs.

**Why.** Wayland does not expose the global cursor position to
unprivileged clients, and GTK 4 mirrors that limitation. The compositor
owns this.

**Workaround.** Configure your compositor to place DevPane on a
specific output. On Sway: `for_window [app_id="io.github.nfantunes.DevPane"]
move container to output <name>`. On Hyprland: `windowrule = monitor
<name>, ^(io.github.nfantunes.DevPane)$`.

**Scoped:** M6. **Could be revisited if:** the
`org.freedesktop.portal.GlobalShortcuts` portal gains output-targeting
APIs.

### Layer-shell linker order

**What.** `gtk4-layer-shell` must be loaded *before* `libwayland-client`
in the dynamic linker. Python imports alone don't satisfy this.

**Workaround.** The daemon auto-re-execs itself with the right
`LD_PRELOAD` set ([`platform/layer_shell_preload.py`](../src/devpane/platform/layer_shell_preload.py)).
On distros that ship a non-standard library path, the fallback scan in
`_FALLBACK_LIBDIRS` may need extending.

**Scoped:** M4. **Could be revisited if:** the library upstream changes
its init model.

### X11 hints, not override-redirect

**What.** On X11, DevPane requests `_NET_WM_WINDOW_TYPE_DOCK` plus
`ABOVE` / `SKIP_TASKBAR` / `SKIP_PAGER`. Some WMs may decorate or place
the window in ways that don't match the layer-shell experience.

**Why.** Override-redirect bypasses the WM entirely and complicates
focus management. M4 favored portability; the dock hint is honored by
most modern X11 WMs (i3, openbox, xfwm4, KWin under X11).

**Workaround.** Use a Wayland session with `gtk4-layer-shell` for the
best UX. On i3, add a `for_window [class="io.github.nfantunes.DevPane"]
floating enable` rule.

**Scoped:** M4. **Could be revisited if:** an X11 user reports the dock
hint is insufficient.

## Hotkeys

### No portal-based global hotkey

**What.** DevPane does not register its own global hotkey via the
`org.freedesktop.portal.GlobalShortcuts` portal.

**Why.** Portal support is uneven across compositors and adds
significant complexity. Delegating to the DE's keyboard settings works
identically on every desktop.

**Workaround.** Bind `devpane-toggle` (or `devpaned` — running it twice
acts as a toggle) to a key in your DE's keyboard settings. See
[HOTKEY-SETUP.md](HOTKEY-SETUP.md).

**Scoped:** plan §"Out of Scope for v1".

## Editor

### No collision resolution

**What.** If you edit the same note in DevPane *and* in another tool
(e.g. your editor + `git pull`) at the same time, the last write wins.
There is no merge or conflict marker.

**Why.** Detection requires file watching + diff logic; not worth the
complexity when the obvious workflow is "use one editor at a time".

**Workaround.** The notes dir is a plain markdown filesystem — run `git
init` in it and you get a real history.

**Scoped:** M5.

### Multi-monitor focus on show

**What.** When the pane is presented, GTK focuses our window via
`Adw.Application.present()`, but on some Wayland compositors the
focused-output question is decided by the compositor. KDE honors it;
GNOME may briefly mis-focus.

**Workaround.** Toggle once more.

**Scoped:** M6.

## Persistence

### Prefs are JSON, not GSettings (still)

**What.** User prefs (`height_ratio`, `last_note`, `animate`) are stored
in `$XDG_CONFIG_HOME/devpane/prefs.json`, not read from GSettings —
even though the GSettings schema is now shipped by the packaging.

**Why.** Migrating the runtime to GSettings means the dev workflow
(running from `src/`) breaks unless schemas are compiled locally and
`GSETTINGS_SCHEMA_DIR` is set. We shipped the schema XML in M7 so
distro packages install it and so the schema ID is reserved, but the
code still reads/writes JSON.

**Workaround.** Edit the JSON file directly (the daemon re-reads it on
each startup).

**Scoped:** M6/M7. **Will revisit in:** v0.2 when we add a JSON↔GSettings
shim that prefers GSettings if available, with one-time migration from
JSON.

## Distribution

### Packaging files shipped, not published

**What.** As of v0.1.0 the repo includes an Arch PKGBUILD, a systemd
user unit, an XDG autostart `.desktop`, AppStream metainfo, a
placeholder SVG icon, a GSettings schema, and a Flatpak manifest. None
have been **published** — the PKGBUILD isn't pushed to the AUR and the
Flatpak isn't on Flathub.

**Workaround.** Build locally:

- Arch: `cd packaging/arch && makepkg -si`
- Flatpak: `flatpak-builder --user --install build-dir
  packaging/flatpak/io.github.nfantunes.DevPane.yml`

**Scoped:** M7. **Will revisit in:** v0.1.x when the maintainer is
ready to commit to AUR + Flathub upkeep.

### Flatpak is a skeleton

**What.** The Flatpak manifest builds locally and produces a working
app, but it's not Flathub-ready: no screenshots in the AppStream
metainfo, no designed icon, no `flatpak run-checker` pass, and the
`sha256` for the `gtk4-layer-shell` module source is a placeholder.

**Workaround.** Replace the `sha256: 00000...` line in the manifest with
the real hash (`curl -sL <url> | sha256sum`) before building.

**Scoped:** M7.

### Placeholder app icon

**What.** `data/icons/.../io.github.nfantunes.DevPane.svg` is a
geometric placeholder, not a designed icon.

**Workaround.** Replace the SVG with a proper icon before any public
release. The package builds and installs it identically.

**Scoped:** M7.

### Tests under non-system Python skip GUI paths

**What.** Tests that need `gi.repository` (Gtk4LayerShell factory test)
skip under pyenv-managed Python where PyGObject is not available.

**Workaround.** Run the test suite under the distro's Python
(`/usr/bin/python3`) for full coverage. CI does this.

**Scoped:** M3.
