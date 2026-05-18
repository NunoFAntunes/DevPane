"""XDG path resolution for DevPane data, state, and runtime files.

All getters are pure: they read environment variables on each call so tests
can override `XDG_*` via monkeypatching without process restart.
"""

from __future__ import annotations

import os
from pathlib import Path

_APP = "devpane"


def _xdg(env: str, default: Path) -> Path:
    value = os.environ.get(env)
    return Path(value) if value else default


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / _APP


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", Path.home() / ".local" / "state") / _APP


def runtime_dir() -> Path:
    # XDG_RUNTIME_DIR is owned by the user with 0700 under systemd.
    # Fall back to /tmp/devpane-<uid> if absent (e.g. CI containers).
    val = os.environ.get("XDG_RUNTIME_DIR")
    if val:
        return Path(val) / _APP
    return Path(f"/tmp/{_APP}-{os.getuid()}")


def notes_dir() -> Path:
    return data_dir() / "notes"


def index_path() -> Path:
    return data_dir() / "index.sqlite"


def socket_path() -> Path:
    return runtime_dir() / "devpane.sock"


def log_path() -> Path:
    return state_dir() / "devpane.log"


def ensure_dirs() -> None:
    """Create all DevPane directories with appropriate permissions."""
    notes_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)
    rt = runtime_dir()
    rt.mkdir(parents=True, exist_ok=True)
    os.chmod(rt, 0o700)
