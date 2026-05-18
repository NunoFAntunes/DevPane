"""User preferences persisted as JSON under ``$XDG_CONFIG_HOME/devpane``.

M6 stores only what the window needs across restarts: height ratio (so a
manual resize sticks) and the last-open note (so toggling restores
context). GSettings migration is planned for M7 once we have packaging.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

_FILENAME = "prefs.json"
_DEFAULT_HEIGHT_RATIO = 0.6


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "devpane"


def _prefs_path() -> Path:
    return config_dir() / _FILENAME


@dataclass
class Prefs:
    height_ratio: float = _DEFAULT_HEIGHT_RATIO
    last_note: str | None = None
    animate: bool = True

    @classmethod
    def load(cls) -> Prefs:
        path = _prefs_path()
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            _log.warning("prefs: failed to load %s (%s); using defaults", path, e)
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(
            height_ratio=_clamp_ratio(data.get("height_ratio", _DEFAULT_HEIGHT_RATIO)),
            last_note=data.get("last_note") if isinstance(data.get("last_note"), str) else None,
            animate=bool(data.get("animate", True)),
        )

    def save(self) -> None:
        path = _prefs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, path)


def _clamp_ratio(v: object) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _DEFAULT_HEIGHT_RATIO
    return max(0.2, min(0.95, f))
