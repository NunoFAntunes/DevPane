"""Wayland fallback for compositors without layer-shell (GNOME/Mutter).

Wayland deliberately does not let regular toplevels position themselves;
the compositor owns placement. With GTK 4 alone we cannot anchor the
window to the top edge — we can only ensure it is borderless and the
right size. Mutter typically centers our window; KWin/Sway/Hyprland do
similarly when layer-shell is absent.

If you want a real drop-down on GNOME, install ``gtk4-layer-shell`` and
DevPane will pick the layer-shell adapter automatically.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devpane.ui.window import DropDownWindow

_log = logging.getLogger(__name__)


class WaylandPlainAdapter:
    name = "wayland-plain"

    def configure(self, window: DropDownWindow) -> None:
        # Window is already decoration-less from DropDownWindow.__init__.
        # Mark as non-resizable so the compositor doesn't add resize affordances.
        window.set_resizable(False)
        _log.debug("wayland plain: borderless toplevel")

    def on_show(self, window: DropDownWindow) -> None:
        return None

    def on_hide(self, window: DropDownWindow) -> None:
        return None
