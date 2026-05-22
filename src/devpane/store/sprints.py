"""Sprint discovery and rename registry.

A sprint groups tasks. Identity is an ISO-8601 timestamp captured at the
moment the sprint comes into existence (typically: the first task is
created in it, or a task is migrated past the last existing sprint).

Sprints are **emergent** from task frontmatter — the canonical list is
computed by scanning every task's ``sprint:`` field. No sprint record
exists if no task references it.

A small JSON registry at ``$XDG_DATA_HOME/devpane/sprints.json`` stores
**rename overrides only**. Missing entries fall back to a date-derived
default name (``YYYY-MM-DD``). The registry is therefore optional —
delete it and you only lose names, not sprint membership.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from dataclasses import dataclass

from devpane.store import notes
from devpane.store.paths import data_dir

_log = logging.getLogger(__name__)

_REGISTRY_FILENAME = "sprints.json"


@dataclass(frozen=True)
class Sprint:
    """A sprint, materialized for the UI."""

    id: str        # ISO timestamp, e.g. "2026-05-22T18:30:45"
    name: str      # display name (rename override or date-derived default)


def new_sprint_id(now: datetime.datetime | None = None) -> str:
    """Mint a fresh sprint id from the current time (or an injected one)."""
    if now is None:
        now = datetime.datetime.now()
    return now.replace(microsecond=0).isoformat()


def default_name_for(sprint_id: str) -> str:
    """Default display name = the date portion of the id (``YYYY-MM-DD``)."""
    # IDs are produced by ``new_sprint_id`` so the date is always the first
    # 10 chars. Guard against truncated/garbled values just in case.
    if len(sprint_id) >= 10:
        return sprint_id[:10]
    return sprint_id


# ---- rename registry -----------------------------------------------------


def _registry_path() -> str:
    return str(data_dir() / _REGISTRY_FILENAME)


def _load_registry() -> dict[str, str]:
    path = _registry_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("sprints: failed to read registry (%s); ignoring", e)
        return {}
    if not isinstance(data, dict):
        return {}
    # Coerce to {str: str}; drop garbage entries silently.
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _save_registry(reg: dict[str, str]) -> None:
    path = _registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def rename_sprint(sprint_id: str, new_name: str) -> None:
    """Persist a display-name override. Empty name removes the override."""
    reg = _load_registry()
    name = new_name.strip()
    if name and name != default_name_for(sprint_id):
        reg[sprint_id] = name
    else:
        reg.pop(sprint_id, None)
    _save_registry(reg)


def name_for(sprint_id: str, registry: dict[str, str] | None = None) -> str:
    reg = registry if registry is not None else _load_registry()
    return reg.get(sprint_id) or default_name_for(sprint_id)


# ---- discovery & navigation ----------------------------------------------


def list_existing() -> list[Sprint]:
    """Return all sprints emergent from task frontmatter, chronologically.

    Tasks without a ``sprint:`` field are ignored here — callers should
    have already run :func:`bootstrap_existing` so every task on disk
    carries a sprint id.
    """
    ids: set[str] = set()
    for name in notes.list_notes():
        try:
            sid = notes.get_sprint(name)
        except OSError:
            continue
        if sid:
            ids.add(sid)
    reg = _load_registry()
    return [Sprint(id=sid, name=name_for(sid, reg)) for sid in sorted(ids)]


def next_of(current_id: str | None, sprints: list[Sprint]) -> Sprint | None:
    if not sprints:
        return None
    if current_id is None:
        return sprints[0]
    for i, s in enumerate(sprints):
        if s.id == current_id and i + 1 < len(sprints):
            return sprints[i + 1]
    return None


def prev_of(current_id: str | None, sprints: list[Sprint]) -> Sprint | None:
    if not sprints or current_id is None:
        return None
    for i, s in enumerate(sprints):
        if s.id == current_id and i > 0:
            return sprints[i - 1]
    return None


# ---- bootstrap -----------------------------------------------------------


def bootstrap_existing() -> str | None:
    """Assign a sprint to any task that lacks one.

    Idempotent. If at least one un-sprinted task exists, mints a single
    new sprint id (or reuses the latest existing one, see below) and
    writes it to every un-sprinted file's frontmatter.

    Behavior:

    - All un-sprinted tasks share one id, so the user lands in a single
      "legacy" sprint rather than as many sprints as there are files.
    - If sprints already exist, the most recent one is reused (so a
      fresh install with both old and new tasks doesn't create a second
      "today" sprint right next to the existing one).

    Returns the id written, or ``None`` if nothing needed bootstrapping.
    """
    orphans: list[str] = []
    existing_ids: set[str] = set()
    for n in notes.list_notes():
        try:
            sid = notes.get_sprint(n)
        except OSError:
            continue
        if sid:
            existing_ids.add(sid)
        else:
            orphans.append(n)
    if not orphans:
        return None
    target_id = max(existing_ids) if existing_ids else new_sprint_id()
    for n in orphans:
        try:
            notes.set_sprint(n, target_id)
        except OSError as e:
            _log.warning("sprints: bootstrap failed for %s (%s)", n, e)
    _log.info("sprints: bootstrapped %d task(s) into %s", len(orphans), target_id)
    return target_id
