"""Tests for the devpane-toggle CLI client."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _run_toggle(
    env: dict[str, str], *args: str, timeout: float = 10.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "devpane.cli.toggle", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_toggle_spawns_daemon_when_missing(xdg_tmp: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent / "src")

    from devpane.daemon.single_instance import send_sync
    from devpane.store import paths

    sock = paths.socket_path()
    assert not sock.exists()
    try:
        result = _run_toggle(env, "toggle", "--json")
        assert result.returncode == 0, result.stderr
        assert sock.exists()
        body = json.loads(result.stdout)
        assert body["ok"] is True
        assert body["data"]["visible"] is True
    finally:
        if sock.exists():
            try:
                send_sync(sock, "quit", timeout=1.0)
            except ConnectionError:
                pass
            deadline = time.monotonic() + 3.0
            while sock.exists() and time.monotonic() < deadline:
                time.sleep(0.02)


def test_toggle_no_spawn_returns_error(xdg_tmp: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent / "src")
    result = _run_toggle(env, "toggle", "--no-spawn")
    assert result.returncode == 1
    assert "no daemon" in result.stderr
