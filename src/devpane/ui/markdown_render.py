"""Live markdown rendering layered over a ``GtkSource.Buffer``.

Notion-style: visible styling (headers grow, bold/italic/code render
inline, links go accent-coloured) PLUS markers (``#``, ``**``, `` ` ``,
``[…](…)``) hidden when the cursor is elsewhere and revealed when it
returns to the line/span.

The buffer's text is never mutated — only ``Gtk.TextTag``s are added and
removed — so autosave, undo/redo, the slash menu, and copy/paste of the
source are unaffected.

The pure helper :func:`compute_reveal_set` is GTK-free and tested in
``tests/test_markdown_reveal.py``.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

from devpane.ui.markdown_scan import RegexScanner, Scanner, Span, SpanKind  # noqa: E402

_log = logging.getLogger(__name__)


# How much rescans are coalesced. Keystrokes within this window share one
# scan pass. 30 ms is well under perceived latency and prevents thrashing
# during fast typing or paste.
_RESCAN_DELAY_MS = 30


def compute_reveal_set(
    spans: list[Span],
    cursor_offset: int,
    active_range: tuple[int, int],
) -> set[tuple[int, int]]:
    """Marker ranges that should be revealed (rendered visible) right now.

    ``active_range`` is the cursor's current line bounds, optionally already
    expanded to include any selection. We then expand it further to cover
    any ``Span`` that contains the cursor — so multi-line spans (fenced
    code, future block constructs) reveal both ends when you're inside.
    """
    a_start, a_end = active_range
    for span in spans:
        if span.start <= cursor_offset < span.end:
            a_start = min(a_start, span.start)
            a_end = max(a_end, span.end)

    revealed: set[tuple[int, int]] = set()
    for span in spans:
        for mr in span.marker_ranges:
            if mr[0] < a_end and mr[1] > a_start:
                revealed.add(mr)
    return revealed


class MarkdownRenderer:
    """Drives live markdown rendering on a ``GtkSource.Buffer``.

    Attach with ``MarkdownRenderer(buffer)``; the renderer wires its own
    signals. Call :meth:`rescan_all` after a programmatic ``set_text``
    (the editor does this in ``_load_into_buffer``) and
    :meth:`refresh_theme` when the system light/dark mode flips.
    """

    def __init__(self, buffer: Gtk.TextBuffer, scanner: Scanner | None = None) -> None:
        self._buffer = buffer
        self._scanner: Scanner = scanner or RegexScanner()
        self._spans: list[Span] = []
        self._suppress = False
        self._rescan_source: int | None = None
        self._reveal_source: int | None = None

        self._tags: dict[SpanKind, Gtk.TextTag] = {}
        self._invisible: Gtk.TextTag | None = None
        self._revealed: Gtk.TextTag | None = None
        self._build_tags()
        self.refresh_theme()

        self._sig_changed = buffer.connect("changed", self._on_changed)
        self._sig_cursor = buffer.connect("notify::cursor-position", self._on_cursor)
        self._sig_sel = buffer.connect("notify::has-selection", self._on_cursor)

    # ---- public API ----

    def set_suppressed(self, suppressed: bool) -> None:
        """While suppressed, buffer changes do not schedule a rescan.

        Used by the editor's ``_load_into_buffer`` to avoid scanning
        partial state during ``set_text``; the editor calls
        :meth:`rescan_all` once the load completes.
        """
        self._suppress = suppressed

    def rescan_all(self) -> None:
        """Re-scan the whole buffer and re-apply all tags. Cheap enough at
        the size of typical notes (sub-millisecond)."""
        try:
            text = self._get_text()
            self._spans = self._scanner.scan(text)
            self._apply_all_tags()
            self._apply_reveal()
        except Exception:
            _log.exception("markdown: rescan_all failed")

    def refresh_theme(self) -> None:
        """Re-apply theme-dependent tag properties (link colour, code bg)."""
        dark = Adw.StyleManager.get_default().get_dark()
        code_bg = _rgba(1, 1, 1, 0.10) if dark else _rgba(0, 0, 0, 0.06)
        link_fg = _rgba_hex("#62a0ea") if dark else _rgba_hex("#1c71d8")
        quote_fg = _rgba_hex("#c0bfbc") if dark else _rgba_hex("#5e5c64")
        hr_fg = _rgba_hex("#9a9996") if dark else _rgba_hex("#77767b")

        self._tags[SpanKind.CODE_INLINE].set_property("background-rgba", code_bg)
        self._tags[SpanKind.CODE_BLOCK].set_property("paragraph-background-rgba", code_bg)
        self._tags[SpanKind.LINK].set_property("foreground-rgba", link_fg)
        self._tags[SpanKind.QUOTE].set_property("foreground-rgba", quote_fg)
        self._tags[SpanKind.HR].set_property("foreground-rgba", hr_fg)

    # ---- signal handlers ----

    def _on_changed(self, _buffer: Gtk.TextBuffer) -> None:
        if self._suppress:
            return
        if self._rescan_source is not None:
            GLib.source_remove(self._rescan_source)
        self._rescan_source = GLib.timeout_add(_RESCAN_DELAY_MS, self._do_rescan)

    def _on_cursor(self, *_args) -> None:
        if self._suppress:
            return
        # Coalesce cursor-position + has-selection bursts (selection drags
        # fire both rapidly).
        if self._reveal_source is not None:
            return
        self._reveal_source = GLib.idle_add(self._do_reveal)

    def _do_rescan(self) -> bool:
        self._rescan_source = None
        self.rescan_all()
        return False

    def _do_reveal(self) -> bool:
        self._reveal_source = None
        try:
            self._apply_reveal()
        except Exception:
            _log.exception("markdown: reveal pass failed")
        return False

    # ---- tag application ----

    def _apply_all_tags(self) -> None:
        start, end = self._buffer.get_bounds()
        # Strip all our tags from the buffer before re-applying.
        for tag in self._tags.values():
            self._buffer.remove_tag(tag, start, end)
        if self._invisible is not None:
            self._buffer.remove_tag(self._invisible, start, end)
        if self._revealed is not None:
            self._buffer.remove_tag(self._revealed, start, end)

        for span in self._spans:
            style_tag = self._tags.get(span.kind)
            if style_tag is not None:
                s = self._buffer.get_iter_at_offset(span.start)
                e = self._buffer.get_iter_at_offset(span.end)
                self._buffer.apply_tag(style_tag, s, e)
            if self._invisible is not None:
                for mr_start, mr_end in span.marker_ranges:
                    s = self._buffer.get_iter_at_offset(mr_start)
                    e = self._buffer.get_iter_at_offset(mr_end)
                    self._buffer.apply_tag(self._invisible, s, e)

    def _apply_reveal(self) -> None:
        if self._revealed is None:
            return
        start, end = self._buffer.get_bounds()
        self._buffer.remove_tag(self._revealed, start, end)

        cursor_iter = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        cursor_offset = cursor_iter.get_offset()

        line_start_iter = cursor_iter.copy()
        line_start_iter.set_line_offset(0)
        line_end_iter = cursor_iter.copy()
        if not line_end_iter.ends_line():
            line_end_iter.forward_to_line_end()
        a_start = line_start_iter.get_offset()
        a_end = line_end_iter.get_offset()

        sel = self._buffer.get_selection_bounds()
        if sel:
            sel_start, sel_end = sel
            a_start = min(a_start, sel_start.get_offset())
            a_end = max(a_end, sel_end.get_offset())

        reveal = compute_reveal_set(self._spans, cursor_offset, (a_start, a_end))
        for mr_start, mr_end in reveal:
            s = self._buffer.get_iter_at_offset(mr_start)
            e = self._buffer.get_iter_at_offset(mr_end)
            self._buffer.apply_tag(self._revealed, s, e)

    # ---- helpers ----

    def _get_text(self) -> str:
        start, end = self._buffer.get_bounds()
        return self._buffer.get_text(start, end, True)

    def _build_tags(self) -> None:
        table = self._buffer.get_tag_table()

        def make(name: str, **props: object) -> Gtk.TextTag:
            tag_name = f"devpane-md-{name}"
            existing = table.lookup(tag_name)
            if existing is not None:
                return existing
            tag = Gtk.TextTag(name=tag_name)
            for k, v in props.items():
                tag.set_property(k.replace("_", "-"), v)
            table.add(tag)
            return tag

        bold = Pango.Weight.BOLD
        italic = Pango.Style.ITALIC
        self._tags[SpanKind.H1] = make("h1", scale=1.6, weight=bold)
        self._tags[SpanKind.H2] = make("h2", scale=1.4, weight=bold)
        self._tags[SpanKind.H3] = make("h3", scale=1.25, weight=bold)
        self._tags[SpanKind.H4] = make("h4", scale=1.15, weight=bold)
        self._tags[SpanKind.H5] = make("h5", scale=1.05, weight=bold)
        self._tags[SpanKind.H6] = make("h6", scale=1.0, weight=bold)
        self._tags[SpanKind.BOLD] = make("bold", weight=bold)
        self._tags[SpanKind.ITALIC] = make("italic", style=italic)
        self._tags[SpanKind.CODE_INLINE] = make("code-inline", family="monospace")
        self._tags[SpanKind.CODE_BLOCK] = make("code-block", family="monospace")
        self._tags[SpanKind.LINK] = make("link", underline=Pango.Underline.SINGLE)
        self._tags[SpanKind.QUOTE] = make("quote", style=italic)
        self._tags[SpanKind.HR] = make("hr", strikethrough=True)

        # Marker visibility tags. Add ``invisible-marker`` first so that
        # ``marker-revealed`` (added second) has higher priority and wins
        # where both apply.
        self._invisible = make("invisible-marker", invisible=True)
        self._revealed = make("marker-revealed", invisible=False)


def _rgba(r: float, g: float, b: float, a: float) -> Gdk.RGBA:
    c = Gdk.RGBA()
    c.red, c.green, c.blue, c.alpha = r, g, b, a
    return c


def _rgba_hex(hex_str: str) -> Gdk.RGBA:
    c = Gdk.RGBA()
    c.parse(hex_str)
    return c
