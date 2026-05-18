"""Thread-safe debouncer used for the 2-second autosave.

A scheduled call fires ``delay_s`` after the *last* ``schedule()`` invocation.
``flush()`` cancels the pending timer and runs the callable synchronously,
which the daemon uses to force a save on window hide.
"""

from __future__ import annotations

import threading
from collections.abc import Callable


class Debouncer:
    def __init__(self, delay_s: float, fn: Callable[[], None]) -> None:
        self._delay = delay_s
        self._fn = fn
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def schedule(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
        self._fn()

    def flush(self) -> bool:
        """Run pending callable synchronously. Returns True if a call was pending."""
        with self._lock:
            pending = self._timer is not None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if pending:
            self._fn()
        return pending

    def cancel(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    @property
    def pending(self) -> bool:
        with self._lock:
            return self._timer is not None
