"""Tests for the pure ``compute_reveal_set`` helper.

Exercises the cursor-aware marker reveal logic without touching GTK.
The actual tag application is verified manually since the repo has no
headless widget harness.
"""

from __future__ import annotations

from devpane.ui.markdown_render import compute_reveal_set
from devpane.ui.markdown_scan import RegexScanner


def test_cursor_on_heading_reveals_its_marker() -> None:
    # "# Hello" — marker is (0, 2). Cursor at 3 (on the line).
    spans = RegexScanner().scan("# Hello")
    reveal = compute_reveal_set(spans, cursor_offset=3, active_range=(0, 7))
    assert (0, 2) in reveal


def test_cursor_on_other_line_does_not_reveal() -> None:
    # Line 1: "# Hello"  (0..7)
    # Line 2: "body"     (8..12)
    spans = RegexScanner().scan("# Hello\nbody")
    # Cursor on line 2; line 2 range is (8, 12). The header's marker
    # range (0, 2) does not intersect (8, 12).
    reveal = compute_reveal_set(spans, cursor_offset=10, active_range=(8, 12))
    assert (0, 2) not in reveal


def test_cursor_inside_fenced_block_reveals_both_fences() -> None:
    text = "```\nint x;\n```"
    spans = RegexScanner().scan(text)
    # Cursor on the middle line, at offset 5 (inside "int x;").
    # Line range of that line is (4, 10).
    reveal = compute_reveal_set(spans, cursor_offset=5, active_range=(4, 10))
    # Both fence lines should be revealed because the cursor's span is
    # the whole code block.
    assert (0, 3) in reveal       # opening ```
    assert (11, 14) in reveal     # closing ```


def test_cursor_outside_block_does_not_reveal_fences() -> None:
    text = "before\n```\nint x;\n```\nafter"
    spans = RegexScanner().scan(text)
    # Cursor on "before" line: offset 0..6.
    reveal = compute_reveal_set(spans, cursor_offset=2, active_range=(0, 6))
    # No marker ranges intersect (0, 6).
    assert reveal == set()


def test_selection_reveals_markers_inside_it() -> None:
    # "a **bold** c" — bold markers at (2, 4) and (8, 10).
    # Cursor on a different line, but selection covers part of the line.
    text = "x\na **bold** c"
    spans = RegexScanner().scan(text)
    # Cursor at 0 (on "x"), but the caller passes an expanded active
    # range covering the selection: from 2 to 12 of the second line.
    # That second line starts at offset 2 in the buffer, so we want
    # active_range covering the buffer offsets that include the markers.
    reveal = compute_reveal_set(spans, cursor_offset=0, active_range=(0, 14))
    assert (4, 6) in reveal       # **
    assert (10, 12) in reveal     # **


def test_empty_buffer_empty_reveal() -> None:
    assert compute_reveal_set([], 0, (0, 0)) == set()


def test_marker_range_touching_active_boundary_does_not_reveal() -> None:
    # marker range (0, 2), active range (2, 10) — share a single point;
    # the marker ends exactly where the active region begins. Since the
    # intersection check is half-open, no reveal.
    spans = RegexScanner().scan("# x\nbody")
    reveal = compute_reveal_set(spans, cursor_offset=5, active_range=(4, 8))
    assert (0, 2) not in reveal
