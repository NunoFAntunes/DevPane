"""Auto-continue markdown list items on Enter.

Behaviour, modelled on Notion / most modern markdown editors:

- Pressing Enter at the end of ``- foo`` inserts ``\\n- `` so the next
  item is prefilled.
- Pressing Enter on an empty marker (``- ``, ``1. ``, ``- [ ] ``) strips
  the marker so a second Enter exits the list and starts a normal line.
- Numbered lists auto-increment (``3. third`` + Enter → ``4. ``).
- Bullet variants ``*`` and ``+`` are handled identically to ``-``.
- Indented lists keep their indent (``  - foo`` + Enter → ``  - ``).
- Shift+Enter is left alone — it's the "soft line break" escape hatch.

The pure :func:`compute_list_action` helper is GTK-free and unit-tested.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk  # noqa: E402

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ListAction:
    """What Enter should do on a list line.

    Two variants:

    - **continue**: insert ``"\\n" + next_prefix`` at the cursor.
    - **escape**:   delete the marker from the line so the user lands on
      an empty line (a second Enter then starts a fresh paragraph).
    """

    next_prefix: str
    is_escape: bool


# Checkbox must be checked BEFORE bullet, because a checkbox line also
# matches the bullet pattern.
_CHECKBOX_RE = re.compile(r"^(\s*)([-*+]) \[[ xX]\] (.*)$")
_BULLET_RE = re.compile(r"^(\s*)([-*+]) (.*)$")
_NUMBERED_RE = re.compile(r"^(\s*)(\d+)\. (.*)$")


def compute_list_action(line_text: str) -> ListAction | None:
    """Inspect the line up to the cursor; decide what Enter should do.

    Returns ``None`` if the line isn't a list item — Enter behaves normally.
    """
    m = _CHECKBOX_RE.match(line_text)
    if m:
        indent, marker, content = m.group(1), m.group(2), m.group(3)
        if not content.strip():
            return ListAction(next_prefix="", is_escape=True)
        return ListAction(next_prefix=f"{indent}{marker} [ ] ", is_escape=False)

    m = _BULLET_RE.match(line_text)
    if m:
        indent, marker, content = m.group(1), m.group(2), m.group(3)
        if not content.strip():
            return ListAction(next_prefix="", is_escape=True)
        return ListAction(next_prefix=f"{indent}{marker} ", is_escape=False)

    m = _NUMBERED_RE.match(line_text)
    if m:
        indent, num_s, content = m.group(1), m.group(2), m.group(3)
        if not content.strip():
            return ListAction(next_prefix="", is_escape=True)
        return ListAction(next_prefix=f"{indent}{int(num_s) + 1}. ", is_escape=False)

    return None


class ListContinuation:
    """Installs an Enter handler on a ``Gtk.TextView`` to drive list auto-continue.

    Construct with ``ListContinuation(view)`` and let it live for the
    lifetime of the view. The handler uses ``CAPTURE`` phase so it runs
    before the buffer's default newline insertion. It returns ``False``
    for non-list lines and Shift+Enter, leaving normal behaviour intact.
    """

    def __init__(self, view: Gtk.TextView) -> None:
        self._view = view
        self._buffer = view.get_buffer()

        kc = Gtk.EventControllerKey()
        kc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        kc.connect("key-pressed", self._on_key_pressed)
        view.add_controller(kc)

    def _on_key_pressed(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        if state & Gdk.ModifierType.SHIFT_MASK:
            return False
        # Ignore if any non-shift modifier is involved (Ctrl+Enter etc.).
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False

        try:
            return self._handle_enter()
        except Exception:
            _log.exception("list-continuation: handle_enter failed")
            return False

    def _handle_enter(self) -> bool:
        cursor = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        line_start = cursor.copy()
        line_start.set_line_offset(0)
        line_text = self._buffer.get_text(line_start, cursor, False)

        action = compute_list_action(line_text)
        if action is None:
            return False

        self._buffer.begin_user_action()
        try:
            if action.is_escape:
                # Re-fetch the cursor iter in case other handlers moved it.
                cursor_now = self._buffer.get_iter_at_mark(self._buffer.get_insert())
                line_start_now = cursor_now.copy()
                line_start_now.set_line_offset(0)
                self._buffer.delete(line_start_now, cursor_now)
            else:
                self._buffer.insert_at_cursor("\n" + action.next_prefix)
        finally:
            self._buffer.end_user_action()
        return True
