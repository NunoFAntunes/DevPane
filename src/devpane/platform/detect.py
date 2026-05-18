"""Session-type, compositor, and layer-shell detection.

All probes are environment-based — we do not run subprocesses or touch
D-Bus. The result is intentionally informational: the daemon uses it to
pick a window adapter (M4), and CI uses it to decide whether to skip
display-dependent tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class SessionType(StrEnum):
    WAYLAND = "wayland"
    X11 = "x11"
    NONE = "none"


class Compositor(StrEnum):
    HYPRLAND = "hyprland"
    SWAY = "sway"
    KDE = "kde"
    GNOME = "gnome"
    WLROOTS = "wlroots"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlatformInfo:
    session: SessionType
    compositor: Compositor
    has_layer_shell: bool

    @property
    def has_display(self) -> bool:
        return self.session is not SessionType.NONE


def has_display() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def _detect_session() -> SessionType:
    # WAYLAND_DISPLAY wins because some Wayland sessions also set DISPLAY for XWayland.
    if os.environ.get("WAYLAND_DISPLAY"):
        return SessionType.WAYLAND
    if os.environ.get("DISPLAY"):
        # XDG_SESSION_TYPE can disambiguate; trust it if it says wayland.
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            return SessionType.WAYLAND
        return SessionType.X11
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return SessionType.WAYLAND
    if os.environ.get("XDG_SESSION_TYPE") == "x11":
        return SessionType.X11
    return SessionType.NONE


def _detect_compositor() -> Compositor:
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return Compositor.HYPRLAND
    if os.environ.get("SWAYSOCK"):
        return Compositor.SWAY
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").upper()
    if "KDE" in desktop or os.environ.get("KDE_FULL_SESSION"):
        return Compositor.KDE
    if "GNOME" in desktop or os.environ.get("GNOME_SHELL_SESSION_MODE"):
        return Compositor.GNOME
    if os.environ.get("WAYLAND_DISPLAY"):
        return Compositor.WLROOTS  # best-effort fallback for unknown Wayland
    return Compositor.UNKNOWN


def _probe_layer_shell() -> bool:
    """Return True iff gtk4-layer-shell is importable via gobject-introspection.

    A return of False does not mean layer-shell is unsupported — it means we
    cannot use it from Python in this environment. The daemon falls back to
    a plain top-anchored toplevel.
    """
    try:
        import gi

        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell  # noqa: F401
    except (ImportError, ValueError):
        return False
    return True


def detect() -> PlatformInfo:
    return PlatformInfo(
        session=_detect_session(),
        compositor=_detect_compositor(),
        has_layer_shell=_probe_layer_shell(),
    )
