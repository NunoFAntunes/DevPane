"""Keyboard shortcuts for inline markdown formatting.

| Shortcut       | Inserts / wraps selection with                |
|----------------|------------------------------------------------|
| Ctrl+B         | ``**bold**``                                   |
| Ctrl+I         | ``*italic*``                                   |
| Ctrl+K         | ``[text](url)``                                |
| Ctrl+Shift+C   | `` `inline code` ``                            |

Each shortcut delegates to :func:`devpane.ui.slash_commands.apply_template`
so the wrap/insert behaviour is identical to the equivalent slash command.
The chosen chords don't conflict with ``Gtk.TextView``'s default
bindings (copy, paste, select-all, undo, etc.) or with the existing
``SlashMenu`` / ``ListContinuation`` capture-phase handlers — both of
those return ``False`` for keys they don't handle, so this controller
gets a clean shot at the event.

The pure :func:`match_shortcut` helper is unit-tested without GTK.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk  # noqa: E402

from devpane.ui.slash_commands import COMMANDS, SlashCommand, apply_template  # noqa: E402

_log = logging.getLogger(__name__)


_COMMAND_BY_TRIGGER: dict[str, SlashCommand] = {c.trigger: c for c in COMMANDS}

# Only Ctrl/Shift/Alt are considered when matching. NumLock, CapsLock,
# Mod2 etc. are stripped.
_SIGNIFICANT_MODS = (
    Gdk.ModifierType.CONTROL_MASK
    | Gdk.ModifierType.SHIFT_MASK
    | Gdk.ModifierType.ALT_MASK
)


# (keyval-after-keyval_to_lower, modifier-mask) -> trigger key into COMMANDS.
_SHORTCUTS: dict[tuple[int, int], str] = {
    (Gdk.KEY_b, Gdk.ModifierType.CONTROL_MASK): "bold",
    (Gdk.KEY_i, Gdk.ModifierType.CONTROL_MASK): "italic",
    (Gdk.KEY_k, Gdk.ModifierType.CONTROL_MASK): "link",
    (
        Gdk.KEY_c,
        Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK,
    ): "inlinecode",
}


def match_shortcut(keyval: int, state: Gdk.ModifierType) -> SlashCommand | None:
    """Look up which slash command (if any) this key combo should invoke.

    ``keyval`` is normalised to lowercase so Caps Lock / Shift state on
    layout-dependent keys doesn't trip us up; the actual modifier state
    is matched on the masked bits.
    """
    keyval_lower = Gdk.keyval_to_lower(keyval)
    mods = int(state) & int(_SIGNIFICANT_MODS)
    trigger = _SHORTCUTS.get((keyval_lower, mods))
    if trigger is None:
        return None
    return _COMMAND_BY_TRIGGER.get(trigger)


class KeyboardShortcuts:
    """Installs a CAPTURE-phase key controller on a ``Gtk.TextView``.

    The controller returns ``True`` (consuming the event) only for keys
    that match one of our shortcuts, so the view's default bindings and
    the SlashMenu / ListContinuation controllers are untouched.
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
        cmd = match_shortcut(keyval, state)
        if cmd is None:
            return False
        try:
            self._buffer.begin_user_action()
            try:
                apply_template(self._buffer, cmd.insert)
            finally:
                self._buffer.end_user_action()
        except Exception:
            _log.exception("shortcuts: applying %s failed", cmd.trigger)
            return False
        return True
