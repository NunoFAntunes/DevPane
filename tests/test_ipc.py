"""Tests for the asyncio IPC server."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from devpane.daemon.ipc import IPCServer
from devpane.daemon.protocol import Request, Response, err, ok


async def _send(socket_path: Path, payload: bytes) -> bytes:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    writer.write(payload)
    await writer.drain()
    line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return line


@pytest.mark.asyncio
async def test_dispatch_known_command(tmp_path: Path) -> None:
    async def handler(req: Request) -> Response:
        return ok({"echo": req.get("cmd", "")})

    server = IPCServer(tmp_path / "s.sock", {"ping": handler})
    await server.start()
    serve = asyncio.create_task(server.serve_forever())
    try:
        line = await _send(server.socket_path, b'{"cmd":"ping"}\n')
        assert json.loads(line) == {"ok": True, "data": {"echo": "ping"}}
    finally:
        await server.stop()
        serve.cancel()


@pytest.mark.asyncio
async def test_unknown_command(tmp_path: Path) -> None:
    server = IPCServer(tmp_path / "s.sock", {})
    await server.start()
    serve = asyncio.create_task(server.serve_forever())
    try:
        line = await _send(server.socket_path, b'{"cmd":"bogus"}\n')
        body = json.loads(line)
        assert body["ok"] is False
        assert "unknown command" in body["error"]
    finally:
        await server.stop()
        serve.cancel()


@pytest.mark.asyncio
async def test_invalid_json(tmp_path: Path) -> None:
    server = IPCServer(tmp_path / "s.sock", {})
    await server.start()
    serve = asyncio.create_task(server.serve_forever())
    try:
        line = await _send(server.socket_path, b"not-json\n")
        body = json.loads(line)
        assert body["ok"] is False
        assert "invalid json" in body["error"]
    finally:
        await server.stop()
        serve.cancel()


@pytest.mark.asyncio
async def test_handler_exception_returns_error(tmp_path: Path) -> None:
    async def boom(_req: Request) -> Response:
        raise RuntimeError("kaboom")

    server = IPCServer(tmp_path / "s.sock", {"x": boom})
    await server.start()
    serve = asyncio.create_task(server.serve_forever())
    try:
        line = await _send(server.socket_path, b'{"cmd":"x"}\n')
        body = json.loads(line)
        assert body == err("handler error: kaboom")
    finally:
        await server.stop()
        serve.cancel()


@pytest.mark.asyncio
async def test_socket_removed_on_stop(tmp_path: Path) -> None:
    server = IPCServer(tmp_path / "s.sock", {})
    await server.start()
    assert server.socket_path.exists()
    await server.stop()
    assert not server.socket_path.exists()


@pytest.mark.asyncio
async def test_socket_permissions_0600(tmp_path: Path) -> None:
    server = IPCServer(tmp_path / "s.sock", {})
    await server.start()
    try:
        import os

        mode = os.stat(server.socket_path).st_mode & 0o777
        assert mode == 0o600
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_stale_socket_replaced(tmp_path: Path) -> None:
    sock = tmp_path / "s.sock"
    sock.write_bytes(b"")  # simulate a stale socket file
    server = IPCServer(sock, {})
    await server.start()
    try:
        assert server.socket_path.exists()
    finally:
        await server.stop()
