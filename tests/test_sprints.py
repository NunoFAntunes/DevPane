"""Tests for sprint discovery, navigation, and bootstrap."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from devpane.store import notes, sprints
from devpane.store.paths import data_dir


def test_get_set_sprint_round_trip(xdg_tmp: Path) -> None:
    notes.write_task("t", {"done": "false"}, "body")
    assert notes.get_sprint("t") is None
    notes.set_sprint("t", "2026-05-22T18:30:45")
    assert notes.get_sprint("t") == "2026-05-22T18:30:45"
    # Body & other meta preserved.
    meta, body = notes.read_task("t")
    assert meta["done"] == "false"
    assert body == "body"


def test_set_sprint_empty_removes_field(xdg_tmp: Path) -> None:
    notes.write_task("t", {"sprint": "2026-05-22T18:30:45"}, "x")
    notes.set_sprint("t", "")
    assert notes.get_sprint("t") is None


def test_new_sprint_id_uses_injected_now(xdg_tmp: Path) -> None:
    when = datetime.datetime(2026, 5, 22, 18, 30, 45, 123456)
    assert sprints.new_sprint_id(when) == "2026-05-22T18:30:45"


def test_default_name_for_is_date_portion(xdg_tmp: Path) -> None:
    assert sprints.default_name_for("2026-05-22T18:30:45") == "2026-05-22"


def test_list_existing_returns_unique_sorted(xdg_tmp: Path) -> None:
    notes.write_task("a", {"sprint": "2026-06-01T10:00:00"}, "")
    notes.write_task("b", {"sprint": "2026-05-01T10:00:00"}, "")
    notes.write_task("c", {"sprint": "2026-06-01T10:00:00"}, "")
    notes.write_task("d", {}, "")  # un-sprinted, ignored
    out = sprints.list_existing()
    ids = [s.id for s in out]
    assert ids == ["2026-05-01T10:00:00", "2026-06-01T10:00:00"]
    # Default names = date portion.
    assert [s.name for s in out] == ["2026-05-01", "2026-06-01"]


def test_rename_persists_and_survives_reload(xdg_tmp: Path) -> None:
    sid = "2026-05-22T18:30:45"
    notes.write_task("t", {"sprint": sid}, "")
    sprints.rename_sprint(sid, "Auth refactor")
    out = sprints.list_existing()
    assert out[0].name == "Auth refactor"
    # And it landed in sprints.json.
    reg = json.loads((data_dir() / "sprints.json").read_text())
    assert reg[sid] == "Auth refactor"


def test_rename_to_default_removes_override(xdg_tmp: Path) -> None:
    sid = "2026-05-22T18:30:45"
    notes.write_task("t", {"sprint": sid}, "")
    sprints.rename_sprint(sid, "Auth refactor")
    sprints.rename_sprint(sid, "2026-05-22")  # same as default
    reg_path = data_dir() / "sprints.json"
    assert json.loads(reg_path.read_text()) == {}


def test_rename_empty_string_removes_override(xdg_tmp: Path) -> None:
    sid = "2026-05-22T18:30:45"
    notes.write_task("t", {"sprint": sid}, "")
    sprints.rename_sprint(sid, "X")
    sprints.rename_sprint(sid, "   ")
    reg_path = data_dir() / "sprints.json"
    assert json.loads(reg_path.read_text()) == {}


def test_next_prev_of(xdg_tmp: Path) -> None:
    a = sprints.Sprint(id="2026-05-01T00:00:00", name="A")
    b = sprints.Sprint(id="2026-06-01T00:00:00", name="B")
    c = sprints.Sprint(id="2026-07-01T00:00:00", name="C")
    lst = [a, b, c]
    assert sprints.next_of(a.id, lst) == b
    assert sprints.next_of(c.id, lst) is None
    assert sprints.next_of(None, lst) == a
    assert sprints.prev_of(b.id, lst) == a
    assert sprints.prev_of(a.id, lst) is None
    assert sprints.prev_of(None, lst) is None
    assert sprints.next_of(a.id, []) is None


def test_bootstrap_assigns_orphans_to_one_id(xdg_tmp: Path) -> None:
    notes.write_atomic("a", "alpha")
    notes.write_atomic("b", "bravo")
    notes.write_atomic("c", "charlie")
    sid = sprints.bootstrap_existing()
    assert sid is not None
    assert notes.get_sprint("a") == sid
    assert notes.get_sprint("b") == sid
    assert notes.get_sprint("c") == sid


def test_bootstrap_reuses_existing_sprint(xdg_tmp: Path) -> None:
    notes.write_task("a", {"sprint": "2026-05-01T00:00:00"}, "")
    notes.write_atomic("b", "no frontmatter yet")
    sid = sprints.bootstrap_existing()
    # Orphan adopted the most recent existing sprint.
    assert sid == "2026-05-01T00:00:00"
    assert notes.get_sprint("b") == "2026-05-01T00:00:00"


def test_bootstrap_idempotent_when_all_sprinted(xdg_tmp: Path) -> None:
    notes.write_task("a", {"sprint": "2026-05-01T00:00:00"}, "")
    assert sprints.bootstrap_existing() is None


def test_bootstrap_no_tasks_is_noop(xdg_tmp: Path) -> None:
    assert sprints.bootstrap_existing() is None


def test_registry_with_garbage_is_ignored(xdg_tmp: Path) -> None:
    (data_dir()).mkdir(parents=True, exist_ok=True)
    (data_dir() / "sprints.json").write_text("not json")
    notes.write_task("t", {"sprint": "2026-05-22T18:30:45"}, "")
    out = sprints.list_existing()
    # Falls back to default name silently.
    assert out[0].name == "2026-05-22"
