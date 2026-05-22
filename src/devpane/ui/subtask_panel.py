"""Subtask panel — middle column of the pane.

Owned by a single task at a time. Each row has:

- a checkbox (done state)
- a click-to-edit ``GtkEditableLabel`` for the subtask text
- a hover-visible delete button on the right
- drag-and-drop reordering within this task (the drop target accepts a
  source-row index expressed as a ``GObject.Value(int)``)

Every mutation rewrites the JSON sidecar atomically via
:mod:`devpane.store.subtasks`. The whole panel reloads from disk on
:meth:`load_for` so external edits are picked up.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from devpane.store import subtasks  # noqa: E402
from devpane.store.subtasks import Subtask  # noqa: E402

_log = logging.getLogger(__name__)


class SubtaskRow(Gtk.ListBoxRow):  # type: ignore[misc]
    """One subtask: checkbox + editable label + (hover) delete button."""

    def __init__(
        self,
        index: int,
        item: Subtask,
        on_toggle: Callable[[int, bool], None],
        on_text_commit: Callable[[int, str], None],
        on_delete: Callable[[int], None],
        on_drop: Callable[[int, int, bool], None],
    ) -> None:
        super().__init__()
        self._index = index
        self.add_css_class("subtask-row")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(6)
        box.set_margin_end(6)
        box.set_margin_top(2)
        box.set_margin_bottom(2)

        self._check = Gtk.CheckButton()
        self._check.set_active(item.done)
        self._check.set_focus_on_click(False)
        self._check.connect("toggled", lambda b: on_toggle(self._index, b.get_active()))
        box.append(self._check)

        self._label = Gtk.EditableLabel()
        self._label.set_text(item.text)
        self._label.set_hexpand(True)
        # EditableLabel collapses to zero width when its text is empty.
        # That makes a freshly-added subtask invisible until first commit,
        # so the row stays clickable to enter edit mode and the parent
        # panel calls ``start_editing()`` after the row is mapped.
        self._label.set_size_request(80, -1)
        # On transition out of editing, commit (empty text → row deletion,
        # handled by the panel's commit callback).
        self._label.connect("notify::editing", self._on_editing_changed, on_text_commit)
        box.append(self._label)

        self._delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        self._delete_btn.add_css_class("flat")
        self._delete_btn.add_css_class("delete-btn")
        self._delete_btn.set_tooltip_text("Delete subtask")
        self._delete_btn.connect("clicked", lambda _b: on_delete(self._index))
        box.append(self._delete_btn)

        self.set_child(box)
        if item.done:
            self.add_css_class("subtask-done")

        self._install_dnd(on_drop)

    @property
    def index(self) -> int:
        return self._index

    def start_editing(self) -> None:
        self._label.start_editing()

    def _on_editing_changed(
        self,
        label: Gtk.EditableLabel,
        _pspec: object,
        on_text_commit: Callable[[int, str], None],
    ) -> None:
        if label.get_property("editing"):
            return
        on_text_commit(self._index, label.get_text().strip())

    # ---- drag and drop -------------------------------------------------

    def _install_dnd(self, on_drop: Callable[[int, int, bool], None]) -> None:
        # Source: ship our index as an int payload.
        src = Gtk.DragSource()
        src.set_actions(Gdk.DragAction.MOVE)

        def _prepare(_source: Gtk.DragSource, _x: float, _y: float) -> Gdk.ContentProvider:
            value = GObject.Value(int, self._index)
            return Gdk.ContentProvider.new_for_value(value)

        def _drag_begin(_source: Gtk.DragSource, _drag: Gdk.Drag) -> None:
            self.add_css_class("dragging")

        def _drag_end(_source: Gtk.DragSource, _drag: Gdk.Drag, _del: bool) -> None:
            self.remove_css_class("dragging")

        src.connect("prepare", _prepare)
        src.connect("drag-begin", _drag_begin)
        src.connect("drag-end", _drag_end)
        self.add_controller(src)

        # Target: accept ints, decide "before" / "after" by drop y-coord.
        dst = Gtk.DropTarget.new(int, Gdk.DragAction.MOVE)

        def _on_enter(_t: Gtk.DropTarget, _x: float, y: float) -> Gdk.DragAction:
            self._update_drop_indicator(y)
            return Gdk.DragAction.MOVE

        def _on_motion(_t: Gtk.DropTarget, _x: float, y: float) -> Gdk.DragAction:
            self._update_drop_indicator(y)
            return Gdk.DragAction.MOVE

        def _on_leave(_t: Gtk.DropTarget) -> None:
            self.remove_css_class("drop-above")
            self.remove_css_class("drop-below")

        def _on_drop(_t: Gtk.DropTarget, value: int, _x: float, y: float) -> bool:
            self.remove_css_class("drop-above")
            self.remove_css_class("drop-below")
            below = y > self.get_height() / 2
            on_drop(int(value), self._index, below)
            return True

        dst.connect("enter", _on_enter)
        dst.connect("motion", _on_motion)
        dst.connect("leave", _on_leave)
        dst.connect("drop", _on_drop)
        self.add_controller(dst)

    def _update_drop_indicator(self, y: float) -> None:
        if y < self.get_height() / 2:
            self.add_css_class("drop-above")
            self.remove_css_class("drop-below")
        else:
            self.add_css_class("drop-below")
            self.remove_css_class("drop-above")


class SubtaskPanel:
    """Middle pane. Use ``.widget`` to embed."""

    def __init__(self, on_changed: Callable[[], None] | None = None) -> None:
        # ``on_changed`` fires after any subtask mutation so the parent task's
        # progress indicator can update.
        self._on_changed = on_changed
        self._task_name: str | None = None
        self._items: list[Subtask] = []

        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.widget.add_css_class("subtask-panel")

        # --- header -----------------------------------------------------
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.add_css_class("subtask-header")
        title = Gtk.Label(label="Subtasks", xalign=0)
        title.add_css_class("heading")
        title.set_hexpand(True)
        header.append(title)
        self._add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        self._add_btn.add_css_class("flat")
        self._add_btn.set_tooltip_text("Add subtask")
        self._add_btn.connect("clicked", lambda _b: self._add())
        header.append(self._add_btn)
        self.widget.append(header)

        # --- list -------------------------------------------------------
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.add_css_class("subtask-list")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self._listbox)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        self.widget.append(scrolled)

        # --- empty-state placeholder -----------------------------------
        self._placeholder = Gtk.Label(label="No subtasks yet — click + to add")
        self._placeholder.add_css_class("dim-label")
        self._placeholder.set_wrap(True)
        self._placeholder.set_margin_top(12)
        self._placeholder.set_margin_bottom(12)
        self._placeholder.set_margin_start(12)
        self._placeholder.set_margin_end(12)
        self._listbox.set_placeholder(self._placeholder)

        self._set_enabled(False)

    # ---- public API ----------------------------------------------------

    def load_for(self, task_name: str | None) -> None:
        """Switch to ``task_name``'s subtasks (or clear if ``None``)."""
        self._task_name = task_name
        if task_name is None:
            self._items = []
            self._set_enabled(False)
        else:
            self._items = subtasks.load(task_name)
            self._set_enabled(True)
        self._rebuild()

    # ---- internals -----------------------------------------------------

    def _set_enabled(self, enabled: bool) -> None:
        self._add_btn.set_sensitive(enabled)

    def _rebuild(self) -> None:
        while True:
            child = self._listbox.get_first_child()
            if child is None:
                break
            self._listbox.remove(child)
        for i, item in enumerate(self._items):
            row = SubtaskRow(
                index=i,
                item=item,
                on_toggle=self._on_toggle,
                on_text_commit=self._on_text_commit,
                on_delete=self._on_delete,
                on_drop=self._on_drop,
            )
            self._listbox.append(row)

    def _persist(self) -> None:
        if self._task_name is None:
            return
        try:
            subtasks.save(self._task_name, self._items)
        except OSError as e:
            _log.warning("subtasks: save failed (%s)", e)
            return
        if self._on_changed is not None:
            self._on_changed()

    def _add(self) -> None:
        if self._task_name is None:
            return
        self._items.append(Subtask(text="", done=False))
        new_index = len(self._items) - 1
        # Don't persist yet — empty rows are discarded if the user doesn't
        # type anything. Just render and put focus into the new row.
        self._rebuild()
        row = self._row_at(new_index)
        if row is None:
            return
        # ``start_editing()`` needs the widget realized + mapped to grab
        # focus reliably; hooking the row's ``map`` signal is more
        # robust than an idle callback.
        if row.get_mapped():
            row.start_editing()
        else:
            handler_id: list[int] = []

            def _once(_w: Gtk.Widget) -> None:
                row.start_editing()
                row.disconnect(handler_id[0])

            handler_id.append(row.connect("map", _once))

    def _row_at(self, index: int) -> SubtaskRow | None:
        child = self._listbox.get_first_child()
        i = 0
        while child is not None:
            if isinstance(child, SubtaskRow):
                if i == index:
                    return child
                i += 1
            child = child.get_next_sibling()
        return None

    def _on_toggle(self, index: int, done: bool) -> None:
        if 0 <= index < len(self._items):
            self._items[index].done = done
            self._persist()
            self._rebuild()

    def _on_text_commit(self, index: int, text: str) -> None:
        if not (0 <= index < len(self._items)):
            return
        if not text:
            # Empty after edit → remove row (handles both new-empty rows
            # the user abandoned and existing rows the user blanked out).
            del self._items[index]
            self._persist()
            self._rebuild()
            return
        if self._items[index].text == text:
            return
        self._items[index].text = text
        self._persist()

    def _on_delete(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            self._persist()
            self._rebuild()

    def _on_drop(self, src_index: int, dst_index: int, below: bool) -> None:
        if src_index == dst_index:
            return
        if not (0 <= src_index < len(self._items)):
            return
        if not (0 <= dst_index < len(self._items)):
            return
        # Compute insertion index in the original list, then pop+insert.
        insert_at = dst_index + 1 if below else dst_index
        if src_index < insert_at:
            insert_at -= 1
        if src_index == insert_at:
            return
        item = self._items.pop(src_index)
        self._items.insert(insert_at, item)
        self._persist()
        self._rebuild()
