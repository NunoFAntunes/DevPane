"""Window controller abstraction.

The daemon's IPC handlers talk to a ``WindowController`` instead of a
window directly. This lets us swap a real GTK window (M3+) for a headless
stand-in (tests, CI without a display) without changing handler code.

The controller methods are *async* because the GTK implementation needs to
schedule work onto the GLib main thread and await the result. The
headless implementation just toggles an in-memory flag.
"""

from __future__ import annotations

from typing import Protocol


class WindowController(Protocol):
    async def show(self) -> bool: ...
    async def hide(self) -> bool: ...
    async def toggle(self) -> bool: ...
    def is_visible(self) -> bool: ...


class HeadlessController:
    """No-display fallback. Tracks visibility as a simple bool."""

    def __init__(self) -> None:
        self._visible = False

    async def show(self) -> bool:
        self._visible = True
        return self._visible

    async def hide(self) -> bool:
        self._visible = False
        return self._visible

    async def toggle(self) -> bool:
        self._visible = not self._visible
        return self._visible

    def is_visible(self) -> bool:
        return self._visible
