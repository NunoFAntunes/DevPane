"""Daemon entry point and command dispatch.

For M2 the daemon has no UI yet — commands are accepted, logged, and
acknowledged. M3 will wire a hidden GTK4 window and toggle it from the
``toggle`` handler.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any

from devpane.daemon import single_instance
from devpane.daemon.ipc import IPCServer
from devpane.daemon.protocol import (
    CMD_HIDE,
    CMD_QUIT,
    CMD_SHOW,
    CMD_STATUS,
    CMD_TOGGLE,
    Request,
    Response,
    ok,
)
from devpane.store import notes, paths
from devpane.util.logging import setup as setup_logging
from devpane.version import __version__

_log = logging.getLogger("devpane.daemon")


class Daemon:
    """Lifecycle owner. Holds visibility state and routes commands."""

    def __init__(self, socket_path: Path | None = None) -> None:
        self._socket_path = socket_path or paths.socket_path()
        self._visible = False
        self._stop_event = asyncio.Event()
        self._ipc = IPCServer(
            self._socket_path,
            {
                CMD_TOGGLE: self._on_toggle,
                CMD_SHOW: self._on_show,
                CMD_HIDE: self._on_hide,
                CMD_STATUS: self._on_status,
                CMD_QUIT: self._on_quit,
            },
        )

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def run(self) -> int:
        await self._ipc.start()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop_event.set)
        _log.info("daemon ready (pid=%d, visible=%s)", __import__("os").getpid(), self._visible)
        try:
            serve_task = asyncio.create_task(self._ipc.serve_forever())
            stop_task = asyncio.create_task(self._stop_event.wait())
            _, pending = await asyncio.wait(
                {serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
        finally:
            await self._ipc.stop()
            _log.info("daemon stopped")
        return 0

    # ---- handlers ----

    async def _on_toggle(self, _req: Request) -> Response:
        self._visible = not self._visible
        _log.info("toggle → visible=%s", self._visible)
        return ok({"visible": self._visible})

    async def _on_show(self, _req: Request) -> Response:
        self._visible = True
        _log.info("show")
        return ok({"visible": True})

    async def _on_hide(self, _req: Request) -> Response:
        self._visible = False
        _log.info("hide")
        return ok({"visible": False})

    async def _on_status(self, _req: Request) -> Response:
        data: dict[str, Any] = {
            "version": __version__,
            "visible": self._visible,
            "notes": len(notes.list_notes()),
            "pid": __import__("os").getpid(),
            "socket": str(self._socket_path),
        }
        return ok(data)

    async def _on_quit(self, _req: Request) -> Response:
        _log.info("quit requested")
        self._stop_event.set()
        return ok()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devpaned",
        description="DevPane background daemon — owns the drop-down pane.",
    )
    parser.add_argument("--version", action="version", version=f"devpaned {__version__}")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run a self-check and exit.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Override DEVPANE_LOG_LEVEL (DEBUG, INFO, WARNING, ERROR).",
    )
    args = parser.parse_args(argv)

    setup_logging(args.log_level)

    if args.check:
        paths.ensure_dirs()
        print(f"devpaned {__version__}: skeleton OK")
        print(f"  socket: {paths.socket_path()}")
        print(f"  notes:  {paths.notes_dir()}")
        return 0

    paths.ensure_dirs()
    pidfile = paths.runtime_dir() / "devpane.pid"

    try:
        with single_instance.acquire_lock(pidfile):
            return asyncio.run(Daemon().run())
    except single_instance.AlreadyRunning:
        # A peer holds the lock. Forward a toggle so re-running `devpaned`
        # acts as a hotkey, then exit cleanly.
        socket = paths.socket_path()
        forwarded = asyncio.run(single_instance.forward_toggle(socket))
        if forwarded:
            _log.info("another daemon is running; forwarded toggle")
            return 0
        _log.error("another daemon holds the lock but isn't responding on %s", socket)
        return 1


if __name__ == "__main__":
    sys.exit(main())
