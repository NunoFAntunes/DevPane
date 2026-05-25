"""Task list sidebar — replaces the old header switcher popover.

Each task is one note file. The row shows a status pill (todo / doing /
blocked / done, stored in the note's frontmatter), a title (``meta['title']``
or filename stem), and optional tag chips. Selecting a row opens its notes
file in the editor. Right-click opens a context menu with Rename / Delete.

The store is the source of truth: every mutation calls back into
``devpane.store.notes`` and then ``refresh()`` re-reads from disk.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from devpane.store import notes, subtasks  # noqa: E402
from devpane.ui.status_pill import StatusPill  # noqa: E402

_log = logging.getLogger(__name__)

# Sort order within a sprint: doing first, then todo, then blocked, then
# done. Done sinks to the bottom — same intent as the old (done, -mtime)
# tuple, just with finer-grained buckets for in-flight work.
_STATUS_ORDER: dict[str, int] = {
    notes.STATUS_DOING: 0,
    notes.STATUS_TODO: 1,
    notes.STATUS_BLOCKED: 2,
    notes.STATUS_DONE: 3,
}

# Cap how many tag chips render inline before we collapse the tail into
# a single ``+N`` chip. Avoids wrapping wide tag lists into the row.
_MAX_TAG_CHIPS = 3

_ALL_TAGS_LABEL = "All tags"


class TaskRow(Gtk.ListBoxRow):  # type: ignore[misc]
    """One task: status pill + title + tag chips. Carries its note filename."""

    def __init__(
        self,
        name: str,
        title: str,
        status: str,
        tags: list[str],
        progress: tuple[int, int],
        on_status: Callable[[str, str], None],
        on_context: Callable[[str, TaskRow, float, float], None],
    ) -> None:
        super().__init__()
        self._name = name
        self._on_status = on_status
        self.add_css_class("task-row")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(2)
        box.set_margin_bottom(2)

        self._pill = StatusPill(status)
        self._pill.connect("status-changed", self._on_pill_changed)
        box.append(self._pill)

        self._label = Gtk.Label(label=title, xalign=0)
        self._label.set_hexpand(True)
        self._label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        box.append(self._label)

        if tags:
            chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            chips.add_css_class("task-tags")
            for tag in tags[:_MAX_TAG_CHIPS]:
                chips.append(_make_tag_chip(tag))
            overflow = len(tags) - _MAX_TAG_CHIPS
            if overflow > 0:
                chips.append(_make_tag_chip(f"+{overflow}"))
            box.append(chips)

        done_count, total = progress
        if total > 0:
            progress_label = Gtk.Label(label=f"{done_count}/{total}")
            progress_label.add_css_class("dim-label")
            progress_label.add_css_class("task-progress")
            box.append(progress_label)

        self.set_child(box)
        if status == notes.STATUS_DONE:
            self.add_css_class("task-done")

        # Right-click context menu.
        gesture = Gtk.GestureClick()
        gesture.set_button(Gdk.BUTTON_SECONDARY)
        gesture.connect("pressed", lambda _g, _n, x, y: on_context(self._name, self, x, y))
        self.add_controller(gesture)

    @property
    def name(self) -> str:
        return self._name

    def _on_pill_changed(self, _pill: StatusPill, status: str) -> None:
        self._on_status(self._name, status)


def _make_tag_chip(text: str) -> Gtk.Widget:
    label = Gtk.Label(label=text)
    label.add_css_class("task-tag")
    return label


class TaskList:
    """Sidebar widget. Use ``.widget`` to embed it."""

    def __init__(
        self,
        on_select: Callable[[str], None],
        on_new: Callable[[], None],
        on_delete: Callable[[str], None],
        on_migrate_next: Callable[[str], None],
        on_migrate_prev: Callable[[str], None],
        show_completed: bool,
        tag_filter: str | None = None,
        on_task_changed: Callable[[], None] | None = None,
    ) -> None:
        self._on_select = on_select
        self._on_new = on_new
        self._on_delete = on_delete
        self._on_migrate_next = on_migrate_next
        self._on_migrate_prev = on_migrate_prev
        self._show_completed = show_completed
        self._tag_filter = tag_filter
        self._on_task_changed = on_task_changed
        self._suppress_select = False
        self._current: str | None = None
        self._current_sprint: str | None = None
        self._can_migrate_prev: bool = False
        # Tag dropdown is rebuilt on every refresh from the union of tags
        # in the visible sprint; suppress the resulting ``notify::selected``
        # signal so the rebuild itself doesn't trigger a filter change.
        self._suppress_tag_signal = False
        self._tag_options: list[str] = []

        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.widget.add_css_class("task-list")

        # --- header -----------------------------------------------------
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.add_css_class("task-list-header")
        title = Gtk.Label(label="Tasks", xalign=0)
        title.set_hexpand(True)
        title.add_css_class("heading")
        header.append(title)
        new_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        new_btn.set_tooltip_text("New task (Ctrl+N)")
        new_btn.add_css_class("flat")
        new_btn.connect("clicked", lambda _b: self._on_new())
        header.append(new_btn)
        self.widget.append(header)

        # --- list -------------------------------------------------------
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._listbox.add_css_class("navigation-sidebar")
        self._listbox.connect("row-selected", self._on_row_selected)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self._listbox)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        self.widget.append(scrolled)

        # --- footer: tag filter + show-completed switch -----------------
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        footer.add_css_class("task-list-footer")

        tag_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tag_label = Gtk.Label(label="Tag", xalign=0)
        tag_row.append(tag_label)
        self._tag_dropdown = Gtk.DropDown.new_from_strings([_ALL_TAGS_LABEL])
        self._tag_dropdown.set_hexpand(True)
        self._tag_dropdown.connect("notify::selected", self._on_tag_filter_changed)
        tag_row.append(self._tag_dropdown)
        footer.append(tag_row)

        switch_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer_label = Gtk.Label(label="Show completed", xalign=0)
        footer_label.set_hexpand(True)
        switch_row.append(footer_label)
        self._show_switch = Gtk.Switch()
        self._show_switch.set_active(self._show_completed)
        self._show_switch.connect("notify::active", self._on_show_completed_changed)
        switch_row.append(self._show_switch)
        footer.append(switch_row)
        self.widget.append(footer)

        # --- context menu (single popover, repositioned per row) --------
        self._menu_target: str | None = None
        self._menu = Gtk.PopoverMenu.new_from_model(self._build_menu_model())
        self._menu.set_has_arrow(False)
        self._install_actions()

    # ---- public API ----------------------------------------------------

    def refresh(self) -> None:
        """Re-read tasks from disk and rebuild the list."""
        current = self._current
        self._clear_listbox()
        # We need two passes through the sprint's tasks: one to collect
        # every tag (so the dropdown lists tags even on rows the active
        # filter is currently hiding), and one to materialise the rows.
        sprint_tasks: list[tuple[str, dict[str, str], list[str], str, float]] = []
        tag_universe: set[str] = set()
        for name in notes.list_notes():
            try:
                meta, _ = notes.read_task(name)
            except (OSError, notes.InvalidNoteName) as e:
                _log.warning("task-list: skipping %s (%s)", name, e)
                continue
            sprint = meta.get("sprint", "").strip() or None
            if self._current_sprint is not None and sprint != self._current_sprint:
                continue
            tags = notes.parse_tags(meta.get("tags", ""))
            tag_universe.update(tags)
            status = notes.status_from_meta(meta)
            try:
                mt = notes.mtime(name)
            except OSError:
                mt = 0.0
            sprint_tasks.append((name, meta, tags, status, mt))

        self._rebuild_tag_dropdown(sorted(tag_universe))

        rows: list[tuple[int, float, str, str, str, list[str]]] = []
        for name, meta, tags, status, mt in sprint_tasks:
            if status == notes.STATUS_DONE and not self._show_completed:
                continue
            if self._tag_filter is not None and self._tag_filter not in tags:
                continue
            title = meta.get("title", "").strip() or name[:-3]
            rows.append((_STATUS_ORDER[status], -mt, title, name, status, tags))

        rows.sort(key=lambda r: (r[0], r[1]))

        for _order, _neg_mt, title, name, status, tags in rows:
            try:
                prog = subtasks.progress(name)
            except OSError:
                prog = (0, 0)
            row = TaskRow(
                name=name,
                title=title,
                status=status,
                tags=tags,
                progress=prog,
                on_status=self._on_status_changed,
                on_context=self._open_context_menu,
            )
            self._listbox.append(row)

        if current is not None:
            self.select(current)

    def select(self, name: str) -> None:
        """Programmatically highlight ``name`` (no echo to on_select)."""
        canon = notes.canonical_name(name)
        target = self._find_row(canon)
        self._current = canon
        if target is None:
            return
        self._suppress_select = True
        try:
            self._listbox.select_row(target)
        finally:
            self._suppress_select = False

    @property
    def show_completed(self) -> bool:
        return self._show_completed

    def set_sprint(self, sprint_id: str | None, can_migrate_prev: bool) -> None:
        """Filter the list to ``sprint_id`` and refresh.

        ``can_migrate_prev`` controls whether the "Move to previous
        sprint" context menu item is enabled (the window knows whether
        an earlier sprint exists).
        """
        self._current_sprint = sprint_id
        self._can_migrate_prev = can_migrate_prev
        self.refresh()

    def visible_names(self) -> list[str]:
        """Names of tasks currently shown (post sprint + completed filter)."""
        out: list[str] = []
        child = self._listbox.get_first_child()
        while child is not None:
            if isinstance(child, TaskRow):
                out.append(child.name)
            child = child.get_next_sibling()
        return out

    def set_show_completed(self, value: bool) -> None:
        if value == self._show_completed:
            return
        self._show_completed = value
        if self._show_switch.get_active() != value:
            self._show_switch.set_active(value)
        self.refresh()

    @property
    def tag_filter(self) -> str | None:
        return self._tag_filter

    def set_tag_filter(self, value: str | None) -> None:
        v = (value or "").strip().lower() or None
        if v == self._tag_filter:
            return
        self._tag_filter = v
        self.refresh()

    # ---- internals -----------------------------------------------------

    def _clear_listbox(self) -> None:
        while True:
            child = self._listbox.get_first_child()
            if child is None:
                break
            self._listbox.remove(child)

    def _find_row(self, name: str) -> TaskRow | None:
        child = self._listbox.get_first_child()
        while child is not None:
            if isinstance(child, TaskRow) and child.name == name:
                return child
            child = child.get_next_sibling()
        return None

    def _on_row_selected(self, _box: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if self._suppress_select or row is None:
            return
        if isinstance(row, TaskRow):
            self._current = row.name
            self._on_select(row.name)

    def _on_status_changed(self, name: str, status: str) -> None:
        try:
            notes.set_status(name, status)
        except (OSError, ValueError) as e:
            _log.warning("task-list: set_status %s failed (%s)", name, e)
            return
        # A status change may move the row across the sort buckets, hide
        # it (done + hide-completed), and updates the sprint counts in the
        # sprint bar. Defer both to idle so the popover closes cleanly first.
        GLib.idle_add(self._notify_task_changed_idle)

    def _notify_task_changed_idle(self) -> bool:
        if self._on_task_changed is not None:
            self._on_task_changed()
        else:
            self.refresh()
        return False

    def _refresh_idle(self) -> bool:
        self.refresh()
        return False

    def _on_show_completed_changed(self, sw: Gtk.Switch, _pspec: object) -> None:
        self.set_show_completed(sw.get_active())

    # ---- tag filter ----------------------------------------------------

    def _rebuild_tag_dropdown(self, tags: list[str]) -> None:
        # The Gtk.DropDown StringList model has no public clear method, so
        # we rebuild the model whenever the universe of tags changes. The
        # leading "All tags" entry maps to ``tag_filter == None``.
        options = [_ALL_TAGS_LABEL, *tags]
        if options == self._tag_options:
            self._sync_dropdown_selection()
            return
        self._tag_options = options
        self._suppress_tag_signal = True
        try:
            model = Gtk.StringList.new(options)
            self._tag_dropdown.set_model(model)
            self._sync_dropdown_selection()
        finally:
            self._suppress_tag_signal = False

    def _sync_dropdown_selection(self) -> None:
        if self._tag_filter is None or self._tag_filter not in self._tag_options:
            target = 0
            if self._tag_filter is not None:
                # Filter refers to a tag that no longer exists in this
                # sprint — collapse silently to "All tags".
                self._tag_filter = None
        else:
            target = self._tag_options.index(self._tag_filter)
        if self._tag_dropdown.get_selected() != target:
            self._suppress_tag_signal = True
            try:
                self._tag_dropdown.set_selected(target)
            finally:
                self._suppress_tag_signal = False

    def _on_tag_filter_changed(self, dropdown: Gtk.DropDown, _pspec: object) -> None:
        if self._suppress_tag_signal:
            return
        idx = dropdown.get_selected()
        if idx == 0 or idx >= len(self._tag_options):
            self.set_tag_filter(None)
        else:
            self.set_tag_filter(self._tag_options[idx])

    # ---- context menu --------------------------------------------------

    def _build_menu_model(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Rename", "task.rename")
        move = Gio.Menu()
        move.append("Move to next sprint", "task.migrate-next")
        move.append("Move to previous sprint", "task.migrate-prev")
        menu.append_section(None, move)
        menu.append("Delete", "task.delete")
        return menu

    def _install_actions(self) -> None:
        group = Gio.SimpleActionGroup()
        rename_a = Gio.SimpleAction.new("rename", None)
        rename_a.connect("activate", lambda *_: self._rename_current())
        group.add_action(rename_a)
        delete_a = Gio.SimpleAction.new("delete", None)
        delete_a.connect("activate", lambda *_: self._delete_current())
        group.add_action(delete_a)
        self._migrate_next_a = Gio.SimpleAction.new("migrate-next", None)
        self._migrate_next_a.connect("activate", lambda *_: self._migrate_next_current())
        group.add_action(self._migrate_next_a)
        self._migrate_prev_a = Gio.SimpleAction.new("migrate-prev", None)
        self._migrate_prev_a.connect("activate", lambda *_: self._migrate_prev_current())
        group.add_action(self._migrate_prev_a)
        self._action_group = group
        # Insert into the popover itself once it has a parent (set per-open).

    def _open_context_menu(self, name: str, row: TaskRow, x: float, y: float) -> None:
        self._menu_target = name
        # The popover must be parented to a visible widget tree. Re-parent
        # to the row each time so positioning is row-local.
        if self._menu.get_parent() is not None:
            self._menu.unparent()
        self._menu.set_parent(row)
        self._menu.insert_action_group("task", self._action_group)
        self._migrate_prev_a.set_enabled(self._can_migrate_prev)
        self._migrate_next_a.set_enabled(self._current_sprint is not None)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        self._menu.set_pointing_to(rect)
        self._menu.popup()

    def _rename_current(self) -> None:
        name = self._menu_target
        if name is None:
            return
        current_title = ""
        try:
            current_title = notes.get_title(name)
        except (OSError, notes.InvalidNoteName):
            current_title = name[:-3]

        dialog = Adw.AlertDialog.new("Rename task", None)
        entry = Gtk.Entry()
        entry.set_text(current_title)
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
            new_title = entry.get_text().strip()
            try:
                notes.set_title(name, new_title)
            except OSError as e:
                _log.warning("task-list: rename %s failed (%s)", name, e)
                return
            self.refresh()

        dialog.connect("response", _on_response)
        parent = self.widget.get_root()
        dialog.present(parent)

    def _migrate_next_current(self) -> None:
        if self._menu_target is not None:
            self._on_migrate_next(self._menu_target)

    def _migrate_prev_current(self) -> None:
        if self._menu_target is not None:
            self._on_migrate_prev(self._menu_target)

    def _delete_current(self) -> None:
        name = self._menu_target
        if name is None:
            return
        try:
            title = notes.get_title(name)
        except (OSError, notes.InvalidNoteName):
            title = name[:-3]

        dialog = Adw.AlertDialog.new(
            "Delete task?",
            f"“{title}” and its notes file will be permanently removed.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def _on_response(_d: Adw.AlertDialog, response: str) -> None:
            if response != "delete":
                return
            self._on_delete(name)

        dialog.connect("response", _on_response)
        parent = self.widget.get_root()
        dialog.present(parent)
