"""Single-instance enforcement.

The daemon serializes startup via an ``fcntl.flock`` advisory lock on a
pidfile in ``$XDG_RUNTIME_DIR/devpane/``. Concurrent startups race for the
lock; losers exit (optionally after forwarding a ``toggle`` to the winner).

Three states are possible when ``devpaned`` starts:

1. **No socket, no lock holder** — fresh start.
2. **Socket exists and a daemon answers** — a peer is alive; we forward a
   toggle and exit 0.
3. **Socket exists but no peer answers** — stale socket from a crashed
   daemon. ``IPCServer.start`` will remove and rebind it.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import fcntl
import json
import logging
import os
import socket as _socket
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


class AlreadyRunning(RuntimeError):
    """Raised when another daemon already holds the lock."""


@contextmanager
def acquire_lock(pidfile: Path) -> Iterator[int]:
    """Take an exclusive flock on ``pidfile``. Raises AlreadyRunning if held."""
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(pidfile, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            os.close(fd)
            raise AlreadyRunning(f"{pidfile} is locked by another daemon") from e
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        try:
            yield fd
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            pidfile.unlink(missing_ok=True)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise


async def probe(socket_path: Path, timeout: float = 0.5) -> bool:
    """Return True if a daemon is actively listening on the socket."""
    if not socket_path.exists():
        return False
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(str(socket_path)), timeout=timeout
        )
    except (TimeoutError, FileNotFoundError, ConnectionRefusedError, OSError):
        return False
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
    _ = reader
    return True


def send_sync(
    socket_path: Path, cmd: str, timeout: float = 2.0, **kwargs: object
) -> dict[str, Any]:
    """Synchronous one-shot client. Used by the CLI and by ``forward_toggle``.

    Returns the decoded response dict. Raises ``ConnectionError`` if the
    socket is missing or the daemon doesn't answer.
    """
    s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        try:
            s.connect(str(socket_path))
        except (FileNotFoundError, ConnectionRefusedError) as e:
            raise ConnectionError(f"no daemon at {socket_path}") from e
        except OSError as e:
            if e.errno in (errno.ENOENT, errno.ECONNREFUSED):
                raise ConnectionError(f"no daemon at {socket_path}") from e
            raise
        payload = json.dumps({"cmd": cmd, **kwargs}, separators=(",", ":")) + "\n"
        s.sendall(payload.encode("utf-8"))
        buf = bytearray()
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)
        if not buf:
            raise ConnectionError("empty response from daemon")
        result = json.loads(buf.decode("utf-8"))
        if not isinstance(result, dict):
            raise ConnectionError(f"malformed response: {result!r}")
        return result
    finally:
        s.close()


async def forward_toggle(socket_path: Path) -> bool:
    """If a peer daemon is alive, send a toggle and return True."""
    if not await probe(socket_path):
        return False
    try:
        send_sync(socket_path, "toggle")
        _log.info("forwarded toggle to existing daemon")
        return True
    except ConnectionError:
        return False
