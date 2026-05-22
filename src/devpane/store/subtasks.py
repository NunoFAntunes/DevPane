"""Per-task subtask sidecars.

Each task ``<stem>.md`` may have a companion subtask file at
``$XDG_DATA_HOME/devpane/subtasks/<stem>.json`` holding an ordered list
of ``{text, done}`` items. Missing file = no subtasks; this matches the
"filesystem is authoritative, derived state is rebuildable" principle.

The whole list is rewritten on every mutation. Subtask data is tiny
(usually fewer than a few dozen items per task) so atomic full-file
writes are simpler than tracking diffs.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from devpane.store import notes
from devpane.store.paths import subtasks_dir

_log = logging.getLogger(__name__)


@dataclass
class Subtask:
    text: str
    done: bool = False


def path_for(task_name: str) -> Path:
    """Return the sidecar path for a task. Validates the task name."""
    canon = notes.canonical_name(task_name)
    stem = canon[:-3]
    return subtasks_dir() / f"{stem}.json"


def load(task_name: str) -> list[Subtask]:
    """Load subtasks for ``task_name``. Missing or malformed → ``[]``."""
    path = path_for(task_name)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("subtasks: failed to read %s (%s); treating as empty", path, e)
        return []
    if not isinstance(raw, list):
        return []
    out: list[Subtask] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        done = item.get("done", False)
        if isinstance(text, str):
            out.append(Subtask(text=text, done=bool(done)))
    return out


def save(task_name: str, items: list[Subtask]) -> None:
    """Atomically write ``items`` for ``task_name``. Empty list removes the file."""
    path = path_for(task_name)
    if not items:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump([asdict(i) for i in items], f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def delete_for(task_name: str) -> None:
    """Remove the sidecar (idempotent). Call when the parent task is deleted."""
    with contextlib.suppress(notes.InvalidNoteName):
        path_for(task_name).unlink(missing_ok=True)


def progress(task_name: str) -> tuple[int, int]:
    """Return ``(done_count, total_count)``. ``(0, 0)`` when no subtasks."""
    items = load(task_name)
    if not items:
        return (0, 0)
    done = sum(1 for i in items if i.done)
    return (done, len(items))
