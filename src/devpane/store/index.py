"""SQLite + FTS5 index over the notes filesystem.

The index is a *derived* store: it can be deleted and rebuilt from disk via
``reindex_all`` at any time, so a corrupt index never blocks the user. The
daemon owns a single connection and runs on a single thread (asyncio); do
not share a connection across threads.
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from devpane.store import notes
from devpane.store.paths import index_path

_MIGRATIONS_PKG = "devpane.store.migrations"
_SCHEMA_TABLE = "schema_migrations"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (or create) the index database and run any pending migrations."""
    p = path or index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    return conn


def _applied(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_SCHEMA_TABLE} ("
        "  name TEXT PRIMARY KEY,"
        "  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    return {row[0] for row in conn.execute(f"SELECT name FROM {_SCHEMA_TABLE}")}


def _migrate(conn: sqlite3.Connection) -> None:
    applied = _applied(conn)
    files = sorted(
        (f for f in resources.files(_MIGRATIONS_PKG).iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    for f in files:
        if f.name in applied:
            continue
        sql = f.read_text(encoding="utf-8")
        with conn:
            conn.executescript(sql)
            conn.execute(f"INSERT INTO {_SCHEMA_TABLE}(name) VALUES (?)", (f.name,))


def touch(conn: sqlite3.Connection, name: str, body: str | None = None) -> None:
    """Upsert a note row, refreshing ``updated_at``. Reads from disk if ``body`` is None."""
    canon = notes.canonical_name(name)
    if body is None:
        body = notes.read(canon)
    with conn:
        conn.execute(
            "INSERT INTO notes(name, body) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "  body = excluded.body, "
            "  updated_at = CURRENT_TIMESTAMP",
            (canon, body),
        )


def remove(conn: sqlite3.Connection, name: str) -> None:
    with conn:
        conn.execute("DELETE FROM notes WHERE name = ?", (notes.canonical_name(name),))


def reindex_all(conn: sqlite3.Connection) -> int:
    """Drop all index rows and re-populate from the filesystem. Returns row count."""
    with conn:
        conn.execute("DELETE FROM notes")
    count = 0
    for name in notes.list_notes():
        touch(conn, name)
        count += 1
    return count


def search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[sqlite3.Row]:
    """Full-text search. ``query`` follows FTS5 syntax."""
    return list(
        conn.execute(
            "SELECT n.name AS name, "
            "       snippet(notes_fts, 1, '[', ']', '…', 12) AS snippet, "
            "       n.updated_at AS updated_at "
            "FROM notes_fts "
            "JOIN notes n ON n.rowid = notes_fts.rowid "
            "WHERE notes_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        )
    )


def recent(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT name, updated_at, pinned FROM notes "
            "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
            (limit,),
        )
    )


def set_pinned(conn: sqlite3.Connection, name: str, pinned: bool) -> None:
    canon = notes.canonical_name(name)
    with conn:
        conn.execute("UPDATE notes SET pinned = ? WHERE name = ?", (1 if pinned else 0, canon))
