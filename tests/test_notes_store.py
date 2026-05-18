"""Tests for the filesystem note store."""

from __future__ import annotations

from pathlib import Path

import pytest

from devpane.store import notes


def test_round_trip(xdg_tmp: Path) -> None:
    notes.write_atomic("hello", "# Hi\nbody")
    assert notes.read("hello") == "# Hi\nbody"
    assert notes.read("hello.md") == "# Hi\nbody"


def test_list_empty_then_default(xdg_tmp: Path) -> None:
    assert notes.list_notes() == []
    assert notes.ensure_default() == "scratch.md"
    assert notes.list_notes() == ["scratch.md"]


def test_list_sorted(xdg_tmp: Path) -> None:
    for n in ["c", "a", "b"]:
        notes.write_atomic(n, n)
    assert notes.list_notes() == ["a.md", "b.md", "c.md"]


@pytest.mark.parametrize(
    "bad",
    ["", ".hidden", "../escape", "with space", "slash/inside", ".md", "x/y.md"],
)
def test_rejects_bad_names(xdg_tmp: Path, bad: str) -> None:
    with pytest.raises(notes.InvalidNoteName):
        notes.write_atomic(bad, "x")


def test_write_atomic_leaves_no_tmp_files(xdg_tmp: Path) -> None:
    notes.write_atomic("foo", "x")
    d = notes.notes_dir()
    stray = [p.name for p in d.iterdir() if p.name.startswith(".")]
    assert stray == [], f"unexpected tmp files: {stray}"


def test_write_atomic_overwrites(xdg_tmp: Path) -> None:
    notes.write_atomic("foo", "v1")
    notes.write_atomic("foo", "v2")
    assert notes.read("foo") == "v2"


def test_delete(xdg_tmp: Path) -> None:
    notes.write_atomic("foo", "x")
    notes.delete("foo")
    assert "foo.md" not in notes.list_notes()
    notes.delete("foo")  # idempotent


def test_path_for_within_notes_dir(xdg_tmp: Path) -> None:
    p = notes.path_for("foo")
    assert p.parent == notes.notes_dir()
    assert p.name == "foo.md"


def test_cleanup_orphans_removes_stale_tmp_files(xdg_tmp: Path) -> None:
    d = notes.notes_dir()
    d.mkdir(parents=True, exist_ok=True)
    # Simulate two crashed atomic writes.
    (d / ".scratch.md.abc.tmp").write_text("partial")
    (d / ".other.md.xyz.tmp").write_text("partial")
    # And a real note that must NOT be deleted.
    (d / "real.md").write_text("keep me")
    removed = notes.cleanup_orphans()
    assert removed == 2
    assert (d / "real.md").exists()
    assert not any(p.name.endswith(".tmp") for p in d.iterdir())


def test_cleanup_orphans_with_no_dir(xdg_tmp: Path) -> None:
    # No notes_dir created — should be a no-op, not an error.
    assert notes.cleanup_orphans() == 0


def test_cleanup_orphans_leaves_unrelated_dotfiles(xdg_tmp: Path) -> None:
    d = notes.notes_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / ".gitkeep").write_text("")
    (d / ".scratch.md.abc.tmp").write_text("x")
    assert notes.cleanup_orphans() == 1
    assert (d / ".gitkeep").exists()
