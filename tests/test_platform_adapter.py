"""Tests for the platform adapter factory.

These tests do not touch GTK or import gtk4-layer-shell directly; they
only verify that ``pick_adapter`` returns the right type given a
synthesized ``PlatformInfo``. The adapter modules themselves import
``gi`` lazily, so this suite runs without a display.
"""

from __future__ import annotations

import pytest

from devpane.platform.adapter import NoopAdapter, pick_adapter
from devpane.platform.detect import Compositor, PlatformInfo, SessionType


def _info(
    session: SessionType, compositor: Compositor = Compositor.UNKNOWN, layer_shell: bool = False
) -> PlatformInfo:
    return PlatformInfo(session=session, compositor=compositor, has_layer_shell=layer_shell)


def test_wayland_with_layer_shell_picks_layer_adapter() -> None:
    pytest.importorskip("gi", reason="PyGObject not available in test env")
    pytest.importorskip("gi.repository.Gtk4LayerShell", reason="gtk4-layer-shell not installed")
    a = pick_adapter(_info(SessionType.WAYLAND, Compositor.KDE, layer_shell=True))
    assert a.name == "wayland-layer-shell"


def test_wayland_without_layer_shell_picks_plain_adapter() -> None:
    a = pick_adapter(_info(SessionType.WAYLAND, Compositor.GNOME, layer_shell=False))
    assert a.name == "wayland-plain"


def test_x11_picks_x11_adapter() -> None:
    a = pick_adapter(_info(SessionType.X11, Compositor.UNKNOWN))
    assert a.name == "x11"


def test_no_session_picks_noop() -> None:
    a = pick_adapter(_info(SessionType.NONE, Compositor.UNKNOWN))
    assert isinstance(a, NoopAdapter)
