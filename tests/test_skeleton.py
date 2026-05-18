"""Smoke tests for the M0 skeleton."""

from __future__ import annotations

import subprocess
import sys

import pytest

import devpane
from devpane.cli import toggle
from devpane.daemon import app


def test_version_string() -> None:
    assert devpane.__version__
    assert isinstance(devpane.__version__, str)


def test_daemon_main_runs() -> None:
    assert app.main(["--check"]) == 0


def test_toggle_main_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("devpane.cli.toggle.send_sync", lambda *_a, **_kw: {"ok": True, "data": {}})
    assert toggle.main(["status"]) == 0


def test_daemon_version_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "devpane", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "devpaned" in result.stdout
