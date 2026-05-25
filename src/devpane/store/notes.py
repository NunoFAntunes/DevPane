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
# fields we need (``title``, ``status``, ``tags``, ``created``) and small
# enough to parse without pulling in PyYAML. ``tags`` is encoded as a
# comma-separated string (``tags: bug, refactor``) so the scalar-only
# parser handles it without extension.
#
# A note without a frontmatter block is a perfectly valid task: it reads
# as ``({}, full_text)`` and displays with the filename stem as title.

_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")

# Task status: a four-valued enum stored as ``status: <value>`` in the
# frontmatter. Replaces the older boolean ``done:`` field; readers fall
# back to ``done`` when ``status`` is absent so pre-existing notes keep
# working without an upfront migration pass.
STATUS_TODO = "todo"
STATUS_DOING = "doing"
STATUS_BLOCKED = "blocked"
STATUS_DONE = "done"
STATUSES: tuple[str, ...] = (STATUS_TODO, STATUS_DOING, STATUS_BLOCKED, STATUS_DONE)
_STATUS_SET = frozenset(STATUSES)


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


def status_from_meta(meta: dict[str, str]) -> str:
    """Resolve a task's status, with lazy fallback to legacy ``done:``.

    Rules:

    - ``status`` field present and known → use it.
    - else ``done: "true"`` → ``done``; otherwise ``todo``.
    - unknown ``status`` string → ``todo`` (defensive).
    """
    raw = meta.get("status", "").strip().lower()
    if raw in _STATUS_SET:
        return raw
    if meta.get("done", "").strip().lower() == "true":
        return STATUS_DONE
    return STATUS_TODO


def get_status(name: str) -> str:
    meta, _ = read_task(name)
    return status_from_meta(meta)


def set_status(name: str, status: str) -> None:
    if status not in _STATUS_SET:
        raise ValueError(f"unknown status: {status!r}")
    meta, body = read_task(name)
    meta["status"] = status
    # Drop the legacy ``done:`` key so we don't carry two sources of truth
    # forward. This realises the "rewrite when next touched" half of the
    # lazy migration: untouched files keep ``done:``; mutated ones converge.
    meta.pop("done", None)
    write_task(name, meta, body)


def is_done(name: str) -> bool:
    return get_status(name) == STATUS_DONE


def get_title(name: str) -> str:
    """Display title: ``meta['title']`` if set, else the filename stem."""
    meta, _ = read_task(name)
    title = meta.get("title", "").strip()
    if title:
        return title
    return canonical_name(name)[:-3]


def set_done(name: str, done: bool) -> None:
    set_status(name, STATUS_DONE if done else STATUS_TODO)


# ---- tags -----------------------------------------------------------------
#
# Tags are a comma-separated string in the frontmatter (``tags: bug,
# refactor``). On read we split, strip, lowercase, drop empties, and dedupe
# preserving first-seen order. On write we serialise back to the same form.

def parse_tags(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        t = part.strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def get_tags(name: str) -> list[str]:
    meta, _ = read_task(name)
    return parse_tags(meta.get("tags", ""))


def set_tags(name: str, tags: list[str]) -> None:
    meta, body = read_task(name)
    normalised = parse_tags(", ".join(tags))
    if normalised:
        meta["tags"] = ", ".join(normalised)
    else:
        meta.pop("tags", None)
    write_task(name, meta, body)


def set_title(name: str, title: str) -> None:
    meta, body = read_task(name)
    title = title.strip()
    if title:
        meta["title"] = title
    else:
        meta.pop("title", None)
    write_task(name, meta, body)


def get_sprint(name: str) -> str | None:
    """Return the task's sprint id, or ``None`` if it has none."""
    meta, _ = read_task(name)
    sid = meta.get("sprint", "").strip()
    return sid or None


def set_sprint(name: str, sprint_id: str) -> None:
    """Move a task into ``sprint_id``. Empty/blank id removes the field."""
    meta, body = read_task(name)
    sid = sprint_id.strip()
    if sid:
        meta["sprint"] = sid
    else:
        meta.pop("sprint", None)
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
