"""Logging setup for the daemon and CLI.

Logs to stderr by default. The daemon will also log to a file under
``$XDG_STATE_HOME/devpane/log`` in M8.
"""

from __future__ import annotations

import logging
import os
import sys

_FMT = "%(asctime)s %(levelname)-5s %(name)s — %(message)s"


def setup(level: str | int | None = None) -> None:
    """Configure the root logger. Idempotent."""
    if level is None:
        env = os.environ.get("DEVPANE_LOG_LEVEL", "INFO")
        level = env
    root = logging.getLogger()
    if root.handlers:  # already configured
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FMT, datefmt="%H:%M:%S"))
    root.addHandler(handler)
    root.setLevel(level)
