"""Tests for ``devpane.ui.markdown_scan.RegexScanner``.

Pure-Python; no GTK. Exercises the per-construct detection that drives
visual styling and marker hiding in the editor.
"""

from __future__ import annotations

from devpane.ui.markdown_scan import RegexScanner, Span, SpanKind


def _scan(text: str) -> list[Span]:
    return RegexScanner().scan(text)


def _kinds(spans: list[Span]) -> list[SpanKind]:
    return [s.kind for s in spans]


# ---- headings ----


def test_heading_levels_1_to_6() -> None:
    text = "# a\n## b\n### c\n#### d\n##### e\n###### f"
    spans = _scan(text)
    assert _kinds(spans) == [
        SpanKind.H1, SpanKind.H2, SpanKind.H3,
        SpanKind.H4, SpanKind.H5, SpanKind.H6,
    ]


def test_heading_marker_range_covers_hashes_and_space() -> None:
    spans = _scan("## Hi")
    h = next(s for s in spans if s.kind == SpanKind.H2)
    assert h.marker_ranges == ((0, 3),)  # '## '


def test_seven_hashes_is_not_a_heading() -> None:
    assert _scan("####### Too many") == []


def test_heading_inline_emphasis() -> None:
    spans = _scan("# Hello **world**")
    kinds = _kinds(spans)
    assert SpanKind.H1 in kinds
    assert SpanKind.BOLD in kinds


# ---- bold / italic ----


def test_bold_basic() -> None:
    spans = _scan("a **b** c")
    bold = [s for s in spans if s.kind == SpanKind.BOLD]
    assert len(bold) == 1
    assert (bold[0].start, bold[0].end) == (2, 7)
    assert bold[0].marker_ranges == ((2, 4), (5, 7))


def test_italic_with_asterisk() -> None:
    spans = _scan("a *b* c")
    it = [s for s in spans if s.kind == SpanKind.ITALIC]
    assert len(it) == 1
    assert (it[0].start, it[0].end) == (2, 5)


def test_italic_with_underscore() -> None:
    spans = _scan("a _b_ c")
    it = [s for s in spans if s.kind == SpanKind.ITALIC]
    assert len(it) == 1
    assert (it[0].start, it[0].end) == (2, 5)


def test_snake_case_not_italic() -> None:
    spans = _scan("snake_case_variable")
    assert [s for s in spans if s.kind == SpanKind.ITALIC] == []


def test_escaped_emphasis_does_not_match() -> None:
    spans = _scan(r"\*not bold\*")
    assert [s for s in spans if s.kind in (SpanKind.BOLD, SpanKind.ITALIC)] == []


def test_bold_does_not_double_as_italic() -> None:
    # `**x**` should produce one BOLD, zero ITALIC.
    spans = _scan("**x**")
    assert _kinds(spans) == [SpanKind.BOLD]


def test_bold_with_inner_italic() -> None:
    # `**a *b* c**` — BOLD outer, ITALIC inner.
    spans = _scan("**a *b* c**")
    kinds = _kinds(spans)
    assert SpanKind.BOLD in kinds
    assert SpanKind.ITALIC in kinds


# ---- inline code ----


def test_inline_code() -> None:
    spans = _scan("see `foo` bar")
    code = [s for s in spans if s.kind == SpanKind.CODE_INLINE]
    assert len(code) == 1
    assert (code[0].start, code[0].end) == (4, 9)
    assert code[0].marker_ranges == ((4, 5), (8, 9))


def test_inline_code_blocks_other_inline() -> None:
    # `**bold**` literal inside backticks must NOT also be BOLD.
    spans = _scan("`**not bold**`")
    assert _kinds(spans) == [SpanKind.CODE_INLINE]


# ---- fenced code block ----


def test_fenced_code_block() -> None:
    text = "```\nint x = 1;\nx++;\n```"
    spans = _scan(text)
    blocks = [s for s in spans if s.kind == SpanKind.CODE_BLOCK]
    assert len(blocks) == 1
    assert blocks[0].start == 0
    assert blocks[0].end == len(text)
    assert len(blocks[0].marker_ranges) == 2


def test_fenced_code_block_hides_interior_markdown() -> None:
    text = "```\n**not bold**\n```"
    spans = _scan(text)
    assert _kinds(spans) == [SpanKind.CODE_BLOCK]


def test_unclosed_fence_runs_to_end() -> None:
    text = "```\nstill open"
    spans = _scan(text)
    blocks = [s for s in spans if s.kind == SpanKind.CODE_BLOCK]
    assert len(blocks) == 1
    assert blocks[0].end == len(text)


# ---- links ----


def test_link_basic() -> None:
    spans = _scan("see [me](http://x) ok")
    links = [s for s in spans if s.kind == SpanKind.LINK]
    assert len(links) == 1
    link = links[0]
    assert (link.start, link.end) == (4, 18)
    assert link.extras.get("url") == "http://x"
    # Markers: '[' at 4, '](http://x)' at 7..18
    assert link.marker_ranges == ((4, 5), (7, 18))


def test_link_label_is_not_bold_outside() -> None:
    # `[**bold**](x)` — the LINK masks emphasis inside it for v1.
    spans = _scan("[**bold**](x)")
    assert _kinds(spans) == [SpanKind.LINK]


# ---- quote ----


def test_blockquote_marker_range() -> None:
    spans = _scan("> hello")
    q = next(s for s in spans if s.kind == SpanKind.QUOTE)
    assert q.marker_ranges == ((0, 2),)  # '> '


def test_blockquote_does_not_match_mid_line() -> None:
    spans = _scan("a > b")
    assert [s for s in spans if s.kind == SpanKind.QUOTE] == []


# ---- horizontal rule ----


def test_hr_dashes() -> None:
    spans = _scan("---")
    assert _kinds(spans) == [SpanKind.HR]


def test_hr_underscores() -> None:
    spans = _scan("___")
    assert _kinds(spans) == [SpanKind.HR]


def test_hr_mid_line_does_not_match() -> None:
    spans = _scan("text --- text")
    assert [s for s in spans if s.kind == SpanKind.HR] == []


# ---- ordering / idempotence ----


def test_spans_sorted_by_start() -> None:
    text = "# A\n\nSome **bold** and *italic*.\n"
    spans = _scan(text)
    starts = [s.start for s in spans]
    assert starts == sorted(starts)


def test_scan_idempotent() -> None:
    text = "# A\n**b** `c` _d_ [e](f)\n```\nx\n```\n"
    assert _scan(text) == _scan(text)
