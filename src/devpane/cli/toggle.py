"""`devpane-toggle` CLI. M0 stub — real IPC client lands in M2."""

from __future__ import annotations

import argparse
import sys

from devpane.version import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devpane-toggle",
        description="Toggle the DevPane drop-down. Bind this to a key in your DE.",
    )
    parser.add_argument("--version", action="version", version=f"devpane-toggle {__version__}")
    parser.add_argument(
        "cmd",
        nargs="?",
        default="toggle",
        choices=["toggle", "show", "hide", "status"],
        help="Command to send to the daemon (default: toggle).",
    )
    args = parser.parse_args(argv)

    print(f"devpane-toggle: would send {args.cmd!r} (skeleton; see docs/PLAN.md M2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
