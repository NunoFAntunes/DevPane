"""DropDownWindow — the visible drop-down pane.

M3 is the minimal viable window: an ``Adw.ApplicationWindow`` sized to
full screen width and 60% of screen height, with a placeholder body.
Top-edge anchoring via layer-shell / X11 dock semantics arrives in M4;
for M3 the window appears wherever the compositor chooses to put it.

GTK objects in this module must only be touched from the GLib main
thread. ``GtkController`` (below) bridges from the asyncio worker thread.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

if TYPE_CHECKING:
    from devpane.platform.adapter import PlatformAdapter

_log = logging.getLogger(__name__)

_HEIGHT_FRACTION = 0.6


class DropDownWindow(Adw.ApplicationWindow):  # type: ignore[misc]
    """The drop-down pane window. Visibility is owned by callers."""

    def __init__(self, app: Adw.Application, adapter: PlatformAdapter) -> None:
        super().__init__(application=app)
        self.set_title("DevPane")
        self.set_decorated(False)
        self._build_body()
        self._pane_visible = False
        self._adapter = adapter
        adapter.configure(self)
        _log.info("window: configured for adapter %s", adapter.name)

    def _build_body(self) -> None:
        # M3 placeholder content; replaced by the markdown editor in M5.
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="DevPane"))
        toolbar_view.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_top(24)
        body.set_margin_bottom(24)
        body.set_margin_start(24)
        body.set_margin_end(24)
        body.append(Gtk.Label(label="DevPane drop-down (M3)"))
        sub = Gtk.Label(label="Press your bound key again to hide. Editor lands in M5.")
        sub.add_css_class("dim-label")
        body.append(sub)

        toolbar_view.set_content(body)
        self.set_content(toolbar_view)

    def is_pane_visible(self) -> bool:
        return self._pane_visible

    def show_pane(self) -> None:
        self._size_to_monitor()
        self.present()
        self._adapter.on_show(self)
        self._pane_visible = True
        _log.debug("window: shown")

    def hide_pane(self) -> None:
        self._adapter.on_hide(self)
        self.set_visible(False)
        self._pane_visible = False
        _log.debug("window: hidden")

    def toggle_pane(self) -> None:
        if self._pane_visible:
            self.hide_pane()
        else:
            self.show_pane()

    def _size_to_monitor(self) -> None:
        display = self.get_display()
        if display is None:
            return
        monitors = display.get_monitors()
        if monitors.get_n_items() == 0:
            return
        # M3: use the first monitor. M6 will pick the monitor under the cursor.
        monitor = monitors.get_item(0)
        if monitor is None:
            return
        geom = monitor.get_geometry()
        width = geom.width
        height = int(geom.height * _HEIGHT_FRACTION)
        self.set_default_size(width, height)


class GtkController:
    """``WindowController`` impl that bridges asyncio → GLib main thread."""

    def __init__(self, window: DropDownWindow, loop: asyncio.AbstractEventLoop) -> None:
        self._window = window
        self._loop = loop

    async def show(self) -> bool:
        return await self._call_on_main(self._window.show_pane)

    async def hide(self) -> bool:
        return await self._call_on_main(self._window.hide_pane)

    async def toggle(self) -> bool:
        return await self._call_on_main(self._window.toggle_pane)

    def is_visible(self) -> bool:
        # Reading a bool across threads is fine in CPython; the value will be
        # whatever the most recent main-thread update left it at.
        return self._window.is_pane_visible()

    async def _call_on_main(self, fn: Callable[[], None]) -> bool:
        fut: asyncio.Future[bool] = self._loop.create_future()

        def _runner() -> bool:
            try:
                fn()
                self._loop.call_soon_threadsafe(fut.set_result, self._window.is_pane_visible())
            except Exception as e:  # boundary: ferry exception to the awaiter
                self._loop.call_soon_threadsafe(fut.set_exception, e)
            return False  # one-shot

        GLib.idle_add(_runner)
        return await fut
