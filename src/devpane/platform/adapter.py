"""Platform adapter protocol and factory.

A ``PlatformAdapter`` configures the drop-down window for the current
session (Wayland layer-shell, plain Wayland, or X11) and runs any per-show
/ per-hide work such as keyboard grabs.

The window doesn't import compositor-specific libraries directly — it only
talks to an adapter. This keeps gtk4-layer-shell and python-xlib out of the
import path on platforms that don't need them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from devpane.platform.detect import PlatformInfo, SessionType

if TYPE_CHECKING:
    from devpane.ui.window import DropDownWindow

_log = logging.getLogger(__name__)


class PlatformAdapter(Protocol):
    """Configures a ``DropDownWindow`` for the current session."""

    name: str

    def configure(self, window: DropDownWindow) -> None:
        """Called once when the window is constructed, before it is shown."""

    def on_show(self, window: DropDownWindow) -> None:
        """Called every time the window becomes visible."""

    def on_hide(self, window: DropDownWindow) -> None:
        """Called every time the window is hidden."""


class NoopAdapter:
    """Final fallback. Does nothing; the window stays a plain Adw.Window."""

    name = "noop"

    def configure(self, window: DropDownWindow) -> None:
        return None

    def on_show(self, window: DropDownWindow) -> None:
        return None

    def on_hide(self, window: DropDownWindow) -> None:
        return None


def pick_adapter(info: PlatformInfo) -> PlatformAdapter:
    """Choose the best adapter for the current session.

    Order of preference:

    1. **Wayland + layer-shell** — true top-anchored drop-down. Used on
       Sway, Hyprland, KDE Plasma 6, and any other wlroots-based compositor
       when ``gtk4-layer-shell`` is installed.
    2. **Wayland without layer-shell** — used on GNOME/Mutter and on
       layer-shell-capable compositors where the library is missing. The
       window is a plain top-anchored toplevel; the compositor decides
       placement.
    3. **X11** — sets ``_NET_WM_WINDOW_TYPE_DOCK`` and ``keep above`` on
       the surface; most WMs honor these for floating dock-like windows.
    4. **No display** — should never happen in GTK mode, but ``NoopAdapter``
       keeps the type-checker happy.
    """
    if info.session is SessionType.WAYLAND and info.has_layer_shell:
        from devpane.platform.wayland_layer import LayerShellAdapter

        _log.info("adapter: wayland layer-shell")
        return LayerShellAdapter()
    if info.session is SessionType.WAYLAND:
        from devpane.platform.wayland_plain import WaylandPlainAdapter

        _log.info("adapter: wayland plain (no layer-shell)")
        return WaylandPlainAdapter()
    if info.session is SessionType.X11:
        from devpane.platform.x11 import X11Adapter

        _log.info("adapter: x11")
        return X11Adapter()
    _log.warning("adapter: noop (no display detected)")
    return NoopAdapter()
