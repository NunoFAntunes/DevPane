"""Tests for the debouncer."""

from __future__ import annotations

import threading
import time

from devpane.util.debounce import Debouncer


def test_fires_once_after_delay() -> None:
    calls = 0
    done = threading.Event()

    def fn() -> None:
        nonlocal calls
        calls += 1
        done.set()

    d = Debouncer(0.05, fn)
    d.schedule()
    assert done.wait(timeout=1.0)
    assert calls == 1


def test_coalesces_rapid_schedules() -> None:
    calls = 0
    done = threading.Event()

    def fn() -> None:
        nonlocal calls
        calls += 1
        done.set()

    d = Debouncer(0.05, fn)
    for _ in range(10):
        d.schedule()
        time.sleep(0.005)
    assert done.wait(timeout=1.0)
    time.sleep(0.1)  # ensure no late fires
    assert calls == 1


def test_flush_runs_synchronously() -> None:
    calls = 0

    def fn() -> None:
        nonlocal calls
        calls += 1

    d = Debouncer(10.0, fn)
    d.schedule()
    assert d.pending is True
    assert d.flush() is True
    assert calls == 1
    assert d.pending is False


def test_flush_when_idle_is_noop() -> None:
    calls = 0

    def fn() -> None:
        nonlocal calls
        calls += 1

    d = Debouncer(10.0, fn)
    assert d.flush() is False
    assert calls == 0


def test_cancel_prevents_fire() -> None:
    calls = 0

    def fn() -> None:
        nonlocal calls
        calls += 1

    d = Debouncer(0.05, fn)
    d.schedule()
    d.cancel()
    time.sleep(0.1)
    assert calls == 0
