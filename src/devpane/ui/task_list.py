"""Task list sidebar — replaces the old header switcher popover.

Each task is one note file. The row shows a checkbox (done state, stored
in the note's frontmatter) and a title (``meta['title']`` or filename
stem). Selecting a row opens its notes file in the editor. Right-click
opens a context menu with Rename / Delete.

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

from devpane.store import notes  # noqa: E402

_log = logging.getLogger(__name__)


class TaskRow(Gtk.ListBoxRow):  # type: ignore[misc]
    """One task: checkbox + title label. Carries its note filename."""

    def __init__(
        self,
        name: str,
        title: str,
        done: bool,
        on_toggle: Callable[[str, bool], None],
        on_context: Callable[[str, TaskRow, float, float], None],
    ) -> None:
        super().__init__()
        self._name = name
        self._on_toggle = on_toggle
        self.add_css_class("task-row")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(2)
        box.set_margin_bottom(2)

        self._check = Gtk.CheckButton()
        self._check.set_active(done)
        # Don't let the checkbox steal row activation focus styling.
        self._check.set_focus_on_click(False)
        self._check.connect("toggled", self._on_check_toggled)
        box.append(self._check)

        self._label = Gtk.Label(label=title, xalign=0)
        self._label.set_hexpand(True)
        self._label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        box.append(self._label)

        self.set_child(box)
        if done:
            self.add_css_class("task-done")

        # Right-click context menu.
        gesture = Gtk.GestureClick()
        gesture.set_button(Gdk.BUTTON_SECONDARY)
        gesture.connect("pressed", lambda _g, _n, x, y: on_context(self._name, self, x, y))
        self.add_controller(gesture)

    @property
    def name(self) -> str:
        return self._name

    def _on_check_toggled(self, btn: Gtk.CheckButton) -> None:
        self._on_toggle(self._name, btn.get_active())


class TaskList:
    """Sidebar widget. Use ``.widget`` to embed it."""

    def __init__(
        self,
        on_select: Callable[[str], None],
        on_new: Callable[[], None],
        on_delete: Callable[[str], None],
        show_completed: bool,
    ) -> None:
        self._on_select = on_select
        self._on_new = on_new
        self._on_delete = on_delete
        self._show_completed = show_completed
        self._suppress_select = False
        self._current: str | None = None

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

        # --- footer: show-completed switch ------------------------------
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.add_css_class("task-list-footer")
        footer_label = Gtk.Label(label="Show completed", xalign=0)
        footer_label.set_hexpand(True)
        footer.append(footer_label)
        self._show_switch = Gtk.Switch()
        self._show_switch.set_active(self._show_completed)
        self._show_switch.connect("notify::active", self._on_show_completed_changed)
        footer.append(self._show_switch)
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
        rows: list[tuple[bool, float, str, str]] = []
        for name in notes.list_notes():
            try:
                meta, _ = notes.read_task(name)
            except (OSError, notes.InvalidNoteName) as e:
                _log.warning("task-list: skipping %s (%s)", name, e)
                continue
            done = meta.get("done", "").lower() == "true"
            if done and not self._show_completed:
                continue
            title = meta.get("title", "").strip() or name[:-3]
            try:
                mt = notes.mtime(name)
            except OSError:
                mt = 0.0
            rows.append((done, mt, title, name))

        # Open tasks first (done flag asc), then by mtime desc.
        rows.sort(key=lambda r: (r[0], -r[1]))

        for done, _mt, title, name in rows:
            row = TaskRow(
                name=name,
                title=title,
                done=done,
                on_toggle=self._on_check_toggle,
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

    def set_show_completed(self, value: bool) -> None:
        if value == self._show_completed:
            return
        self._show_completed = value
        if self._show_switch.get_active() != value:
            self._show_switch.set_active(value)
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

    def _on_check_toggle(self, name: str, done: bool) -> None:
        try:
            notes.set_done(name, done)
        except OSError as e:
            _log.warning("task-list: set_done %s failed (%s)", name, e)
            return
        # If we're hiding completed, the row should disappear; otherwise
        # just restyle. Either way, a refresh is the simplest correct path.
        GLib.idle_add(self._refresh_idle)

    def _refresh_idle(self) -> bool:
        self.refresh()
        return False

    def _on_show_completed_changed(self, sw: Gtk.Switch, _pspec: object) -> None:
        self.set_show_completed(sw.get_active())

    # ---- context menu --------------------------------------------------

    def _build_menu_model(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Rename", "task.rename")
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
