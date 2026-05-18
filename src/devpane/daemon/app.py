"""Daemon entry point. M0 stub — wired up in M2/M3."""

from __future__ import annotations

import argparse
import sys

from devpane.version import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devpaned",
        description="DevPane background daemon — owns the drop-down pane.",
    )
    parser.add_argument("--version", action="version", version=f"devpaned {__version__}")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run a self-check and exit (placeholder; implemented in M8).",
    )
    args = parser.parse_args(argv)

    if args.check:
        print("devpaned: skeleton OK")
        return 0

    print("devpaned: skeleton — daemon not yet implemented (see docs/PLAN.md M2+)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
