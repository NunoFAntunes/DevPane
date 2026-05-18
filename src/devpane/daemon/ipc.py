"""Asyncio Unix-socket IPC server.

One client per connection, one JSON line in, one JSON line out, connection
closed. The protocol is intentionally trivial — the CLI client is a
~20-line script that just sends and prints.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, cast

from devpane.daemon.protocol import Request, Response, err

_log = logging.getLogger(__name__)

Handler = Callable[[Request], Awaitable[Response]]


class IPCServer:
    """Owns the listening socket and dispatches requests to handlers."""

    def __init__(self, socket_path: Path, handlers: Mapping[str, Handler]) -> None:
        self._socket_path = socket_path
        self._handlers = handlers
        self._server: asyncio.AbstractServer | None = None

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def start(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove a stale socket file if any. We assume single_instance.acquire
        # already confirmed no live daemon owns it.
        with contextlib.suppress(FileNotFoundError):
            self._socket_path.unlink()
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self._socket_path)
        )
        os.chmod(self._socket_path, 0o600)
        _log.info("ipc: listening on %s", self._socket_path)

    async def serve_forever(self) -> None:
        assert self._server is not None, "call start() first"
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        with contextlib.suppress(FileNotFoundError):
            self._socket_path.unlink()
        _log.info("ipc: stopped")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            response = await self._dispatch(line)
            writer.write(_encode(response))
            await writer.drain()
        except Exception as e:
            _log.exception("ipc: client error")
            try:
                writer.write(_encode(err(f"server error: {e}")))
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _dispatch(self, raw: bytes) -> Response:
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as e:
            return err(f"invalid json: {e}")
        if not isinstance(payload, dict):
            return err("payload must be a JSON object")
        cmd = payload.get("cmd")
        if not isinstance(cmd, str):
            return err("missing 'cmd' string")
        handler = self._handlers.get(cmd)
        if handler is None:
            return err(f"unknown command: {cmd}")
        try:
            return await handler(cast(Request, payload))
        except Exception as e:
            _log.exception("ipc: handler %s raised", cmd)
            return err(f"handler error: {e}")


def _encode(response: Response) -> bytes:
    return (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
