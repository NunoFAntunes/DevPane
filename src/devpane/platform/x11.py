"""X11 adapter — request DOCK type hint via Xlib.

GTK 4 dropped most of its X11-specific positioning API, so we use
``python-xlib`` directly to set ``_NET_WM_WINDOW_TYPE`` to
``_NET_WM_WINDOW_TYPE_DOCK`` and ``_NET_WM_STATE`` to ``ABOVE`` and
``SKIP_TASKBAR`` / ``SKIP_PAGER``. Most reasonable X11 WMs (i3, openbox,
xfwm4, kwin under X11) honor these hints.

We deliberately avoid override-redirect for M4 — it produces the most
"Guake-like" feel but bypasses the WM entirely and complicates focus
management. If the M5 editor needs override-redirect for focus stealing,
we'll add it then.

``python-xlib`` is imported lazily so the adapter is only required on X11
sessions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from devpane.ui.window import DropDownWindow

_log = logging.getLogger(__name__)


class X11Adapter:
    name = "x11"

    def __init__(self) -> None:
        self._xlib_available = self._check_xlib()

    def _check_xlib(self) -> bool:
        try:
            import Xlib.display  # noqa: F401
        except ImportError:
            _log.warning(
                "x11 adapter: python-xlib not installed; window will lack DOCK hint. "
                "Install with `pip install python-xlib` or the distro package."
            )
            return False
        return True

    def configure(self, window: DropDownWindow) -> None:
        window.set_resizable(False)
        # The DOCK / ABOVE hints must be set on the X11 window, which only
        # exists after realize. Defer to a one-shot signal.
        window.connect("realize", self._on_realize)

    def _on_realize(self, window: DropDownWindow) -> None:
        if not self._xlib_available:
            return
        xid = self._get_xid(window)
        if xid is None:
            _log.warning("x11 adapter: could not retrieve XID; skipping hints")
            return
        self._apply_hints(xid)

    def _get_xid(self, window: DropDownWindow) -> int | None:
        surface = window.get_surface()
        if surface is None:
            return None
        try:
            from gi.repository import GdkX11
        except (ImportError, ValueError):
            _log.warning("x11 adapter: GdkX11 typelib not available")
            return None
        try:
            xid_raw: Any = GdkX11.X11Surface.get_xid(surface)
        except Exception:
            _log.exception("x11 adapter: get_xid failed")
            return None
        return int(xid_raw)

    def _apply_hints(self, xid: int) -> None:
        import Xlib.display
        import Xlib.X

        try:
            display = Xlib.display.Display()
            atom = display.intern_atom
            win = display.create_resource_object("window", xid)

            wm_type = atom("_NET_WM_WINDOW_TYPE")
            dock = atom("_NET_WM_WINDOW_TYPE_DOCK")
            win.change_property(wm_type, Xlib.X.AnyPropertyType, 32, [dock])

            wm_state = atom("_NET_WM_STATE")
            states = [
                atom("_NET_WM_STATE_ABOVE"),
                atom("_NET_WM_STATE_SKIP_TASKBAR"),
                atom("_NET_WM_STATE_SKIP_PAGER"),
            ]
            win.change_property(wm_state, Xlib.X.AnyPropertyType, 32, states)
            display.sync()
            _log.debug("x11 adapter: DOCK + ABOVE hints set on xid=%#x", xid)
        except Exception:
            _log.exception("x11 adapter: failed to set window hints")

    def on_show(self, window: DropDownWindow) -> None:
        return None

    def on_hide(self, window: DropDownWindow) -> None:
        return None
