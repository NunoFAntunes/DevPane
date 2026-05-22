"""Sprint navigation bar — sits above the task list.

Shows the current sprint's display name flanked by previous/next arrow
buttons. Clicking the name opens a rename dialog. Arrows are disabled at
the chronological ends — the model is "sprints exist iff a task
references them", so there's nothing to navigate to past the edges.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from devpane.store.sprints import Sprint  # noqa: E402

_log = logging.getLogger(__name__)


class SprintBar:
    """``< Sprint name >`` strip. Use ``.widget`` to embed."""

    def __init__(
        self,
        on_prev: Callable[[], None],
        on_next: Callable[[], None],
        on_rename: Callable[[str, str], None],
    ) -> None:
        self._on_prev = on_prev
        self._on_next = on_next
        self._on_rename = on_rename
        self._sprints: list[Sprint] = []
        self._current_id: str | None = None

        self.widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.widget.add_css_class("sprint-bar")

        self._prev_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._prev_btn.set_tooltip_text("Previous sprint (Alt+Left)")
        self._prev_btn.add_css_class("flat")
        self._prev_btn.connect("clicked", lambda _b: self._on_prev())
        self.widget.append(self._prev_btn)

        self._name_btn = Gtk.Button()
        self._name_btn.set_hexpand(True)
        self._name_btn.add_css_class("flat")
        self._name_btn.add_css_class("sprint-name")
        self._name_btn.set_tooltip_text("Click to rename sprint")
        self._name_btn.connect("clicked", lambda _b: self._open_rename())
        self.widget.append(self._name_btn)

        self._next_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self._next_btn.set_tooltip_text("Next sprint (Alt+Right)")
        self._next_btn.add_css_class("flat")
        self._next_btn.connect("clicked", lambda _b: self._on_next())
        self.widget.append(self._next_btn)

        self._render_empty()

    # ---- public API ----------------------------------------------------

    def set_state(self, sprints: list[Sprint], current_id: str | None) -> None:
        """Replace the navigable sprints and the highlighted current id."""
        self._sprints = sprints
        self._current_id = current_id
        if not sprints or current_id is None:
            self._render_empty()
            return
        idx = next((i for i, s in enumerate(sprints) if s.id == current_id), -1)
        if idx < 0:
            self._render_empty()
            return
        current = sprints[idx]
        self._name_btn.set_label(current.name)
        self._name_btn.set_sensitive(True)
        self._prev_btn.set_sensitive(idx > 0)
        self._next_btn.set_sensitive(idx + 1 < len(sprints))

    @property
    def current_id(self) -> str | None:
        return self._current_id

    # ---- internals -----------------------------------------------------

    def _render_empty(self) -> None:
        self._name_btn.set_label("No sprints")
        self._name_btn.set_sensitive(False)
        self._prev_btn.set_sensitive(False)
        self._next_btn.set_sensitive(False)

    def _open_rename(self) -> None:
        if self._current_id is None:
            return
        sid = self._current_id
        current = next((s for s in self._sprints if s.id == sid), None)
        if current is None:
            return

        dialog = Adw.AlertDialog.new("Rename sprint", None)
        entry = Gtk.Entry()
        entry.set_text(current.name)
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Rename")
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def _on_response(_d: Adw.AlertDialog, response: str) -> None:
            if response != "ok":
                return
            self._on_rename(sid, entry.get_text())

        dialog.connect("response", _on_response)
        parent = self.widget.get_root()
        dialog.present(parent)
