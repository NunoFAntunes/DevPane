"""Tests for the subtask sidecar store."""

from __future__ import annotations

from pathlib import Path

import pytest

from devpane.store import notes, subtasks
from devpane.store.subtasks import Subtask


def test_load_missing_returns_empty(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    assert subtasks.load("t") == []


def test_round_trip_preserves_order(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    items = [
        Subtask("Buy milk", False),
        Subtask("Buy bread", True),
        Subtask("Buy eggs", False),
    ]
    subtasks.save("t", items)
    loaded = subtasks.load("t")
    assert loaded == items


def test_save_empty_removes_file(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    subtasks.save("t", [Subtask("x", False)])
    assert subtasks.path_for("t").is_file()
    subtasks.save("t", [])
    assert not subtasks.path_for("t").exists()


def test_delete_for_idempotent(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    subtasks.save("t", [Subtask("x", True)])
    subtasks.delete_for("t")
    assert not subtasks.path_for("t").exists()
    # Second call is a no-op, not an error.
    subtasks.delete_for("t")


def test_malformed_json_returns_empty(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    path = subtasks.path_for("t")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json{{{")
    assert subtasks.load("t") == []


def test_load_drops_non_dict_entries(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    path = subtasks.path_for("t")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[{"text": "ok", "done": true}, 42, "garbage", {"text": "also ok"}]')
    out = subtasks.load("t")
    assert out == [Subtask("ok", True), Subtask("also ok", False)]


def test_progress_no_subtasks(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    assert subtasks.progress("t") == (0, 0)


def test_progress_mixed(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    subtasks.save(
        "t",
        [
            Subtask("a", True),
            Subtask("b", False),
            Subtask("c", True),
            Subtask("d", False),
        ],
    )
    assert subtasks.progress("t") == (2, 4)


def test_save_atomic_no_orphan_tmp(xdg_tmp: Path) -> None:
    notes.write_atomic("t", "")
    subtasks.save("t", [Subtask("a", False)])
    d = subtasks.path_for("t").parent
    stray = [p.name for p in d.iterdir() if p.name.startswith(".")]
    assert stray == []


def test_path_for_rejects_bad_names(xdg_tmp: Path) -> None:
    with pytest.raises(notes.InvalidNoteName):
        subtasks.path_for("../escape")


def test_delete_for_with_invalid_name_is_noop(xdg_tmp: Path) -> None:
    # Should not raise — defensive cleanup path.
    subtasks.delete_for("../bad")
