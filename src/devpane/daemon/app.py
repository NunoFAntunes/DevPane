"""Daemon entry point.

Two execution modes:

- **gtk** — full GUI. Main thread runs `Adw.Application`; asyncio runs on a
  worker thread and routes window commands through a `GtkController`.
- **headless** — no display. The whole daemon runs on a single asyncio
  loop with a `HeadlessController` that only flips an in-memory flag.

Mode resolution:

1. ``--headless`` CLI flag → headless.
2. ``--gtk`` CLI flag → gtk (error if unavailable).
3. ``DEVPANE_HEADLESS=1`` env → headless.
4. Otherwise: auto — gtk if a display is detected, headless otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
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
from devpane.platform.detect import detect, has_display
from devpane.store import notes, paths
from devpane.ui.controller import HeadlessController, WindowController
from devpane.util.logging import setup as setup_logging
from devpane.version import __version__

_log = logging.getLogger("devpane.daemon")

MODE_AUTO = "auto"
MODE_GTK = "gtk"
MODE_HEADLESS = "headless"


class Daemon:
    """IPC server + lifecycle owner. Mode-agnostic; takes a controller."""

    def __init__(self, socket_path: Path | None = None) -> None:
        self._socket_path = socket_path or paths.socket_path()
        self._controller: WindowController | None = None

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def serve(self, controller: WindowController, stop_event: asyncio.Event) -> int:
        """Run the IPC server until ``stop_event`` is set. Returns 0 on clean exit."""
        self._controller = controller
        ipc = IPCServer(self._socket_path, self._handlers(stop_event))
        await ipc.start()
        _log.info(
            "daemon ready (pid=%d, mode=%s)",
            os.getpid(),
            "gtk" if not isinstance(controller, HeadlessController) else "headless",
        )
        try:
            serve_task = asyncio.create_task(ipc.serve_forever())
            stop_task = asyncio.create_task(stop_event.wait())
            _, pending = await asyncio.wait(
                {serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
        finally:
            await ipc.stop()
            _log.info("daemon stopped")
        return 0

    # ---- handlers ----

    def _handlers(self, stop_event: asyncio.Event) -> dict[str, Any]:
        async def on_toggle(_req: Request) -> Response:
            assert self._controller is not None
            visible = await self._controller.toggle()
            _log.info("toggle → visible=%s", visible)
            return ok({"visible": visible})

        async def on_show(_req: Request) -> Response:
            assert self._controller is not None
            visible = await self._controller.show()
            _log.info("show")
            return ok({"visible": visible})

        async def on_hide(_req: Request) -> Response:
            assert self._controller is not None
            visible = await self._controller.hide()
            _log.info("hide")
            return ok({"visible": visible})

        async def on_status(_req: Request) -> Response:
            assert self._controller is not None
            return ok(
                {
                    "version": __version__,
                    "visible": self._controller.is_visible(),
                    "notes": len(notes.list_notes()),
                    "pid": os.getpid(),
                    "socket": str(self._socket_path),
                }
            )

        async def on_quit(_req: Request) -> Response:
            _log.info("quit requested")
            stop_event.set()
            return ok()

        return {
            CMD_TOGGLE: on_toggle,
            CMD_SHOW: on_show,
            CMD_HIDE: on_hide,
            CMD_STATUS: on_status,
            CMD_QUIT: on_quit,
        }


def _resolve_mode(cli_mode: str) -> str:
    if cli_mode in (MODE_GTK, MODE_HEADLESS):
        return cli_mode
    if os.environ.get("DEVPANE_HEADLESS"):
        return MODE_HEADLESS
    return MODE_GTK if has_display() else MODE_HEADLESS


def _run_headless(daemon: Daemon) -> int:
    async def amain() -> int:
        controller = HeadlessController()
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, stop_event.set)
        return await daemon.serve(controller, stop_event)

    return asyncio.run(amain())


def _run_gtk(daemon: Daemon) -> int:
    # Layer-shell requires LD_PRELOAD-ing libgtk4-layer-shell.so before any
    # GTK or Wayland code is touched. If we're not already preloaded, this
    # re-execs the process and never returns.
    from devpane.platform.layer_shell_preload import ensure_preloaded

    ensure_preloaded()

    try:
        from devpane.ui.gtk_app import run_gtk
    except (ImportError, ValueError) as e:
        _log.error("GTK mode unavailable (%s); falling back to headless", e)
        return _run_headless(daemon)
    return run_gtk(daemon.serve)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devpaned",
        description="DevPane background daemon — owns the drop-down pane.",
    )
    parser.add_argument("--version", action="version", version=f"devpaned {__version__}")
    parser.add_argument("--check", action="store_true", help="Run a self-check and exit.")
    parser.add_argument("--log-level", default=None, help="Override DEVPANE_LOG_LEVEL.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--gtk", action="store_const", dest="mode", const=MODE_GTK)
    mode_group.add_argument("--headless", action="store_const", dest="mode", const=MODE_HEADLESS)
    parser.set_defaults(mode=MODE_AUTO)
    args = parser.parse_args(argv)

    setup_logging(args.log_level)

    if args.check:
        paths.ensure_dirs()
        info = detect()
        print(f"devpaned {__version__}: skeleton OK")
        print(f"  socket:      {paths.socket_path()}")
        print(f"  notes:       {paths.notes_dir()}")
        print(f"  session:     {info.session.value}")
        print(f"  compositor:  {info.compositor.value}")
        print(f"  layer-shell: {'yes' if info.has_layer_shell else 'no'}")
        return 0

    paths.ensure_dirs()
    pidfile = paths.runtime_dir() / "devpane.pid"

    try:
        with single_instance.acquire_lock(pidfile):
            resolved_mode = _resolve_mode(args.mode)
            _log.info("starting daemon in %s mode", resolved_mode)
            daemon = Daemon()
            if resolved_mode == MODE_GTK:
                return _run_gtk(daemon)
            return _run_headless(daemon)
    except single_instance.AlreadyRunning:
        forwarded = asyncio.run(single_instance.forward_toggle(paths.socket_path()))
        if forwarded:
            _log.info("another daemon is running; forwarded toggle")
            return 0
        _log.error("another daemon holds the lock but isn't responding")
        return 1


if __name__ == "__main__":
    sys.exit(main())
