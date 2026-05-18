"""Re-exec the daemon with ``LD_PRELOAD`` set to ``libgtk4-layer-shell.so``.

Layer-shell requires the library to be linked *before* libwayland-client.
Python imports alone don't satisfy this; only ``LD_PRELOAD`` does. This
module probes for ``gtk4-layer-shell`` via ``pkg-config`` and, if the
current process isn't already preloading it, re-execs itself with the
right environment.

Skip this entirely by setting ``DEVPANE_SKIP_LAYER_SHELL_PRELOAD=1`` (the
fallback Wayland-plain adapter will be used instead).

Reference: https://github.com/wmww/gtk4-layer-shell/blob/main/linking.md
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

_log = logging.getLogger(__name__)

_PRELOAD_MARKER = "libgtk4-layer-shell"


def ensure_preloaded() -> None:
    """If needed, re-exec the current process with ``LD_PRELOAD`` set.

    Returns normally if no re-exec is needed (already preloaded, library
    missing, or opted out). On re-exec, this function does not return —
    ``execvpe`` replaces the process image.
    """
    if os.environ.get("DEVPANE_SKIP_LAYER_SHELL_PRELOAD"):
        return
    if _PRELOAD_MARKER in os.environ.get("LD_PRELOAD", ""):
        return

    so_path = _find_library()
    if so_path is None:
        return  # not installed — adapter factory will fall back

    new_env = os.environ.copy()
    existing = new_env.get("LD_PRELOAD", "")
    new_env["LD_PRELOAD"] = f"{so_path}:{existing}" if existing else str(so_path)
    _log.info("re-execing with LD_PRELOAD=%s", new_env["LD_PRELOAD"])
    os.execvpe(sys.executable, [sys.executable, *sys.argv], new_env)


_FALLBACK_LIBDIRS = (
    Path("/usr/lib"),
    Path("/usr/lib64"),
    Path("/usr/lib/x86_64-linux-gnu"),
    Path("/usr/local/lib"),
)
_CANDIDATE_NAMES = (
    "libgtk4-layer-shell.so",
    "libgtk4-layer-shell.so.0",
)


def _find_library() -> Path | None:
    # Try pkg-config first; some distros split the .pc into a devel package
    # (notably Arch), so fall back to scanning standard library paths.
    search_dirs: list[Path] = []
    libdir = _pkg_config_libdir()
    if libdir is not None:
        search_dirs.append(libdir)
    search_dirs.extend(_FALLBACK_LIBDIRS)
    for d in search_dirs:
        for name in _CANDIDATE_NAMES:
            path = d / name
            if path.exists():
                return path.resolve()
    return None


def _pkg_config_libdir() -> Path | None:
    try:
        result = subprocess.run(
            ["pkg-config", "--variable=libdir", "gtk4-layer-shell"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    libdir = Path(result.stdout.strip())
    if not libdir.is_dir():
        return None
    return libdir
