"""Tests for ``match_shortcut`` — the pure key-combo → command lookup."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")

from gi.repository import Gdk

from devpane.ui.keyboard_shortcuts import match_shortcut


_CTRL = Gdk.ModifierType.CONTROL_MASK
_SHIFT = Gdk.ModifierType.SHIFT_MASK
_ALT = Gdk.ModifierType.ALT_MASK


def test_ctrl_b_returns_bold() -> None:
    cmd = match_shortcut(Gdk.KEY_b, _CTRL)
    assert cmd is not None
    assert cmd.trigger == "bold"


def test_ctrl_b_uppercase_keyval_still_matches() -> None:
    # Some keyboard layouts deliver the uppercase keyval; we normalise.
    cmd = match_shortcut(Gdk.KEY_B, _CTRL)
    assert cmd is not None
    assert cmd.trigger == "bold"


def test_ctrl_i_returns_italic() -> None:
    cmd = match_shortcut(Gdk.KEY_i, _CTRL)
    assert cmd is not None
    assert cmd.trigger == "italic"


def test_ctrl_k_returns_link() -> None:
    cmd = match_shortcut(Gdk.KEY_k, _CTRL)
    assert cmd is not None
    assert cmd.trigger == "link"


def test_ctrl_shift_c_returns_inline_code() -> None:
    cmd = match_shortcut(Gdk.KEY_c, _CTRL | _SHIFT)
    assert cmd is not None
    assert cmd.trigger == "inlinecode"


def test_ctrl_c_alone_is_not_a_shortcut() -> None:
    # Ctrl+C is the standard "copy" — we must not steal it.
    assert match_shortcut(Gdk.KEY_c, _CTRL) is None


def test_plain_b_is_not_a_shortcut() -> None:
    assert match_shortcut(Gdk.KEY_b, Gdk.ModifierType(0)) is None


def test_ctrl_shift_b_is_not_bold() -> None:
    # Extra modifiers disqualify the match — different chord.
    assert match_shortcut(Gdk.KEY_b, _CTRL | _SHIFT) is None


def test_ctrl_alt_b_is_not_bold() -> None:
    assert match_shortcut(Gdk.KEY_b, _CTRL | _ALT) is None


def test_irrelevant_modifiers_are_ignored() -> None:
    # CapsLock / lock state shouldn't break the chord.
    cmd = match_shortcut(Gdk.KEY_b, _CTRL | Gdk.ModifierType.LOCK_MASK)
    assert cmd is not None
    assert cmd.trigger == "bold"


def test_unmapped_key_returns_none() -> None:
    assert match_shortcut(Gdk.KEY_F1, _CTRL) is None
