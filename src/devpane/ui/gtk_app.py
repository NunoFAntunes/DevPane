"""Adw.Application bootstrap and the asyncio↔GLib bridge.

Threading model:

- **Main thread**: GTK / GLib main loop. ``Adw.Application.run`` runs here.
  All window operations happen on this thread.
- **Worker thread (``devpane-asyncio``)**: an asyncio event loop. The IPC
  server lives here. Command handlers schedule window operations onto the
  main thread via ``GLib.idle_add`` and await the result.

The two loops shut down together: ``on_shutdown`` (GTK side) signals the
asyncio loop's stop event, and the asyncio thread, when it finishes
serving, schedules ``app.quit()`` on the main thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
import threading
from collections.abc import Awaitable, Callable

import gi

# gtk4-layer-shell MUST be loaded before GTK initializes libwayland or it
# silently no-ops. We eagerly import it here, before any Adw/Gtk symbol is
# touched, so the layer-shell adapter (chosen later in `on_activate`) is
# guaranteed to work. If the typelib is absent, swallow the error — the
# factory will pick a non-layer-shell adapter.
try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as _LayerShell  # noqa: F401
except (ImportError, ValueError):
    pass

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib  # noqa: E402

from devpane.platform.adapter import pick_adapter  # noqa: E402
from devpane.platform.detect import detect  # noqa: E402
from devpane.store import index as store_index  # noqa: E402
from devpane.ui.window import DropDownWindow, GtkController  # noqa: E402

_log = logging.getLogger(__name__)

APPLICATION_ID = "com.devpane.Daemon"

# Type for the asyncio serve coroutine the daemon hands us:
# ``serve(controller, stop_event)`` returns the daemon exit code.
ServeFn = Callable[[GtkController, asyncio.Event], Awaitable[int]]


def run_gtk(serve: ServeFn) -> int:
    """Launch the GTK app and the asyncio worker. Returns the process exit code."""
    app = Adw.Application(
        application_id=APPLICATION_ID,
        flags=Gio.ApplicationFlags.NON_UNIQUE,
    )

    state: dict[str, object] = {
        "exit_code": 0,
        "thread": None,
        "loop": None,
        "stop_event": None,
    }
    ready = threading.Event()

    def on_activate(app: Adw.Application) -> None:
        adapter = pick_adapter(detect())
        # SQLite connection lives on the GTK main thread alongside the editor.
        conn = store_index.connect()
        state["index_conn"] = conn
        window = DropDownWindow(app, adapter, conn)
        # The window is created hidden. Toggle commands present/hide it.
        # Without explicit hold(), the app would quit as soon as it has no
        # visible windows. The hold keeps it alive in the background.
        app.hold()

        def asyncio_main() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            stop_event = asyncio.Event()
            state["loop"] = loop
            state["stop_event"] = stop_event
            controller = GtkController(window, loop)
            ready.set()
            try:
                state["exit_code"] = loop.run_until_complete(serve(controller, stop_event))
            except Exception:
                _log.exception("asyncio thread crashed")
                state["exit_code"] = 1
            finally:
                loop.close()
                # When asyncio is done, ask GTK to quit on the main thread.
                GLib.idle_add(app.quit)

        t = threading.Thread(target=asyncio_main, daemon=True, name="devpane-asyncio")
        state["thread"] = t
        t.start()
        ready.wait()
        _log.info("gtk app activated; asyncio worker running")

    def on_shutdown(_app: Adw.Application) -> None:
        # Triggered by Ctrl+C, SIGTERM, or our own app.quit(). Signal the
        # asyncio loop to wind down; the thread will exit shortly after.
        # If asyncio asked *us* to quit (the common case), its loop is
        # already closed — guard against the race.
        loop = state.get("loop")
        stop_event = state.get("stop_event")
        if (
            isinstance(loop, asyncio.AbstractEventLoop)
            and not loop.is_closed()
            and isinstance(stop_event, asyncio.Event)
        ):
            # The loop may close between the is_closed() check and this call.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(stop_event.set)
        thread = state.get("thread")
        if isinstance(thread, threading.Thread):
            thread.join(timeout=5.0)
            if thread.is_alive():
                _log.warning("asyncio worker did not exit within 5s")
        conn = state.get("index_conn")
        if isinstance(conn, sqlite3.Connection):
            with contextlib.suppress(Exception):
                conn.close()

    app.connect("activate", on_activate)
    app.connect("shutdown", on_shutdown)

    rc: int = app.run([])
    # If the asyncio thread errored, prefer its exit code.
    asyncio_rc = state.get("exit_code")
    if isinstance(asyncio_rc, int) and asyncio_rc != 0:
        return asyncio_rc
    return rc
