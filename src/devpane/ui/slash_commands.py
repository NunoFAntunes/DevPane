"""Slash-command popup for the markdown editor.

Typing ``/`` (at start-of-line or after whitespace) opens a popover
listing formatting commands (``/h1``, ``/list``, ``/bold``, ...). Selecting
one replaces the ``/word`` trigger with the corresponding markdown and
positions the cursor.

The implementation deliberately avoids ``GtkSource.Completion`` because
PyGObject's ``Gio.Task`` plumbing does not survive the C round-trip
through that interface (Bug #683599 + assertion failures on
``g_task_get_source_object``). A plain ``Gtk.Popover`` we drive
ourselves sidesteps both.

The pure helpers (``match``, ``find_trigger``, ``expand_insert``) are
free of any GTK dependency and are exercised by
``tests/test_slash_commands.py``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlashCommand:
    """One entry in the slash-command menu.

    ``insert`` is a template: ``{sel}`` is replaced by the current selection
    (or empty), and ``{cursor}`` marks where to place the caret after insertion.
    """

    trigger: str
    label: str
    description: str
    insert: str


COMMANDS: list[SlashCommand] = [
    SlashCommand("h1", "/h1", "Heading 1", "# {cursor}"),
    SlashCommand("h2", "/h2", "Heading 2", "## {cursor}"),
    SlashCommand("h3", "/h3", "Heading 3", "### {cursor}"),
    SlashCommand("h4", "/h4", "Heading 4", "#### {cursor}"),
    SlashCommand("h5", "/h5", "Heading 5", "##### {cursor}"),
    SlashCommand("h6", "/h6", "Heading 6", "###### {cursor}"),
    SlashCommand("list", "/list", "Bulleted list", "- {cursor}"),
    SlashCommand("numlist", "/numlist", "Numbered list", "1. {cursor}"),
    SlashCommand("todo", "/todo", "Task checkbox", "- [ ] {cursor}"),
    SlashCommand("quote", "/quote", "Blockquote", "> {cursor}"),
    SlashCommand("code", "/code", "Fenced code block", "```\n{cursor}\n```"),
    SlashCommand("hr", "/hr", "Horizontal rule", "\n---\n{cursor}"),
    SlashCommand("bold", "/bold", "Bold (wraps selection)", "**{sel}{cursor}**"),
    SlashCommand("italic", "/italic", "Italic (wraps selection)", "*{sel}{cursor}*"),
    SlashCommand("inlinecode", "/inlinecode", "Inline code (wraps selection)", "`{sel}{cursor}`"),
    SlashCommand("link", "/link", "Link (wraps selection as text)", "[{cursor}{sel}](url)"),
]


# A '/word' token at the cursor, bounded by start-of-string or whitespace.
_TRIGGER_RE = re.compile(r"(?:^|(?<=\s))/([a-z0-9]*)$")


def find_trigger(line_before_cursor: str) -> tuple[int, str] | None:
    """Return ``(slash_offset_in_line, word)`` if the cursor is inside a
    slash-command token, else ``None``.

    The slash must follow start-of-line or whitespace, so e.g. ``src/foo``
    does not trigger.
    """
    m = _TRIGGER_RE.search(line_before_cursor)
    if not m:
        return None
    return m.start(), m.group(1)


def match(query: str) -> list[SlashCommand]:
    """Return commands matching ``query`` (case-insensitive), prefix matches first."""
    q = query.lower()
    if not q:
        return list(COMMANDS)
    prefix = [c for c in COMMANDS if c.trigger.startswith(q)]
    substring = [c for c in COMMANDS if q in c.trigger and not c.trigger.startswith(q)]
    return prefix + substring


def expand_insert(template: str, selection: str = "") -> tuple[str, int]:
    """Render ``template`` by substituting ``{sel}`` and ``{cursor}``.

    Returns ``(rendered_text, cursor_offset_from_start)``. If ``{cursor}``
    is absent the caret lands at the end.
    """
    text = template.replace("{sel}", selection)
    cursor_pos = text.find("{cursor}")
    if cursor_pos < 0:
        return text, len(text)
    return text.replace("{cursor}", "", 1), cursor_pos


# ---- GTK integration ----


class SlashMenu:
    """A self-contained slash-command popover attached to a text view.

    Installs its own signal handlers on the buffer and view. Owners only
    need to construct it (``SlashMenu(view)``) and let it live for the
    lifetime of the view.
    """

    def __init__(self, view: Gtk.TextView) -> None:
        self._view = view
        self._buffer = view.get_buffer()
        self._matches: list[SlashCommand] = []
        # While True, our buffer mutations should not re-trigger the menu.
        self._mutating = False
        # Set when the popover is open. Anchored at the '/' that opened it.
        self._trigger_mark: Gtk.TextMark | None = None

        self._popover = Gtk.Popover()
        self._popover.set_parent(view)
        self._popover.set_autohide(False)
        self._popover.set_has_arrow(False)
        self._popover.set_position(Gtk.PositionType.BOTTOM)
        self._popover.add_css_class("devpane-slash-popover")

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self._listbox.add_css_class("devpane-slash-list")
        self._listbox.connect("row-activated", self._on_row_activated)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_width(260)
        scrolled.set_max_content_height(280)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_child(self._listbox)
        self._popover.set_child(scrolled)

        # Detect '/' typed in the buffer.
        self._buffer.connect_after("insert-text", self._on_after_insert)
        self._buffer.connect_after("delete-range", self._on_after_delete)

        # Capture nav keys while open so they don't reach the buffer.
        kc = Gtk.EventControllerKey()
        kc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        kc.connect("key-pressed", self._on_key_pressed)
        view.add_controller(kc)

    # ---- buffer signals ----

    def _on_after_insert(self, _buffer, location, text, _length) -> None:
        if self._mutating:
            return
        if self._trigger_mark is not None:
            self._refresh_query()
            return
        if text != "/":
            return
        # ``location`` is positioned just AFTER the inserted '/'. Check the
        # char before the '/' for a valid trigger boundary.
        insert_iter = location.copy()
        slash_iter = insert_iter.copy()
        slash_iter.backward_char()
        if not slash_iter.is_start():
            before = slash_iter.copy()
            before.backward_char()
            if before.get_char() not in (" ", "\t", "\n", "\r"):
                return
        self._open(slash_iter)

    def _on_after_delete(self, _buffer, _start, _end) -> None:
        if self._mutating or self._trigger_mark is None:
            return
        self._refresh_query()

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state) -> bool:
        if self._trigger_mark is None:
            return False
        if keyval == Gdk.KEY_Escape:
            self._close()
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self._move(+1)
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_ISO_Left_Tab):
            self._move(-1)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._accept()
            return True
        return False

    # ---- popover lifecycle ----

    def _open(self, slash_iter: Gtk.TextIter) -> None:
        self._trigger_mark = self._buffer.create_mark(None, slash_iter, True)
        self._populate("")
        self._anchor_to_cursor()
        self._popover.popup()

    def _close(self) -> None:
        if self._trigger_mark is not None:
            self._buffer.delete_mark(self._trigger_mark)
            self._trigger_mark = None
        self._popover.popdown()

    def _refresh_query(self) -> None:
        """Update the visible list based on the text between '/' and the cursor."""
        if self._trigger_mark is None:
            return
        slash_iter = self._buffer.get_iter_at_mark(self._trigger_mark)
        cursor_iter = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        if cursor_iter.compare(slash_iter) < 0:
            # Cursor moved before the slash — bail.
            self._close()
            return
        word = self._buffer.get_text(slash_iter, cursor_iter, False)
        if not word.startswith("/"):
            self._close()
            return
        query = word[1:]
        if not re.fullmatch(r"[a-zA-Z0-9]*", query):
            self._close()
            return
        self._populate(query)
        if not self._matches:
            # Keep open with an empty state, or close — closing feels better.
            self._close()

    def _populate(self, query: str) -> None:
        self._matches = match(query)
        # Clear existing rows.
        while True:
            row = self._listbox.get_row_at_index(0)
            if row is None:
                break
            self._listbox.remove(row)
        for cmd in self._matches:
            self._listbox.append(_build_row(cmd))
        if self._matches:
            first = self._listbox.get_row_at_index(0)
            if first is not None:
                self._listbox.select_row(first)

    def _anchor_to_cursor(self) -> None:
        if self._trigger_mark is None:
            return
        slash_iter = self._buffer.get_iter_at_mark(self._trigger_mark)
        rect = self._view.get_iter_location(slash_iter)
        bx, by = self._view.buffer_to_window_coords(
            Gtk.TextWindowType.WIDGET, rect.x, rect.y + rect.height
        )
        anchor = Gdk.Rectangle()
        anchor.x = bx
        anchor.y = by
        anchor.width = 1
        anchor.height = 1
        self._popover.set_pointing_to(anchor)

    def _move(self, delta: int) -> None:
        row = self._listbox.get_selected_row()
        if row is None:
            return
        idx = row.get_index() + delta
        total = len(self._matches)
        if total == 0:
            return
        idx %= total
        target = self._listbox.get_row_at_index(idx)
        if target is not None:
            self._listbox.select_row(target)

    def _accept(self) -> None:
        row = self._listbox.get_selected_row()
        if row is None:
            self._close()
            return
        idx = row.get_index()
        if not (0 <= idx < len(self._matches)):
            self._close()
            return
        self._apply_command(self._matches[idx])

    def _on_row_activated(self, _listbox, row: Gtk.ListBoxRow) -> None:
        idx = row.get_index()
        if 0 <= idx < len(self._matches):
            self._apply_command(self._matches[idx])

    # ---- command execution ----

    def _apply_command(self, cmd: SlashCommand) -> None:
        if self._trigger_mark is None:
            return
        slash_iter = self._buffer.get_iter_at_mark(self._trigger_mark)
        cursor_iter = self._buffer.get_iter_at_mark(self._buffer.get_insert())

        bounds = self._buffer.get_selection_bounds()
        has_sel = bool(bounds)
        selection_text = ""
        if has_sel:
            sel_start, sel_end = bounds
            selection_text = self._buffer.get_text(sel_start, sel_end, False)

        text, cursor_offset = expand_insert(cmd.insert, selection_text)

        self._mutating = True
        try:
            self._buffer.begin_user_action()
            try:
                self._buffer.delete(slash_iter, cursor_iter)
                if has_sel:
                    s = self._buffer.get_iter_at_mark(self._buffer.get_selection_bound())
                    e = self._buffer.get_iter_at_mark(self._buffer.get_insert())
                    if not s.equal(e):
                        self._buffer.delete(s, e)
                insert_iter = self._buffer.get_iter_at_mark(self._buffer.get_insert())
                insert_pos = insert_iter.get_offset()
                self._buffer.insert(insert_iter, text)
                new_cursor = self._buffer.get_iter_at_offset(insert_pos + cursor_offset)
                self._buffer.place_cursor(new_cursor)
            finally:
                self._buffer.end_user_action()
        finally:
            self._mutating = False
            # Defer close so the focus-grab dance doesn't race buffer signals.
            GLib.idle_add(self._close_idle)

    def _close_idle(self) -> bool:
        self._close()
        return False


def _build_row(cmd: SlashCommand) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    row.add_css_class("devpane-slash-row")
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_margin_top(4)
    box.set_margin_bottom(4)
    box.set_margin_start(8)
    box.set_margin_end(8)
    name = Gtk.Label(label=cmd.label, xalign=0)
    name.add_css_class("devpane-slash-name")
    desc = Gtk.Label(label=cmd.description, xalign=0)
    desc.add_css_class("devpane-slash-desc")
    desc.add_css_class("dim-label")
    desc.set_hexpand(True)
    desc.set_halign(Gtk.Align.END)
    box.append(name)
    box.append(desc)
    row.set_child(box)
    return row
