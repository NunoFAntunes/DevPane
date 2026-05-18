"""Wire protocol for DevPane IPC.

One JSON object per line, both directions, UTF-8. Requests carry a ``cmd``
field and optional command-specific keys. Responses always carry ``ok`` and,
on success, an optional ``data`` payload; on failure, an ``error`` string.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict


class Request(TypedDict, total=False):
    cmd: str


class Response(TypedDict, total=False):
    ok: bool
    data: dict[str, Any]
    error: str


# Commands handled by the daemon. Adding a command: extend this set and add
# a handler in `daemon.app.Daemon._handlers`.
CMD_TOGGLE: Final = "toggle"
CMD_SHOW: Final = "show"
CMD_HIDE: Final = "hide"
CMD_STATUS: Final = "status"
CMD_QUIT: Final = "quit"

ALL_COMMANDS: Final = frozenset({CMD_TOGGLE, CMD_SHOW, CMD_HIDE, CMD_STATUS, CMD_QUIT})


def ok(data: dict[str, Any] | None = None) -> Response:
    r: Response = {"ok": True}
    if data is not None:
        r["data"] = data
    return r


def err(message: str) -> Response:
    return {"ok": False, "error": message}
