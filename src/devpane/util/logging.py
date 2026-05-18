"""Logging setup for the daemon and CLI.

Logs to stderr always; the daemon additionally tees to a rotating file at
``$XDG_STATE_HOME/devpane/devpane.log`` so post-mortems are possible
after the daemon exits.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

_FMT = "%(asctime)s %(levelname)-5s %(name)s — %(message)s"
_FILE_FMT = "%(asctime)s %(levelname)-5s %(name)s %(process)d — %(message)s"

_MAX_BYTES = 1_000_000  # 1 MB per file
_BACKUP_COUNT = 3  # keep 3 rotated files


def setup(level: str | int | None = None, log_file: Path | None = None) -> None:
    """Configure the root logger. Idempotent.

    If ``log_file`` is provided (typically the daemon), a rotating file
    handler is added in addition to stderr.
    """
    if level is None:
        level = os.environ.get("DEVPANE_LOG_LEVEL", "INFO")
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter(_FMT, datefmt="%H:%M:%S"))
    root.addHandler(stderr_handler)
    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(logging.Formatter(_FILE_FMT, datefmt="%Y-%m-%d %H:%M:%S"))
            root.addHandler(file_handler)
        except OSError as e:
            stderr_handler.handle(
                logging.LogRecord(
                    name="devpane",
                    level=logging.WARNING,
                    pathname="",
                    lineno=0,
                    msg="log file unavailable (%s); stderr only",
                    args=(e,),
                    exc_info=None,
                )
            )
    root.setLevel(level)
