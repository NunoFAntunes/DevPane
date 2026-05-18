"""Wayland adapter using ``gtk4-layer-shell``.

Layer-shell makes the window a *layer surface* on the compositor's TOP
layer, anchored to the top edge and spanning the full width. The surface
floats above normal windows but does not reserve screen real estate
(``exclusive_zone = 0`` — we are an overlay, not a panel).

Keyboard mode is ``ON_DEMAND``: the layer surface receives input only when
focused, which lets the user click away to dismiss focus without the
window stealing global keyboard input. Switching to ``EXCLUSIVE`` would
suit a Guake-style "captures everything while visible" UX; we defer that
choice to M5+ when the editor is present.

Layer-shell calls must happen *before* the window is mapped, so all the
configuration is done in ``configure()`` and not on show/hide.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

if TYPE_CHECKING:
    from devpane.ui.window import DropDownWindow

_log = logging.getLogger(__name__)

_NAMESPACE = "devpane"


class LayerShellAdapter:
    name = "wayland-layer-shell"

    def configure(self, window: DropDownWindow) -> None:
        LayerShell.init_for_window(window)
        LayerShell.set_namespace(window, _NAMESPACE)
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
        LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
        LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
        LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, False)
        LayerShell.set_exclusive_zone(window, 0)
        LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.ON_DEMAND)
        _log.debug("layer-shell configured (top, on-demand keyboard)")

    def on_show(self, window: DropDownWindow) -> None:
        return None

    def on_hide(self, window: DropDownWindow) -> None:
        return None
