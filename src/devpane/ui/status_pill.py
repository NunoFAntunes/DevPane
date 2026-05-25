"""StatusPill — a small dropdown that displays and changes a task's status.

Shows a coloured dot + short label (``todo``/``doing``/``blocked``/``done``).
Clicking opens a popover with one button per status. The widget emits a
``status-changed`` signal carrying the new status string; the row connects
this and writes the change to disk.

Status colours are driven by CSS classes (``status-todo`` / ``status-doing``
/ ``status-blocked`` / ``status-done``) defined in ``styles.css`` so the
look matches the user's libadwaita theme.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GObject, Gtk  # noqa: E402

from devpane.store import notes  # noqa: E402

_LABELS: dict[str, str] = {
    notes.STATUS_TODO: "Todo",
    notes.STATUS_DOING: "Doing",
    notes.STATUS_BLOCKED: "Blocked",
    notes.STATUS_DONE: "Done",
}


class StatusPill(Gtk.MenuButton):  # type: ignore[misc]
    """Pill-shaped status indicator + picker. ``status-changed`` carries str."""

    __gsignals__: ClassVar[dict[str, tuple[object, ...]]] = {
        "status-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, status: str) -> None:
        super().__init__()
        self._status = status if status in notes.STATUSES else notes.STATUS_TODO
        self.add_css_class("status-pill")
        self.add_css_class("flat")
        self.set_focus_on_click(False)

        self._label = Gtk.Label(label=_LABELS[self._status])
        self._label.add_css_class("status-pill-label")
        self.set_child(self._label)
        self._apply_status_class(self._status)

        popover = Gtk.Popover()
        popover.set_has_arrow(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.add_css_class("status-pill-menu")
        for s in notes.STATUSES:
            btn = Gtk.Button(label=_LABELS[s])
            btn.add_css_class("flat")
            btn.add_css_class(f"status-{s}")
            btn.connect("clicked", self._make_pick(s, popover))
            box.append(btn)
        popover.set_child(box)
        self.set_popover(popover)

    @property
    def status(self) -> str:
        return self._status

    def set_status(self, status: str) -> None:
        if status not in notes.STATUSES or status == self._status:
            return
        self._apply_status_class(status)
        self._status = status
        self._label.set_label(_LABELS[status])

    def _apply_status_class(self, status: str) -> None:
        for s in notes.STATUSES:
            self.remove_css_class(f"status-{s}")
        self.add_css_class(f"status-{status}")

    def _make_pick(self, new_status: str, popover: Gtk.Popover) -> Callable[[Gtk.Button], None]:
        def _pick(_btn: Gtk.Button) -> None:
            popover.popdown()
            if new_status == self._status:
                return
            self.set_status(new_status)
            self.emit("status-changed", new_status)

        return _pick
