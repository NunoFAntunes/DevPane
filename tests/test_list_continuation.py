"""Tests for the pure ``compute_list_action`` helper."""

from __future__ import annotations

from devpane.ui.list_continuation import ListAction, compute_list_action


def test_bullet_continues() -> None:
    a = compute_list_action("- item")
    assert a == ListAction(next_prefix="- ", is_escape=False)


def test_bullet_star() -> None:
    a = compute_list_action("* item")
    assert a == ListAction(next_prefix="* ", is_escape=False)


def test_bullet_plus() -> None:
    a = compute_list_action("+ item")
    assert a == ListAction(next_prefix="+ ", is_escape=False)


def test_indented_bullet_keeps_indent() -> None:
    a = compute_list_action("    - nested item")
    assert a == ListAction(next_prefix="    - ", is_escape=False)


def test_empty_bullet_escapes() -> None:
    a = compute_list_action("- ")
    assert a == ListAction(next_prefix="", is_escape=True)


def test_whitespace_only_bullet_escapes() -> None:
    a = compute_list_action("-   \t ")
    assert a == ListAction(next_prefix="", is_escape=True)


def test_numbered_continues_and_increments() -> None:
    a = compute_list_action("3. third")
    assert a == ListAction(next_prefix="4. ", is_escape=False)


def test_numbered_handles_big_numbers() -> None:
    a = compute_list_action("999. nine")
    assert a == ListAction(next_prefix="1000. ", is_escape=False)


def test_empty_numbered_escapes() -> None:
    a = compute_list_action("1. ")
    assert a == ListAction(next_prefix="", is_escape=True)


def test_indented_numbered_keeps_indent() -> None:
    a = compute_list_action("  2. nested")
    assert a == ListAction(next_prefix="  3. ", is_escape=False)


def test_checkbox_continues_unchecked() -> None:
    a = compute_list_action("- [ ] task")
    assert a == ListAction(next_prefix="- [ ] ", is_escape=False)


def test_checkbox_checked_continues_unchecked() -> None:
    # A finished item shouldn't seed the next item as already done.
    a = compute_list_action("- [x] done")
    assert a == ListAction(next_prefix="- [ ] ", is_escape=False)


def test_empty_checkbox_escapes() -> None:
    a = compute_list_action("- [ ] ")
    assert a == ListAction(next_prefix="", is_escape=True)


def test_indented_checkbox_keeps_indent() -> None:
    a = compute_list_action("  - [ ] nested")
    assert a == ListAction(next_prefix="  - [ ] ", is_escape=False)


def test_plain_paragraph_is_not_a_list() -> None:
    assert compute_list_action("just a paragraph") is None


def test_heading_is_not_a_list() -> None:
    assert compute_list_action("# Heading") is None


def test_blockquote_is_not_a_list() -> None:
    assert compute_list_action("> quoted") is None


def test_empty_line_is_not_a_list() -> None:
    assert compute_list_action("") is None


def test_dash_without_space_is_not_a_list() -> None:
    # `-foo` (no space after the dash) is not a list item in markdown.
    assert compute_list_action("-foo") is None
