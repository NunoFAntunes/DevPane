# DevPane — Hotkey Setup

DevPane delegates global-hotkey registration to your desktop environment.
Bind `devpane-toggle` to a key of your choice (F12 is the recommended
default).

## GNOME (Wayland or X11)

1. Open **Settings → Keyboard → View and Customize Shortcuts**.
2. Scroll to **Custom Shortcuts** and click **+**.
3. Name: `DevPane`. Command: `devpane-toggle`. Shortcut: press F12.
4. Save.

## KDE Plasma (Wayland or X11)

1. Open **System Settings → Shortcuts → Custom Shortcuts**.
2. **Edit → New → Global Shortcut → Command/URL**.
3. Trigger tab: set `F12`. Action tab: command `devpane-toggle`.
4. Apply.

## Sway

Add to `~/.config/sway/config`:

```
bindsym F12 exec devpane-toggle
```

Reload with `swaymsg reload`.

## Hyprland

Add to `~/.config/hypr/hyprland.conf`:

```
bind = , F12, exec, devpane-toggle
```

Reload Hyprland (`hyprctl reload`).

## i3 / xmonad / other X11 WMs

Bind `F12` to `devpane-toggle` using your WM's native config. For i3:

```
bindsym F12 exec --no-startup-id devpane-toggle
```

## Verifying the binding

After binding:

1. Run `devpaned &` (or rely on autostart from `data/com.devpane.Daemon.desktop`).
2. Press F12 → the pane should drop down within 200 ms.
3. Press F12 again → the pane hides and the file is saved.

If nothing happens, run `devpane-toggle status` from a terminal to confirm
the daemon is reachable. If not, start it manually with
`scripts/dev-run.sh` and check the logs.

## Verified compatibility matrix

Filled in during M4 / M7 validation.

| Session | Drop-down style | Status |
|---------|-----------------|--------|
| Sway | layer-shell | TBD |
| Hyprland | layer-shell | TBD |
| KDE Plasma 6 (Wayland) | layer-shell | TBD |
| GNOME 46+ (Wayland) | top-anchored toplevel | TBD |
| GNOME (X11) | dock + override-redirect | TBD |
| i3 (X11) | dock + override-redirect | TBD |
