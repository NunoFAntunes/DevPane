"""Filesystem-of-record for DevPane notes.

Notes live as plain ``.md`` files under ``notes_dir()``. Writes are atomic
via ``os.replace`` so a crashed daemon never leaves a partially-written file.
The filesystem is authoritative; the SQLite index is a derived cache.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from devpane.store.paths import notes_dir

DEFAULT_NOTE = "scratch.md"

# Allow letters, digits, underscore, hyphen, dot in the stem. No directory
# separators, no leading dots, no spaces — keeps shell/grep ergonomics clean.
_STEM_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


class InvalidNoteName(ValueError):
    """Raised when a note name fails validation."""


def canonical_name(name: str) -> str:
    """Validate and normalize a note name to its on-disk form (``<stem>.md``)."""
    if not name.endswith(".md"):
        name = f"{name}.md"
    stem = name[:-3]
    if not stem or not _STEM_RE.match(stem):
        raise InvalidNoteName(name)
    return name


def path_for(name: str) -> Path:
    return notes_dir() / canonical_name(name)


def exists(name: str) -> bool:
    return path_for(name).is_file()


def list_notes() -> list[str]:
    """Return sorted note filenames. Does not create files (see ``ensure_default``)."""
    d = notes_dir()
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix == ".md")


def ensure_default() -> str:
    """Create the default scratch note if no notes exist; return its name."""
    if not list_notes():
        write_atomic(DEFAULT_NOTE, "")
    return DEFAULT_NOTE


def read(name: str) -> str:
    return path_for(name).read_text(encoding="utf-8")


def write_atomic(name: str, body: str) -> None:
    """Write ``body`` to the note ``name`` atomically.

    Uses a same-directory temp file + ``os.replace`` so the rename is atomic
    on POSIX. Calls ``fsync`` before the rename to bound data loss on power
    failure to whatever the autosave debounce window allows.
    """
    target = path_for(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp = Path(tmp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def delete(name: str) -> None:
    path_for(name).unlink(missing_ok=True)


def mtime(name: str) -> float:
    return path_for(name).stat().st_mtime
