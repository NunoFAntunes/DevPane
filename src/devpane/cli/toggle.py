"""`devpane-toggle` — tiny IPC client.

Sends a single JSON-line command to the running daemon and prints the
response. If no daemon is reachable, optionally spawns one and retries.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from devpane.daemon.single_instance import send_sync
from devpane.store import paths
from devpane.version import __version__

_SPAWN_TIMEOUT_S = 3.0
_SPAWN_POLL_S = 0.05


def _spawn_daemon() -> None:
    """Fork a detached daemon process. The parent returns immediately."""
    devnull = open(os.devnull, "rb+")  # noqa: SIM115 — handed to subprocess
    subprocess.Popen(
        [sys.executable, "-m", "devpane"],
        stdin=devnull,
        stdout=devnull,
        stderr=devnull,
        close_fds=True,
        start_new_session=True,
    )


def _wait_for_socket(socket: Path, timeout_s: float = _SPAWN_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if socket.exists():
            return True
        time.sleep(_SPAWN_POLL_S)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devpane-toggle",
        description="Toggle the DevPane drop-down. Bind this to a key in your DE.",
    )
    parser.add_argument("--version", action="version", version=f"devpane-toggle {__version__}")
    parser.add_argument(
        "cmd",
        nargs="?",
        default="toggle",
        choices=["toggle", "show", "hide", "status", "quit"],
        help="Command to send to the daemon (default: toggle).",
    )
    parser.add_argument(
        "--no-spawn",
        action="store_true",
        help="Do not start the daemon if it is not running.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw JSON response (default: human-friendly summary).",
    )
    args = parser.parse_args(argv)

    socket = paths.socket_path()

    try:
        response = send_sync(socket, args.cmd)
    except ConnectionError:
        if args.no_spawn:
            print(f"devpane-toggle: no daemon at {socket}", file=sys.stderr)
            return 1
        _spawn_daemon()
        if not _wait_for_socket(socket):
            print(
                f"devpane-toggle: spawned daemon did not open {socket} within "
                f"{_SPAWN_TIMEOUT_S:.0f}s",
                file=sys.stderr,
            )
            return 1
        try:
            response = send_sync(socket, args.cmd)
        except ConnectionError as e:
            print(f"devpane-toggle: {e}", file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps(response))
    else:
        _print_summary(args.cmd, response)
    return 0 if response.get("ok") else 2


def _print_summary(cmd: str, response: dict[str, Any]) -> None:
    if not response.get("ok"):
        print(f"devpane-toggle: error: {response.get('error', 'unknown')}", file=sys.stderr)
        return
    data: dict[str, Any] = response.get("data") or {}
    if cmd == "status":
        for k, v in data.items():
            print(f"{k}: {v}")
    elif "visible" in data:
        print(f"visible: {data['visible']}")


if __name__ == "__main__":
    sys.exit(main())
