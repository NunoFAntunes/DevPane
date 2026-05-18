"""Pane header — current note title, new-note button, switcher popover.

``Adw.HeaderBar`` is final in libadwaita, so this class wraps one via
composition rather than inheriting. Access the underlying widget through
``.widget`` to add it to a container.

The note list shown in the switcher popover is read lazily from the store
each time the popover opens — no caching, no stale state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from devpane.store import notes  # noqa: E402

_log = logging.getLogger(__name__)


class PaneHeader:
    def __init__(
        self,
        on_new: Callable[[], None],
        on_switch_to: Callable[[str], None],
    ) -> None:
        self.widget = Adw.HeaderBar()
        self.widget.set_show_end_title_buttons(False)
        self.widget.set_show_start_title_buttons(False)

        self._title = Adw.WindowTitle.new("DevPane", "")
        self.widget.set_title_widget(self._title)

        new_btn = Gtk.Button.new_from_icon_name("document-new-symbolic")
        new_btn.set_tooltip_text("New note (Ctrl+N)")
        new_btn.connect("clicked", lambda _btn: on_new())
        self.widget.pack_start(new_btn)

        self._on_switch_to = on_switch_to
        self._switcher_btn = Gtk.MenuButton()
        self._switcher_btn.set_icon_name("view-list-symbolic")
        self._switcher_btn.set_tooltip_text("Switch note (Ctrl+K)")
        self._popover = Gtk.Popover()
        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("navigation-sidebar")
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.connect("row-activated", self._on_row_activated)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self._listbox)
        scrolled.set_min_content_width(240)
        scrolled.set_min_content_height(240)
        scrolled.set_propagate_natural_height(True)
        self._popover.set_child(scrolled)
        self._popover.connect("show", lambda _p: self._refresh_list())
        self._switcher_btn.set_popover(self._popover)
        self.widget.pack_end(self._switcher_btn)

    def set_current_note(self, name: str) -> None:
        self._title.set_subtitle(name)

    def open_switcher(self) -> None:
        self._switcher_btn.activate()

    def _refresh_list(self) -> None:
        while True:
            row = self._listbox.get_first_child()
            if row is None:
                break
            self._listbox.remove(row)
        for name in notes.list_notes():
            row = Gtk.ListBoxRow()
            row.set_child(
                Gtk.Label(
                    label=name,
                    xalign=0,
                    margin_top=6,
                    margin_bottom=6,
                    margin_start=12,
                    margin_end=12,
                )
            )
            row.set_name(name)
            self._listbox.append(row)

    def _on_row_activated(self, _box: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        name = row.get_name()
        if name:
            self._popover.popdown()
            self._on_switch_to(name)
