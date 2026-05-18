"""Shared fixtures. Redirect XDG dirs into per-test tmp paths so the suite
never touches the user's real DevPane state."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def xdg_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point all XDG_* env vars at a fresh tmp dir for the duration of a test."""
    for sub, env in [
        ("data", "XDG_DATA_HOME"),
        ("state", "XDG_STATE_HOME"),
        ("runtime", "XDG_RUNTIME_DIR"),
        ("config", "XDG_CONFIG_HOME"),
        ("cache", "XDG_CACHE_HOME"),
    ]:
        p = tmp_path / sub
        p.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(env, str(p))
    yield tmp_path
