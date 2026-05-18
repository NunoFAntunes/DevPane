"""Tests for XDG path resolution."""

from __future__ import annotations

from pathlib import Path

from devpane.store import paths


def test_xdg_dirs_honored(xdg_tmp: Path) -> None:
    assert paths.data_dir() == xdg_tmp / "data" / "devpane"
    assert paths.notes_dir() == xdg_tmp / "data" / "devpane" / "notes"
    assert paths.index_path() == xdg_tmp / "data" / "devpane" / "index.sqlite"
    assert paths.state_dir() == xdg_tmp / "state" / "devpane"
    assert paths.runtime_dir() == xdg_tmp / "runtime" / "devpane"
    assert paths.socket_path() == xdg_tmp / "runtime" / "devpane" / "devpane.sock"


def test_ensure_dirs_creates_with_runtime_0700(xdg_tmp: Path) -> None:
    paths.ensure_dirs()
    assert paths.notes_dir().is_dir()
    assert paths.state_dir().is_dir()
    rt = paths.runtime_dir()
    assert rt.is_dir()
    mode = rt.stat().st_mode & 0o777
    assert mode == 0o700, f"runtime dir should be 0700, got {oct(mode)}"
