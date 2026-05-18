"""Tests for platform / session / compositor detection."""

from __future__ import annotations

import pytest

from devpane.platform.detect import (
    Compositor,
    SessionType,
    _detect_compositor,
    _detect_session,
    has_display,
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "WAYLAND_DISPLAY",
        "DISPLAY",
        "XDG_SESSION_TYPE",
        "XDG_CURRENT_DESKTOP",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "SWAYSOCK",
        "KDE_FULL_SESSION",
        "GNOME_SHELL_SESSION_MODE",
    ):
        monkeypatch.delenv(var, raising=False)


def test_no_env_is_none_session(clean_env: None) -> None:
    assert _detect_session() is SessionType.NONE
    assert has_display() is False


def test_wayland_display_wins(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")  # XWayland
    assert _detect_session() is SessionType.WAYLAND
    assert has_display() is True


def test_x11_only(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.setenv("DISPLAY", ":0")
    assert _detect_session() is SessionType.X11


def test_xdg_session_type_disambiguates(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert _detect_session() is SessionType.WAYLAND


def test_compositor_hyprland(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "abc")
    assert _detect_compositor() is Compositor.HYPRLAND


def test_compositor_sway(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.setenv("SWAYSOCK", "/run/user/1000/sway.sock")
    assert _detect_compositor() is Compositor.SWAY


def test_compositor_kde(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert _detect_compositor() is Compositor.KDE


def test_compositor_gnome(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    assert _detect_compositor() is Compositor.GNOME


def test_compositor_wlroots_fallback(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert _detect_compositor() is Compositor.WLROOTS


def test_compositor_unknown(clean_env: None) -> None:
    assert _detect_compositor() is Compositor.UNKNOWN
