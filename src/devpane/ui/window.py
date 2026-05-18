"""DropDownWindow — the visible drop-down pane.

Hosts the markdown editor and header. Lifecycle:

- ``show_pane()`` reloads the current note from disk (so external edits
  are visible), then presents and focuses the editor.
- ``hide_pane()`` flushes any pending autosave so quitting/hiding never
  loses unsaved text.

Keyboard bindings (window-local):

- ``Escape``      hide the pane
- ``Ctrl+N``      create a new note (auto-named) and switch to it
- ``Ctrl+K``      open the note switcher popover
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import sqlite3
from collections.abc import Callable
from importlib import resources
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from devpane.store import notes  # noqa: E402
from devpane.ui.editor import NoteEditor  # noqa: E402
from devpane.ui.header import PaneHeader  # noqa: E402

if TYPE_CHECKING:
    from devpane.platform.adapter import PlatformAdapter

_log = logging.getLogger(__name__)

_HEIGHT_FRACTION = 0.6
_CSS_LOADED = False


def _load_css_once() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    css = resources.files("devpane.ui").joinpath("styles.css").read_text(encoding="utf-8")
    provider = Gtk.CssProvider()
    provider.load_from_data(css, -1)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        _CSS_LOADED = True


class DropDownWindow(Adw.ApplicationWindow):  # type: ignore[misc]
    """The drop-down pane window. Visibility is owned by callers."""

    def __init__(
        self,
        app: Adw.Application,
        adapter: PlatformAdapter,
        conn: sqlite3.Connection,
    ) -> None:
        super().__init__(application=app)
        self.set_title("DevPane")
        self.set_decorated(False)
        self.add_css_class("devpane-window")
        _load_css_once()

        self._adapter = adapter
        self._pane_visible = False

        self._editor = NoteEditor(conn)
        self._header = PaneHeader(on_new=self._new_note, on_switch_to=self._switch_to)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(self._header.widget)
        toolbar_view.set_content(self._editor)
        self.set_content(toolbar_view)

        self._install_shortcuts()

        adapter.configure(self)
        _log.info("window: configured for adapter %s", adapter.name)

        # Ensure a default note exists so first show has content to load.
        notes.ensure_default()
        self._load(notes.DEFAULT_NOTE)

    # ---- visibility ----

    def is_pane_visible(self) -> bool:
        return self._pane_visible

    def show_pane(self) -> None:
        # Re-read the active note from disk so changes made externally
        # (editor, `git pull`, Syncthing) are reflected.
        if self._editor.current_note is not None:
            self._load(self._editor.current_note)
        self._size_to_monitor()
        self.present()
        self._adapter.on_show(self)
        self._editor.focus()
        self._pane_visible = True
        _log.debug("window: shown")

    def hide_pane(self) -> None:
        # Always flush before hiding so nothing is in flight when we sleep.
        self._editor.flush()
        self._adapter.on_hide(self)
        self.set_visible(False)
        self._pane_visible = False
        _log.debug("window: hidden")

    def toggle_pane(self) -> None:
        if self._pane_visible:
            self.hide_pane()
        else:
            self.show_pane()

    # ---- internals ----

    def _install_shortcuts(self) -> None:
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if keyval == Gdk.KEY_Escape:
            self.hide_pane()
            return True
        if ctrl and keyval in (Gdk.KEY_n, Gdk.KEY_N):
            self._new_note()
            return True
        if ctrl and keyval in (Gdk.KEY_k, Gdk.KEY_K):
            self._header.open_switcher()
            return True
        return False

    def _new_note(self) -> None:
        # Format: note-YYYYMMDD-HHMM. Append a counter if it collides
        # within the same minute.
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        base = f"note-{stamp}"
        name = f"{base}.md"
        suffix = 1
        while notes.exists(name):
            suffix += 1
            name = f"{base}-{suffix}.md"
        notes.write_atomic(name, "")
        _log.info("window: new note %s", name)
        self._switch_to(name)

    def _switch_to(self, name: str) -> None:
        self._load(name)

    def _load(self, name: str) -> None:
        self._editor.load_note(name)
        canon = notes.canonical_name(name)
        self._header.set_current_note(canon)

    def _size_to_monitor(self) -> None:
        display = self.get_display()
        if display is None:
            return
        monitors = display.get_monitors()
        if monitors.get_n_items() == 0:
            return
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
        # Reading a bool across threads is fine in CPython.
        return self._window.is_pane_visible()

    async def _call_on_main(self, fn: Callable[[], None]) -> bool:
        fut: asyncio.Future[bool] = self._loop.create_future()

        def _runner() -> bool:
            try:
                fn()
                self._loop.call_soon_threadsafe(fut.set_result, self._window.is_pane_visible())
            except Exception as e:
                self._loop.call_soon_threadsafe(fut.set_exception, e)
            return False

        GLib.idle_add(_runner)
        return await fut
