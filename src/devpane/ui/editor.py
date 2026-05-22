"""Markdown editor widget backed by ``GtkSourceView``.

Owns:

- The text buffer + view (line wrap, monospace, no line numbers).
- The autosave debouncer (2-second window).
- The "current note" identity. Switching notes flushes the previous one.
- Light/dark style scheme tracking via ``Adw.StyleManager``.

The editor talks to the store directly (``notes.write_atomic`` +
``index.touch``). Both operations are fast and main-thread-safe.
"""

from __future__ import annotations

import logging
import sqlite3

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gtk, GtkSource  # noqa: E402

from devpane.store import index, notes  # noqa: E402
from devpane.ui.autosave import AutoSaver  # noqa: E402

_log = logging.getLogger(__name__)

_AUTOSAVE_MS = 2000


class NoteEditor(Gtk.Box):  # type: ignore[misc]
    """Scrolled GtkSourceView + autosave, with a notion of "current note"."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._conn = conn
        self._current_note: str | None = None
        # While True, buffer changes do not trigger autosave (used when
        # programmatically loading a note into the buffer).
        self._loading = False

        self._buffer = GtkSource.Buffer()
        self._apply_language()
        self._apply_style_scheme()

        self._view = GtkSource.View.new_with_buffer(self._buffer)
        self._view.set_monospace(True)
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._view.set_show_line_numbers(False)
        self._view.set_left_margin(12)
        self._view.set_right_margin(12)
        self._view.set_top_margin(12)
        self._view.set_bottom_margin(12)
        self._view.add_css_class("devpane-editor")

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self._view)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        self.append(scrolled)

        self._autosaver = AutoSaver(_AUTOSAVE_MS, self._save_now)
        self._buffer.connect("changed", self._on_changed)

        # Track system dark-mode changes.
        sm = Adw.StyleManager.get_default()
        sm.connect("notify::dark", lambda *_: self._apply_style_scheme())

    @property
    def current_note(self) -> str | None:
        return self._current_note

    @property
    def view(self) -> GtkSource.View:
        return self._view

    def load_note(self, name: str) -> None:
        """Switch to `name`, flushing the previous note's state first."""
        canon = notes.canonical_name(name)
        # If we're truly switching, save the outgoing note. If we're
        # "switching" to the same note we're already on, do not flush —
        # that would clobber a cursor position written externally
        # (e.g. by a sibling process or the prior daemon run) with the
        # current in-buffer position.
        if self._current_note is not None and self._current_note != canon:
            self.flush()
        self._load_into_buffer(canon)

    def refresh(self) -> None:
        """Reload the current note's text + cursor from disk. No-op if none."""
        if self._current_note is None:
            return
        self._load_into_buffer(self._current_note)

    def _load_into_buffer(self, canon: str) -> None:
        existed = notes.exists(canon)
        body = notes.read_task(canon)[1] if existed else ""
        # Touch first so the row exists; then read the cursor.
        index.touch(self._conn, canon, body)
        saved_offset = index.get_cursor(self._conn, canon) if existed else 0
        self._loading = True
        try:
            self._buffer.set_text(body)
            # Clamp to the current buffer length — body length may have
            # shrunk since the cursor was saved (e.g. external truncation).
            offset = max(0, min(saved_offset, self._buffer.get_char_count()))
            self._buffer.place_cursor(self._buffer.get_iter_at_offset(offset))
        finally:
            self._loading = False
        self._current_note = canon
        _log.info("editor: loaded %s (%d bytes, cursor=%d)", canon, len(body), offset)

    def flush(self) -> None:
        """Force any pending autosave to run synchronously, and snapshot the cursor."""
        had_pending = self._autosaver.flush()
        # The cursor moves without dirtying the buffer (e.g. arrow keys), so
        # save it explicitly even when no autosave was pending.
        if not had_pending and self._current_note is not None:
            self._save_cursor_only()

    def focus(self) -> None:
        self._view.grab_focus()

    # ---- internals ----

    def _on_changed(self, _buffer: GtkSource.Buffer) -> None:
        if self._loading or self._current_note is None:
            return
        self._autosaver.schedule()

    def _save_now(self) -> None:
        if self._current_note is None:
            return
        start, end = self._buffer.get_bounds()
        text = self._buffer.get_text(start, end, False)
        meta, _ = notes.read_task(self._current_note) if notes.exists(self._current_note) else ({}, "")
        notes.write_task(self._current_note, meta, text)
        index.touch(self._conn, self._current_note, text)
        self._save_cursor_only()
        _log.debug("editor: saved %s (%d bytes)", self._current_note, len(text))

    def _save_cursor_only(self) -> None:
        if self._current_note is None:
            return
        offset = int(self._buffer.get_property("cursor-position"))
        index.save_cursor(self._conn, self._current_note, offset)

    def _apply_language(self) -> None:
        lang = GtkSource.LanguageManager.get_default().get_language("markdown")
        if lang is not None:
            self._buffer.set_language(lang)

    def _apply_style_scheme(self) -> None:
        sm = Adw.StyleManager.get_default()
        scheme_name = "Adwaita-dark" if sm.get_dark() else "Adwaita"
        scheme = GtkSource.StyleSchemeManager.get_default().get_scheme(scheme_name)
        if scheme is not None:
            self._buffer.set_style_scheme(scheme)
