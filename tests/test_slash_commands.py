"""Tests for the pure helpers in ``devpane.ui.slash_commands``.

The GTK ``CompletionProvider`` integration is verified manually (no
headless widget harness in this repo); these tests exercise the
command table, matcher, trigger detection, and template expansion.
"""

from __future__ import annotations

from devpane.ui.slash_commands import (
    COMMANDS,
    SlashCommand,
    expand_insert,
    find_trigger,
    match,
)


# ---- command table integrity ----


def test_command_table_triggers_unique() -> None:
    triggers = [c.trigger for c in COMMANDS]
    assert len(triggers) == len(set(triggers))


def test_command_table_required_fields() -> None:
    for c in COMMANDS:
        assert isinstance(c, SlashCommand)
        assert c.trigger and c.trigger.isalnum()
        assert c.label.startswith("/") and c.label[1:] == c.trigger
        assert c.description
        assert c.insert


def test_command_table_covers_planned_commands() -> None:
    triggers = {c.trigger for c in COMMANDS}
    expected = {
        "h1", "h2", "h3", "h4", "h5", "h6",
        "list", "numlist", "todo",
        "code", "quote", "hr",
        "bold", "italic", "inlinecode", "link",
    }
    assert expected.issubset(triggers)


# ---- matcher ----


def test_match_empty_returns_all() -> None:
    assert match("") == list(COMMANDS)


def test_match_h_returns_headings_first() -> None:
    results = match("h")
    assert [c.trigger for c in results[:6]] == ["h1", "h2", "h3", "h4", "h5", "h6"]
    assert "hr" in [c.trigger for c in results]  # substring/prefix both fine


def test_match_li_returns_list_and_link() -> None:
    triggers = [c.trigger for c in match("li")]
    assert "list" in triggers
    assert "link" not in triggers[:1]  # 'list' is a prefix match, ranked first


def test_match_no_results() -> None:
    assert match("zzz") == []


def test_match_substring_after_prefix() -> None:
    # 'ode' is a substring of 'code' and 'inlinecode' but prefix of neither.
    triggers = [c.trigger for c in match("ode")]
    assert set(triggers) == {"code", "inlinecode"}


def test_match_is_case_insensitive() -> None:
    assert [c.trigger for c in match("H1")] == ["h1"]


# ---- find_trigger ----


def test_find_trigger_at_start() -> None:
    assert find_trigger("/h") == (0, "h")


def test_find_trigger_after_space() -> None:
    assert find_trigger("hello /li") == (6, "li")


def test_find_trigger_after_tab() -> None:
    assert find_trigger("\t/code") == (1, "code")


def test_find_trigger_inside_path_returns_none() -> None:
    assert find_trigger("src/foo") is None


def test_find_trigger_empty_word() -> None:
    assert find_trigger("/") == (0, "")


def test_find_trigger_no_slash_returns_none() -> None:
    assert find_trigger("just some text") is None


def test_find_trigger_must_be_at_end_of_line() -> None:
    # The cursor is at the end of the passed text; a slash followed by a
    # space (i.e. not at the cursor) should not be treated as the trigger.
    assert find_trigger("/h1 more") is None


# ---- expand_insert ----


def test_expand_insert_simple_heading() -> None:
    text, cur = expand_insert("# {cursor}")
    assert text == "# "
    assert cur == 2


def test_expand_insert_no_cursor_placeholder() -> None:
    text, cur = expand_insert("---")
    assert text == "---"
    assert cur == 3


def test_expand_insert_wrap_empty_selection() -> None:
    text, cur = expand_insert("**{sel}{cursor}**")
    assert text == "****"
    assert cur == 2


def test_expand_insert_wrap_with_selection() -> None:
    text, cur = expand_insert("**{sel}{cursor}**", selection="hi")
    assert text == "**hi**"
    assert cur == 4


def test_expand_insert_code_block() -> None:
    text, cur = expand_insert("```\n{cursor}\n```")
    assert text == "```\n\n```"
    # Cursor lands between the two newlines, i.e. after "```\n".
    assert text[:cur] == "```\n"


def test_expand_insert_link_no_selection() -> None:
    text, cur = expand_insert("[{cursor}{sel}](url)")
    assert text == "[](url)"
    assert cur == 1


def test_expand_insert_link_with_selection() -> None:
    text, cur = expand_insert("[{cursor}{sel}](url)", selection="DevPane")
    assert text == "[DevPane](url)"
    # Cursor sits just inside the opening bracket so the user can type
    # over the link text if they wish.
    assert cur == 1
