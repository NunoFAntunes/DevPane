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


# ---- task frontmatter ----------------------------------------------------


def test_read_task_no_frontmatter(xdg_tmp: Path) -> None:
    notes.write_atomic("plain", "just a body")
    meta, body = notes.read_task("plain")
    assert meta == {}
    assert body == "just a body"


def test_write_task_round_trip(xdg_tmp: Path) -> None:
    notes.write_task("t", {"title": "Buy milk", "done": "false"}, "details\nhere")
    meta, body = notes.read_task("t")
    assert meta == {"title": "Buy milk", "done": "false"}
    assert body == "details\nhere"


def test_write_task_empty_meta_writes_body_only(xdg_tmp: Path) -> None:
    notes.write_task("t", {}, "hi")
    assert notes.read("t") == "hi"


def test_set_done_preserves_body_and_meta(xdg_tmp: Path) -> None:
    # ``set_done`` is a thin wrapper over ``set_status`` for backwards
    # compatibility — it writes ``status:`` and drops any legacy ``done:``.
    notes.write_task("t", {"title": "X"}, "body")
    notes.set_done("t", True)
    meta, body = notes.read_task("t")
    assert meta["title"] == "X"
    assert meta["status"] == notes.STATUS_DONE
    assert "done" not in meta
    assert body == "body"
    assert notes.is_done("t") is True
    notes.set_done("t", False)
    assert notes.is_done("t") is False
    meta, _ = notes.read_task("t")
    assert meta["status"] == notes.STATUS_TODO


# ---- status (A5) ----------------------------------------------------------


def test_status_round_trip(xdg_tmp: Path) -> None:
    notes.write_task("t", {"title": "X"}, "body")
    for s in notes.STATUSES:
        notes.set_status("t", s)
        assert notes.get_status("t") == s


def test_status_rejects_unknown_value(xdg_tmp: Path) -> None:
    notes.write_task("t", {}, "")
    with pytest.raises(ValueError):
        notes.set_status("t", "nope")


def test_status_lazy_fallback_from_legacy_done(xdg_tmp: Path) -> None:
    # File predates the status enum and carries only ``done: true``.
    notes.write_task("legacy_done", {"done": "true"}, "b")
    assert notes.get_status("legacy_done") == notes.STATUS_DONE
    # ``done: false`` and missing both default to ``todo``.
    notes.write_task("legacy_open", {"done": "false"}, "b")
    assert notes.get_status("legacy_open") == notes.STATUS_TODO
    notes.write_task("bare", {}, "b")
    assert notes.get_status("bare") == notes.STATUS_TODO


def test_status_unknown_value_falls_back_to_todo(xdg_tmp: Path) -> None:
    notes.write_task("t", {"status": "wat"}, "b")
    assert notes.get_status("t") == notes.STATUS_TODO


def test_set_status_drops_legacy_done_key(xdg_tmp: Path) -> None:
    notes.write_task("t", {"done": "true", "title": "X"}, "body")
    notes.set_status("t", notes.STATUS_DOING)
    meta, _ = notes.read_task("t")
    assert meta["status"] == notes.STATUS_DOING
    assert "done" not in meta
    assert meta["title"] == "X"


def test_status_present_wins_over_legacy_done(xdg_tmp: Path) -> None:
    # Defensive: if both keys are present, ``status:`` is canonical.
    notes.write_task("t", {"done": "true", "status": "doing"}, "")
    assert notes.get_status("t") == notes.STATUS_DOING


# ---- tags (A4) ------------------------------------------------------------


def test_tags_round_trip(xdg_tmp: Path) -> None:
    notes.write_task("t", {}, "")
    notes.set_tags("t", ["bug", "auth"])
    raw = notes.read("t")
    assert "tags: bug, auth" in raw
    assert notes.get_tags("t") == ["bug", "auth"]


def test_tags_normalised_on_write(xdg_tmp: Path) -> None:
    notes.write_task("t", {}, "")
    notes.set_tags("t", ["  Bug ", "AUTH", "bug", "", "auth"])
    assert notes.get_tags("t") == ["bug", "auth"]


def test_tags_empty_list_removes_field(xdg_tmp: Path) -> None:
    notes.write_task("t", {"tags": "bug, auth"}, "")
    notes.set_tags("t", [])
    meta, _ = notes.read_task("t")
    assert "tags" not in meta
    assert notes.get_tags("t") == []


def test_parse_tags_handles_csv_directly(xdg_tmp: Path) -> None:
    assert notes.parse_tags("  bug , Auth, , bug ") == ["bug", "auth"]
    assert notes.parse_tags("") == []


def test_get_tags_missing_field(xdg_tmp: Path) -> None:
    notes.write_task("t", {"title": "X"}, "")
    assert notes.get_tags("t") == []


def test_set_title_on_plain_note(xdg_tmp: Path) -> None:
    notes.write_atomic("plain", "body")
    notes.set_title("plain", "Pretty Title")
    meta, body = notes.read_task("plain")
    assert meta == {"title": "Pretty Title"}
    assert body == "body"


def test_get_title_falls_back_to_stem(xdg_tmp: Path) -> None:
    notes.write_atomic("scratch", "x")
    assert notes.get_title("scratch") == "scratch"
    notes.set_title("scratch", "Nice")
    assert notes.get_title("scratch") == "Nice"


def test_malformed_frontmatter_treated_as_body(xdg_tmp: Path) -> None:
    # Missing closing ``---`` — entire content should be returned as body.
    notes.write_atomic("bad", "---\ntitle: x\nbody without close")
    meta, body = notes.read_task("bad")
    assert meta == {}
    assert body == "---\ntitle: x\nbody without close"


def test_frontmatter_with_quoted_values(xdg_tmp: Path) -> None:
    notes.write_atomic("q", '---\ntitle: "Hello: World"\n---\nbody')
    meta, body = notes.read_task("q")
    assert meta["title"] == "Hello: World"
    assert body == "body"


def test_set_title_empty_removes_field(xdg_tmp: Path) -> None:
    notes.write_task("t", {"title": "Old", "done": "false"}, "b")
    notes.set_title("t", "  ")
    meta, _ = notes.read_task("t")
    assert "title" not in meta
    assert meta.get("done") == "false"
