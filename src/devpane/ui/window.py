"""DropDownWindow — the visible drop-down pane.

Hosts a left-side task list and a markdown editor on the right. Lifecycle:

- ``show_pane()`` reloads the current task from disk (so external edits
  are visible), then presents and focuses the editor.
- ``hide_pane()`` flushes any pending autosave so quitting/hiding never
  loses unsaved text.

Keyboard bindings (window-local):

- ``Escape``      hide the pane
- ``Ctrl+N``      create a new task (auto-named) and switch to it
- ``Ctrl+B``      toggle the task sidebar
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import sqlite3
from collections.abc import Callable
from importlib import resources
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

_ANIMATION_MS = 180

from devpane.store import notes, sprints, subtasks  # noqa: E402
from devpane.ui.editor import NoteEditor  # noqa: E402
from devpane.ui.prefs import Prefs  # noqa: E402
from devpane.ui.sprint_bar import SprintBar  # noqa: E402
from devpane.ui.subtask_panel import SubtaskPanel  # noqa: E402
from devpane.ui.task_list import TaskList  # noqa: E402

if TYPE_CHECKING:
    from devpane.platform.adapter import PlatformAdapter

_log = logging.getLogger(__name__)

_CSS_LOADED = False


def _load_css_once() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    css = resources.files("devpane.ui").joinpath("styles.css").read_text(encoding="utf-8")
    provider = Gtk.CssProvider()
    provider.load_from_data(css, -1)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        _CSS_LOADED = True


class DropDownWindow(Adw.ApplicationWindow):  # type: ignore[misc]
    """The drop-down pane window. Visibility is owned by callers."""

    def __init__(
        self,
        app: Adw.Application,
        adapter: PlatformAdapter,
        conn: sqlite3.Connection,
    ) -> None:
        super().__init__(application=app)
        self.set_title("DevPane")
        self.set_decorated(False)
        self.add_css_class("devpane-window")
        _load_css_once()

        self._adapter = adapter
        self._pane_visible = False
        self._prefs = Prefs.load()
        self._target_height = 1
        self._target_width = 1
        self._slide_anim: Adw.TimedAnimation | None = None

        self._editor = NoteEditor(conn)
        self._current_sprint: str | None = None
        self._task_list = TaskList(
            on_select=self._switch_to,
            on_new=self._new_task,
            on_delete=self._delete_task,
            on_migrate_next=self._migrate_next,
            on_migrate_prev=self._migrate_prev,
            show_completed=self._prefs.show_completed,
        )
        self._sprint_bar = SprintBar(
            on_prev=self._sprint_prev,
            on_next=self._sprint_next,
            on_rename=self._sprint_rename,
        )
        self._subtask_panel = SubtaskPanel(on_changed=self._on_subtasks_changed)

        # --- right pane: slim header + editor -----------------------------
        self._title_widget = Adw.WindowTitle.new("DevPane", "")
        right_header = Adw.HeaderBar()
        right_header.set_show_end_title_buttons(False)
        right_header.set_show_start_title_buttons(False)
        right_header.set_title_widget(self._title_widget)

        self._sidebar_btn = Gtk.ToggleButton()
        self._sidebar_btn.set_icon_name("sidebar-show-symbolic")
        self._sidebar_btn.set_tooltip_text("Toggle task list (Ctrl+B)")
        self._sidebar_btn.set_active(self._prefs.show_sidebar)
        self._sidebar_btn.connect("toggled", self._on_sidebar_toggled)
        right_header.pack_start(self._sidebar_btn)

        # Inner split: subtasks on the left of the right pane, editor on the
        # right. ``Gtk.Paned`` gives a draggable separator natively; the
        # last-known position is persisted in prefs.
        self._inner_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._inner_paned.set_start_child(self._subtask_panel.widget)
        self._inner_paned.set_end_child(self._editor)
        self._inner_paned.set_resize_start_child(False)
        self._inner_paned.set_resize_end_child(True)
        self._inner_paned.set_shrink_start_child(False)
        self._inner_paned.set_shrink_end_child(False)
        self._inner_paned.set_position(self._prefs.subtask_panel_width)

        right_view = Adw.ToolbarView()
        right_view.add_top_bar(right_header)
        right_view.set_content(self._inner_paned)

        # --- sidebar: sprint bar above task list --------------------------
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.append(self._sprint_bar.widget)
        sidebar_box.append(self._task_list.widget)
        self._task_list.widget.set_vexpand(True)

        # --- split view ---------------------------------------------------
        self._split = Adw.OverlaySplitView()
        self._split.set_sidebar(sidebar_box)
        self._split.set_content(right_view)
        self._split.set_sidebar_width_fraction(0.22)
        self._split.set_min_sidebar_width(220)
        self._split.set_max_sidebar_width(360)
        self._split.set_show_sidebar(self._prefs.show_sidebar)
        self.set_content(self._split)

        self._install_shortcuts()

        adapter.configure(self)
        _log.info("window: configured for adapter %s", adapter.name)

        # Ensure a default note exists so first show has content to load,
        # then ensure every task is assigned to a sprint (one-shot migration
        # for any pre-existing un-sprinted notes).
        notes.ensure_default()
        sprints.bootstrap_existing()

        existing = sprints.list_existing()
        self._current_sprint = self._choose_initial_sprint(existing)
        self._refresh_sidebar()

        startup_note = self._prefs.last_note or notes.DEFAULT_NOTE
        if not notes.exists(startup_note) or notes.get_sprint(startup_note) != self._current_sprint:
            startup_note = self._first_visible_task() or notes.DEFAULT_NOTE
        self._load(startup_note)

    # ---- visibility ----

    def is_pane_visible(self) -> bool:
        return self._pane_visible

    def show_pane(self) -> None:
        # Re-read the active note's text + cursor from disk so external
        # edits and the cursor saved at hide-time both take effect.
        self._editor.refresh()
        self._refresh_sidebar()
        if self._editor.current_note is not None:
            self._task_list.select(self._editor.current_note)
            self._title_widget.set_subtitle(notes.get_title(self._editor.current_note))
        self._size_to_monitor()
        if self._prefs.animate:
            self.set_default_size(self._target_width, 1)
        self.present()
        self._adapter.on_show(self)
        self._editor.focus()
        self._pane_visible = True
        if self._prefs.animate:
            self._animate_height(1, self._target_height)
        _log.debug("window: shown")

    def hide_pane(self) -> None:
        self._editor.flush()
        if self._editor.current_note is not None:
            self._prefs.last_note = self._editor.current_note
        self._prefs.show_sidebar = self._split.get_show_sidebar()
        self._prefs.show_completed = self._task_list.show_completed
        self._prefs.current_sprint = self._current_sprint
        self._prefs.subtask_panel_width = self._inner_paned.get_position()
        try:
            self._prefs.save()
        except OSError as e:
            _log.warning("prefs: save failed (%s)", e)
        self._adapter.on_hide(self)
        self.set_visible(False)
        self._pane_visible = False
        _log.debug("window: hidden")

    def toggle_pane(self) -> None:
        if self._pane_visible:
            self.hide_pane()
        else:
            self.show_pane()

    # ---- internals ----

    def _install_shortcuts(self) -> None:
        controller = Gtk.EventControllerKey()
        # Capture phase: window-level chords (Esc, Ctrl+N/B, Alt+Arrow) must
        # win over editor word-jump bindings on Alt+Left/Right.
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if keyval == Gdk.KEY_Escape:
            self.hide_pane()
            return True
        if ctrl and keyval in (Gdk.KEY_n, Gdk.KEY_N):
            self._new_task()
            return True
        if ctrl and keyval in (Gdk.KEY_b, Gdk.KEY_B):
            self._sidebar_btn.set_active(not self._sidebar_btn.get_active())
            return True
        alt = bool(state & Gdk.ModifierType.ALT_MASK)
        if alt and keyval == Gdk.KEY_Left:
            self._sprint_prev()
            return True
        if alt and keyval == Gdk.KEY_Right:
            self._sprint_next()
            return True
        return False

    def _on_sidebar_toggled(self, btn: Gtk.ToggleButton) -> None:
        self._split.set_show_sidebar(btn.get_active())

    def _new_task(self) -> None:
        # Format: note-YYYYMMDD-HHMM. Append a counter if it collides
        # within the same minute.
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        base = f"note-{stamp}"
        name = f"{base}.md"
        suffix = 1
        while notes.exists(name):
            suffix += 1
            name = f"{base}-{suffix}.md"
        created = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        # If no sprint exists yet (fresh install, first task), mint one now —
        # the rule "sprints come into being when a task lands in them" means
        # this is the moment to create the first sprint.
        if self._current_sprint is None:
            self._current_sprint = sprints.new_sprint_id()
        meta = {"created": created, "done": "false", "sprint": self._current_sprint}
        notes.write_task(name, meta, "")
        _log.info("window: new task %s (sprint %s)", name, self._current_sprint)
        self._refresh_sidebar()
        self._switch_to(name)
        self._editor.focus()

    def _delete_task(self, name: str) -> None:
        canon = notes.canonical_name(name)
        was_current = self._editor.current_note == canon
        notes.delete(canon)
        subtasks.delete_for(canon)
        _log.info("window: deleted task %s", canon)
        self._refresh_sidebar()
        if was_current:
            fallback = self._first_visible_task()
            if fallback is None:
                # Sprint is now empty. Hop to an adjacent sprint if any
                # exists; otherwise fall back to the default scratch note.
                existing = sprints.list_existing()
                if existing:
                    self._current_sprint = existing[0].id
                    self._refresh_sidebar()
                    fallback = self._first_visible_task()
                if fallback is None:
                    notes.ensure_default()
                    sprints.bootstrap_existing()
                    self._current_sprint = notes.get_sprint(notes.DEFAULT_NOTE)
                    self._refresh_sidebar()
                    fallback = notes.DEFAULT_NOTE
            self._load(fallback)

    # ---- subtasks --------------------------------------------------------

    def _on_subtasks_changed(self) -> None:
        # Subtask mutation may change the parent task's progress display
        # in the sidebar — refresh while preserving selection and filters.
        self._task_list.refresh()

    # ---- sprint navigation -----------------------------------------------

    def _sprint_prev(self) -> None:
        existing = sprints.list_existing()
        target = sprints.prev_of(self._current_sprint, existing)
        if target is None:
            return
        self._current_sprint = target.id
        self._refresh_sidebar()
        first = self._first_visible_task()
        if first is not None:
            self._load(first)

    def _sprint_next(self) -> None:
        existing = sprints.list_existing()
        target = sprints.next_of(self._current_sprint, existing)
        if target is None:
            return
        self._current_sprint = target.id
        self._refresh_sidebar()
        first = self._first_visible_task()
        if first is not None:
            self._load(first)

    def _sprint_rename(self, sprint_id: str, new_name: str) -> None:
        sprints.rename_sprint(sprint_id, new_name)
        self._refresh_sidebar()

    # ---- task migration --------------------------------------------------

    def _migrate_next(self, task_name: str) -> None:
        existing = sprints.list_existing()
        target = sprints.next_of(self._current_sprint, existing)
        target_id = target.id if target is not None else sprints.new_sprint_id()
        self._do_migrate(task_name, target_id)

    def _migrate_prev(self, task_name: str) -> None:
        existing = sprints.list_existing()
        target = sprints.prev_of(self._current_sprint, existing)
        if target is None:
            return
        self._do_migrate(task_name, target.id)

    def _do_migrate(self, task_name: str, target_sprint: str) -> None:
        canon = notes.canonical_name(task_name)
        try:
            notes.set_sprint(canon, target_sprint)
        except OSError as e:
            _log.warning("window: migrate %s failed (%s)", canon, e)
            return
        _log.info("window: migrated %s -> sprint %s", canon, target_sprint)
        was_current = self._editor.current_note == canon
        self._refresh_sidebar()
        if was_current:
            fallback = self._first_visible_task()
            if fallback is not None:
                self._load(fallback)

    # ---- helpers ---------------------------------------------------------

    def _refresh_sidebar(self) -> None:
        existing = sprints.list_existing()
        if existing and (self._current_sprint is None
                         or not any(s.id == self._current_sprint for s in existing)):
            self._current_sprint = existing[-1].id
        self._sprint_bar.set_state(existing, self._current_sprint)
        has_prev = sprints.prev_of(self._current_sprint, existing) is not None
        self._task_list.set_sprint(self._current_sprint, has_prev)

    def _first_visible_task(self) -> str | None:
        names = self._task_list.visible_names()
        return names[0] if names else None

    def _choose_initial_sprint(self, existing: list[sprints.Sprint]) -> str | None:
        if not existing:
            return None
        if self._prefs.current_sprint and any(
            s.id == self._prefs.current_sprint for s in existing
        ):
            return self._prefs.current_sprint
        return existing[-1].id

    def _switch_to(self, name: str) -> None:
        self._load(name)

    def _load(self, name: str) -> None:
        self._editor.load_note(name)
        canon = notes.canonical_name(name)
        self._title_widget.set_subtitle(notes.get_title(canon))
        self._task_list.select(canon)
        self._subtask_panel.load_for(canon)

    def _size_to_monitor(self) -> None:
        # M6 picks the first reported monitor. Following the cursor across
        # monitors is not generally possible on Wayland without compositor
        # extensions; users on multi-monitor setups can configure their
        # compositor to place DevPane on a specific output.
        display = self.get_display()
        if display is None:
            return
        monitors = display.get_monitors()
        if monitors.get_n_items() == 0:
            return
        monitor = monitors.get_item(0)
        if monitor is None:
            return
        geom = monitor.get_geometry()
        self._target_width = geom.width
        self._target_height = max(1, int(geom.height * self._prefs.height_ratio))
        if not self._prefs.animate:
            self.set_default_size(self._target_width, self._target_height)

    def _animate_height(self, from_h: int, to_h: int) -> None:
        if self._slide_anim is not None:
            self._slide_anim.pause()
            self._slide_anim = None

        target_width = self._target_width

        def _apply(v: float) -> None:
            self.set_default_size(target_width, max(1, int(v)))

        target = Adw.CallbackAnimationTarget.new(_apply)
        anim = Adw.TimedAnimation.new(self, from_h, to_h, _ANIMATION_MS, target)
        anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self._slide_anim = anim
        anim.play()


class GtkController:
    """``WindowController`` impl that bridges asyncio → GLib main thread."""

    def __init__(self, window: DropDownWindow, loop: asyncio.AbstractEventLoop) -> None:
        self._window = window
        self._loop = loop

    async def show(self) -> bool:
        return await self._call_on_main(self._window.show_pane)

    async def hide(self) -> bool:
        return await self._call_on_main(self._window.hide_pane)

    async def toggle(self) -> bool:
        return await self._call_on_main(self._window.toggle_pane)

    def is_visible(self) -> bool:
        return self._window.is_pane_visible()

    async def _call_on_main(self, fn: Callable[[], None]) -> bool:
        fut: asyncio.Future[bool] = self._loop.create_future()

        def _runner() -> bool:
            try:
                fn()
                self._loop.call_soon_threadsafe(fut.set_result, self._window.is_pane_visible())
            except Exception as e:
                self._loop.call_soon_threadsafe(fut.set_exception, e)
            return False

        GLib.idle_add(_runner)
        return await fut
