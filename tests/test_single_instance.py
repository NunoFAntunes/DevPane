"""Tests for the single-instance guard."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from devpane.daemon import single_instance


def test_acquire_lock_releases_on_exit(tmp_path: Path) -> None:
    pidfile = tmp_path / "devpane.pid"
    with single_instance.acquire_lock(pidfile):
        assert pidfile.exists()
    assert not pidfile.exists()


def test_second_acquire_raises(tmp_path: Path) -> None:
    pidfile = tmp_path / "devpane.pid"
    # Fork a child that holds the lock, then try to acquire in the parent.
    # Simpler: re-acquire in same process — flock is per-process, so we need
    # a separate fd. We achieve this with a subprocess.
    import subprocess
    import sys
    import textwrap
    import time

    script = textwrap.dedent(
        f"""
        import sys, time
        sys.path.insert(0, {str(Path(__file__).resolve().parent.parent / "src")!r})
        from devpane.daemon.single_instance import acquire_lock
        from pathlib import Path
        with acquire_lock(Path({str(pidfile)!r})):
            print("HOLD", flush=True)
            time.sleep(2)
        """
    )
    p = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Wait until the child reports it has the lock.
        assert p.stdout is not None
        line = p.stdout.readline().strip()
        assert line == "HOLD"
        with pytest.raises(single_instance.AlreadyRunning):
            with single_instance.acquire_lock(pidfile):
                pass
    finally:
        p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()
    # After the holder exits, we should be able to acquire again.
    time.sleep(0.05)
    with single_instance.acquire_lock(pidfile):
        pass


@pytest.mark.asyncio
async def test_probe_false_when_socket_missing(tmp_path: Path) -> None:
    assert await single_instance.probe(tmp_path / "missing.sock") is False


@pytest.mark.asyncio
async def test_probe_true_when_server_listening(tmp_path: Path) -> None:
    from devpane.daemon.ipc import IPCServer

    server = IPCServer(tmp_path / "s.sock", {})
    await server.start()
    serve = asyncio.create_task(server.serve_forever())
    try:
        assert await single_instance.probe(server.socket_path) is True
    finally:
        await server.stop()
        serve.cancel()


def test_send_sync_raises_when_no_daemon(tmp_path: Path) -> None:
    with pytest.raises(ConnectionError):
        single_instance.send_sync(tmp_path / "nope.sock", "toggle")
