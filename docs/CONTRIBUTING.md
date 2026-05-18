# Contributing to DevPane

## Development setup

Requires Python 3.11+, GTK 4, libadwaita, GtkSourceView 5, and PyGObject.

On Arch:

```
sudo pacman -S python python-gobject gtk4 libadwaita gtksourceview5 \
    gtk4-layer-shell python-xlib
```

`gtk4-layer-shell` enables the true top-anchored drop-down on KDE / Sway /
Hyprland; the daemon falls back to a plain borderless window without it.
`python-xlib` is only needed for X11 sessions.

On Debian/Ubuntu:

```
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
    gir1.2-gtksource-5 gir1.2-gtk4layershell-1.0
```

Then:

```
python -m venv .venv --system-site-packages   # so PyGObject is visible
source .venv/bin/activate
pip install -e ".[dev,x11]"
```

The `--system-site-packages` flag is intentional: PyGObject is awkward to
install from PyPI; using the distro package is simpler and faster.

## Running from source

```
./scripts/dev-run.sh
```

This sets `PYTHONPATH=src` and `G_MESSAGES_DEBUG=devpane`, then launches the
daemon.

## Tests, linting, types

```
ruff check .
ruff format .
mypy src
xvfb-run -a pytest
```

CI runs the same commands on every PR.

## Project layout

See [OVERVIEW.md](OVERVIEW.md#repository-map) for the directory map and
[ARCHITECTURE.md](ARCHITECTURE.md#module-boundaries) for the module
boundaries you should respect when adding code.

## Commit hygiene

- Keep commits focused; one milestone artifact per commit when possible.
- Follow Conventional Commits style: `feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`.
- Reference the milestone (e.g. `feat(store): atomic notes writer (M1)`).

## Reporting issues

Open an issue with:

- DE / compositor / session type (`echo $XDG_SESSION_TYPE`,
  `echo $XDG_CURRENT_DESKTOP`).
- DevPane version (`devpaned --version`).
- Relevant log output from `$XDG_STATE_HOME/devpane/log`.
