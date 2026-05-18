"""GLib-main-thread debounced autosave.

Differs from ``util.debounce.Debouncer`` (which uses ``threading.Timer``)
in that this runs the callback on the GLib main thread. That matters for
the editor: the save reads from a ``GtkTextBuffer`` (main-thread-only) and
writes to a SQLite connection that was opened on the main thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib  # noqa: E402

_log = logging.getLogger(__name__)


class AutoSaver:
    """Debounce repeated calls; fire `fn` `delay_ms` after the last schedule()."""

    def __init__(self, delay_ms: int, fn: Callable[[], None]) -> None:
        self._delay_ms = delay_ms
        self._fn = fn
        self._timer_id: int | None = None

    def schedule(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add(self._delay_ms, self._fire)

    def _fire(self) -> bool:
        self._timer_id = None
        try:
            self._fn()
        except Exception:
            _log.exception("autosave callback failed")
        return False  # GLib.SOURCE_REMOVE

    def flush(self) -> bool:
        """Run any pending save immediately. Returns True if one was pending."""
        if self._timer_id is None:
            return False
        GLib.source_remove(self._timer_id)
        self._timer_id = None
        try:
            self._fn()
        except Exception:
            _log.exception("autosave flush failed")
        return True

    def cancel(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    @property
    def pending(self) -> bool:
        return self._timer_id is not None
