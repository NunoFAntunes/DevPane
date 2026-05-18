"""End-to-end: spawn the real daemon as a subprocess and talk to it."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from devpane.daemon.single_instance import send_sync


def _spawn_daemon(env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-m", "devpane", "--headless", "--log-level", "DEBUG"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _wait_for_socket(p: Path, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if p.exists():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def daemon(xdg_tmp: Path) -> Iterator[Path]:
    env = os.environ.copy()
    for var in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
        env[var] = os.environ[var]  # set by xdg_tmp fixture
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent / "src")

    from devpane.store import paths

    sock = paths.socket_path()
    proc = _spawn_daemon(env)
    try:
        if not _wait_for_socket(sock):
            stdout, stderr = proc.communicate(timeout=2)
            pytest.fail(f"daemon did not bind socket\nstdout:{stdout!r}\nstderr:{stderr!r}")
        yield sock
    finally:
        try:
            send_sync(sock, "quit", timeout=1.0)
        except ConnectionError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=2)


def test_status_returns_version_and_zero_notes(daemon: Path) -> None:
    from devpane import __version__

    resp = send_sync(daemon, "status")
    assert resp["ok"] is True
    data = resp["data"]
    assert data["version"] == __version__
    assert data["visible"] is False
    assert data["notes"] == 0


def test_toggle_flips_visibility(daemon: Path) -> None:
    a = send_sync(daemon, "toggle")
    b = send_sync(daemon, "toggle")
    assert a["data"]["visible"] is True
    assert b["data"]["visible"] is False


def test_show_then_hide(daemon: Path) -> None:
    assert send_sync(daemon, "show")["data"]["visible"] is True
    assert send_sync(daemon, "hide")["data"]["visible"] is False


def test_socket_disappears_on_clean_exit(daemon: Path) -> None:
    assert daemon.exists()
    send_sync(daemon, "quit", timeout=1.0)
    # Daemon shuts down asynchronously; give it a moment.
    deadline = time.monotonic() + 3.0
    while daemon.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not daemon.exists()


def test_second_daemon_forwards_toggle(xdg_tmp: Path) -> None:
    """Running `devpaned` a second time should toggle the running peer."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent / "src")

    from devpane.store import paths

    sock = paths.socket_path()
    primary = _spawn_daemon(env)
    try:
        assert _wait_for_socket(sock)
        # baseline: not visible
        assert send_sync(sock, "status")["data"]["visible"] is False
        # second invocation should forward a toggle and exit
        second = subprocess.run(
            [sys.executable, "-m", "devpane", "--headless"],
            env=env,
            capture_output=True,
            timeout=5,
        )
        assert second.returncode == 0
        assert send_sync(sock, "status")["data"]["visible"] is True
    finally:
        try:
            send_sync(sock, "quit", timeout=1.0)
        except ConnectionError:
            pass
        try:
            primary.wait(timeout=3)
        except subprocess.TimeoutExpired:
            primary.terminate()
            primary.wait(timeout=2)
