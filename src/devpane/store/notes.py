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


# ---- task frontmatter ----------------------------------------------------
#
# Tasks are notes with an optional YAML-like header delimited by ``---``
# lines. Only flat ``key: value`` scalars are supported — enough for the
# fields we need (``title``, ``done``, ``created``) and small enough to
# parse without pulling in PyYAML.
#
# A note without a frontmatter block is a perfectly valid task: it reads
# as ``({}, full_text)`` and displays with the filename stem as title.

_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") and text != "---" and not text.startswith("---\r\n"):
        return {}, text
    # Normalize line endings just for the split — we keep the body verbatim
    # after locating the closing marker by offset in the original text.
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
        m = _FM_KEY_RE.match(lines[i])
        if m is None:
            # Malformed frontmatter — treat as no frontmatter.
            return {}, text
        key, value = m.group(1), m.group(2).strip()
        # Strip optional surrounding quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        meta[key] = value
    if end_idx is None:
        return {}, text
    body = "\n".join(lines[end_idx + 1 :])
    return meta, body


def _serialize_frontmatter(meta: dict[str, str], body: str) -> str:
    if not meta:
        return body
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body


def read_task(name: str) -> tuple[dict[str, str], str]:
    """Return ``(meta, body)`` for a task note.

    Missing or malformed frontmatter yields ``({}, full_text)`` so plain
    pre-existing markdown files keep working unchanged.
    """
    return _parse_frontmatter(read(name))


def write_task(name: str, meta: dict[str, str], body: str) -> None:
    """Write ``meta`` + ``body`` atomically. Empty meta writes the body alone."""
    write_atomic(name, _serialize_frontmatter(meta, body))


def is_done(name: str) -> bool:
    meta, _ = read_task(name)
    return meta.get("done", "").lower() == "true"


def get_title(name: str) -> str:
    """Display title: ``meta['title']`` if set, else the filename stem."""
    meta, _ = read_task(name)
    title = meta.get("title", "").strip()
    if title:
        return title
    return canonical_name(name)[:-3]


def set_done(name: str, done: bool) -> None:
    meta, body = read_task(name)
    meta["done"] = "true" if done else "false"
    write_task(name, meta, body)


def set_title(name: str, title: str) -> None:
    meta, body = read_task(name)
    title = title.strip()
    if title:
        meta["title"] = title
    else:
        meta.pop("title", None)
    write_task(name, meta, body)


def mtime(name: str) -> float:
    return path_for(name).stat().st_mtime


def cleanup_orphans() -> int:
    """Remove leftover ``.<name>.<rand>.tmp`` files from crashed atomic writes.

    Atomic write uses ``tempfile.mkstemp`` + ``os.replace``; if the daemon
    is killed between flush and replace, the temp file is orphaned. The
    original note (if any) is untouched, so we just delete the orphans.
    Returns the number removed.
    """
    d = notes_dir()
    if not d.is_dir():
        return 0
    count = 0
    for p in d.iterdir():
        if not p.is_file():
            continue
        if p.name.startswith(".") and p.name.endswith(".tmp"):
            try:
                p.unlink()
                count += 1
            except OSError:
                pass
    return count
