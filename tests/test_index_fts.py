"""Tests for the SQLite + FTS5 index."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from devpane.store import index, notes


@pytest.fixture
def conn(xdg_tmp: Path) -> Iterator[object]:
    c = index.connect()
    try:
        yield c
    finally:
        c.close()  # type: ignore[attr-defined]


def test_migrations_applied(conn) -> None:  # type: ignore[no-untyped-def]
    rows = list(conn.execute("SELECT name FROM schema_migrations ORDER BY name"))
    assert [r[0] for r in rows] == ["0001_init.sql"]


def test_migrations_idempotent(xdg_tmp: Path) -> None:
    c1 = index.connect()
    c1.close()
    c2 = index.connect()
    rows = list(c2.execute("SELECT count(*) FROM schema_migrations"))
    c2.close()
    assert rows[0][0] == 1


def test_touch_and_search(conn) -> None:  # type: ignore[no-untyped-def]
    notes.write_atomic("alpha", "the quick brown fox")
    notes.write_atomic("beta", "lazy dog jumps")
    index.touch(conn, "alpha")
    index.touch(conn, "beta")

    hits = index.search(conn, "quick")
    assert [r["name"] for r in hits] == ["alpha.md"]
    assert "[quick]" in hits[0]["snippet"]

    hits2 = index.search(conn, "dog OR fox")
    names = {r["name"] for r in hits2}
    assert names == {"alpha.md", "beta.md"}


def test_touch_upserts(conn) -> None:  # type: ignore[no-untyped-def]
    notes.write_atomic("n", "first")
    index.touch(conn, "n")
    notes.write_atomic("n", "second revision")
    index.touch(conn, "n")
    assert [r["name"] for r in index.search(conn, "revision")] == ["n.md"]
    assert index.search(conn, "first") == []


def test_remove(conn) -> None:  # type: ignore[no-untyped-def]
    notes.write_atomic("n", "delete me")
    index.touch(conn, "n")
    index.remove(conn, "n.md")
    assert index.search(conn, "delete") == []


def test_reindex_all(conn) -> None:  # type: ignore[no-untyped-def]
    for name, body in [("a", "apple"), ("b", "banana"), ("c", "cherry")]:
        notes.write_atomic(name, body)
    count = index.reindex_all(conn)
    assert count == 3
    assert {r["name"] for r in index.search(conn, "apple OR banana OR cherry")} == {
        "a.md",
        "b.md",
        "c.md",
    }


def test_recent_orders_by_updated_at(conn) -> None:  # type: ignore[no-untyped-def]
    import time

    notes.write_atomic("old", "x")
    index.touch(conn, "old")
    time.sleep(1.1)  # CURRENT_TIMESTAMP has 1s resolution
    notes.write_atomic("new", "y")
    index.touch(conn, "new")
    rec = [r["name"] for r in index.recent(conn)]
    assert rec[0] == "new.md"


def test_pinned_sorts_first(conn) -> None:  # type: ignore[no-untyped-def]
    notes.write_atomic("a", "x")
    notes.write_atomic("b", "y")
    index.touch(conn, "a")
    index.touch(conn, "b")
    index.set_pinned(conn, "a.md", True)
    rec = [r["name"] for r in index.recent(conn)]
    assert rec[0] == "a.md"
