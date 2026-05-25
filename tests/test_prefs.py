"""Tests for the JSON prefs file."""

from __future__ import annotations

import json
from pathlib import Path

from devpane.ui.prefs import Prefs


def test_load_returns_defaults_when_missing(xdg_tmp: Path) -> None:
    p = Prefs.load()
    assert p.height_ratio == 0.6
    assert p.last_note is None
    assert p.animate is True


def test_save_then_load_roundtrip(xdg_tmp: Path) -> None:
    p = Prefs(height_ratio=0.42, last_note="foo.md", animate=False)
    p.save()
    loaded = Prefs.load()
    assert loaded == p


def test_clamp_ratio(xdg_tmp: Path) -> None:
    from devpane.ui import prefs as prefs_mod

    cfg = prefs_mod.config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "prefs.json").write_text(json.dumps({"height_ratio": 5.0}))
    assert Prefs.load().height_ratio == 0.95
    (cfg / "prefs.json").write_text(json.dumps({"height_ratio": 0.0}))
    assert Prefs.load().height_ratio == 0.2


def test_load_ignores_corrupt_file(xdg_tmp: Path) -> None:
    from devpane.ui import prefs as prefs_mod

    cfg = prefs_mod.config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "prefs.json").write_text("not json")
    p = Prefs.load()
    assert p.height_ratio == 0.6


def test_load_rejects_wrong_type_for_last_note(xdg_tmp: Path) -> None:
    from devpane.ui import prefs as prefs_mod

    cfg = prefs_mod.config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "prefs.json").write_text(json.dumps({"last_note": 42}))
    assert Prefs.load().last_note is None


def test_tag_filter_default_is_none(xdg_tmp: Path) -> None:
    assert Prefs.load().tag_filter is None


def test_tag_filter_round_trip(xdg_tmp: Path) -> None:
    Prefs(tag_filter="bug").save()
    assert Prefs.load().tag_filter == "bug"


def test_tag_filter_coerces_invalid_types(xdg_tmp: Path) -> None:
    from devpane.ui import prefs as prefs_mod

    cfg = prefs_mod.config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    for raw in (42, [], {}, None):
        (cfg / "prefs.json").write_text(json.dumps({"tag_filter": raw}))
        assert Prefs.load().tag_filter is None


def test_tag_filter_normalises_whitespace_and_case(xdg_tmp: Path) -> None:
    from devpane.ui import prefs as prefs_mod

    cfg = prefs_mod.config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "prefs.json").write_text(json.dumps({"tag_filter": "  Bug  "}))
    assert Prefs.load().tag_filter == "bug"
    (cfg / "prefs.json").write_text(json.dumps({"tag_filter": "   "}))
    assert Prefs.load().tag_filter is None
