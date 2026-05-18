"""Tests for the logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from devpane.util.logging import setup


def _reset_root_logger() -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


def test_setup_stderr_only_when_no_log_file(xdg_tmp: Path) -> None:
    _reset_root_logger()
    setup(level="DEBUG")
    root = logging.getLogger()
    handler_types = {type(h).__name__ for h in root.handlers}
    assert "StreamHandler" in handler_types
    assert "RotatingFileHandler" not in handler_types


def test_setup_writes_to_log_file_when_provided(xdg_tmp: Path) -> None:
    _reset_root_logger()
    log_path = xdg_tmp / "logs" / "devpane.log"
    setup(level="DEBUG", log_file=log_path)
    logging.getLogger("devpane.test").info("hello %s", "world")
    # File handler buffers; flush via handler.
    for h in logging.getLogger().handlers:
        h.flush()
    assert log_path.is_file()
    body = log_path.read_text(encoding="utf-8")
    assert "hello world" in body


def test_setup_is_idempotent(xdg_tmp: Path) -> None:
    _reset_root_logger()
    setup(level="INFO")
    n = len(logging.getLogger().handlers)
    setup(level="DEBUG")  # second call must not add handlers
    assert len(logging.getLogger().handlers) == n
    assert logging.getLogger().level == logging.DEBUG


def test_setup_handles_unwritable_log_dir(xdg_tmp: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _reset_root_logger()
    # Point at a file path; .mkdir(parents=True) on its child will fail
    # because the parent is a regular file.
    blocker = xdg_tmp / "blocker"
    blocker.write_text("")
    setup(level="INFO", log_file=blocker / "devpane.log")
    # Should fall back to stderr without raising.
    handler_types = {type(h).__name__ for h in logging.getLogger().handlers}
    assert "StreamHandler" in handler_types
