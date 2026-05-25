"""Markdown scanner: identify spans + marker ranges in plain markdown text.

Pure Python — no GTK dependencies. The editor's live renderer consumes
the returned ``Span``s to decide where to apply visual ``Gtk.TextTag``s
and which character ranges are syntactic markers eligible for hiding.

The ``Scanner`` protocol lets us swap the regex implementation for a real
parser (``markdown-it-py``) later without changing the renderer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class SpanKind(Enum):
    """One per supported construct. The renderer maps each to a ``Gtk.TextTag``."""

    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    H4 = "h4"
    H5 = "h5"
    H6 = "h6"
    BOLD = "bold"
    ITALIC = "italic"
    CODE_INLINE = "code_inline"
    CODE_BLOCK = "code_block"
    LINK = "link"
    QUOTE = "quote"
    HR = "hr"


@dataclass(frozen=True)
class Span:
    """A markdown construct's location in the buffer.

    ``start``/``end`` are absolute character offsets (end exclusive).
    ``marker_ranges`` are subranges that are syntactic markers — these get
    hidden when the cursor is elsewhere and revealed when it returns.
    ``extras`` carries kind-specific metadata (e.g. ``{"url": "..."}``).
    """

    start: int
    end: int
    kind: SpanKind
    marker_ranges: tuple[tuple[int, int], ...] = ()
    extras: dict[str, str] = field(default_factory=dict, hash=False, compare=False)


class Scanner(Protocol):
    """Implementations turn raw markdown text into a list of ``Span``s."""

    def scan(self, text: str) -> list[Span]: ...


# ---- Block-level patterns (anchored to start of line) ----

_HEADING_RE = re.compile(r"^(#{1,6})( +)(.*)$")
_HR_RE = re.compile(r"^(-{3,}|_{3,}|\*{3,})\s*$")
_QUOTE_RE = re.compile(r"^(>\s?)(.*)$")
_FENCE_RE = re.compile(r"^(```|~~~)(.*)$")

# ---- Inline patterns ----

# Bold: `**…**`. Outer markers must not be backslash-escaped; inner text
# must start/end on non-whitespace; opening must not be preceded by `*`.
_BOLD_RE = re.compile(r"(?<!\\)(?<!\*)\*\*(?=\S)(.+?)(?<=\S)(?<!\\)\*\*(?!\*)")

# Italic with `*`: single `*` not part of `**`, not escaped, not adjacent
# to a word char on the outside.
_ITALIC_AST_RE = re.compile(
    r"(?<![\\\*])(?<!\w)\*(?!\*)(?=\S)([^\*\n]+?)(?<=\S)(?<!\\)\*(?!\*)(?!\w)"
)

# Italic with `_`: single `_` not adjacent to word chars or other `_`.
_ITALIC_UND_RE = re.compile(r"(?<![\w_\\])_(?=\S)([^_\n]+?)(?<=\S)(?<!\\)_(?![\w_])")

# Inline code: `…`. Markdown inside is NOT interpreted further.
_CODE_INLINE_RE = re.compile(r"(?<!\\)`([^`\n]+)`")

# Link: [label](url). Label can't contain `]` or newline; URL can't
# contain `)` or newline (good-enough for v1).
_LINK_RE = re.compile(r"(?<!\\)\[([^\]\n]+)\]\(([^\)\n]*)\)")


_HEADING_KIND = {
    1: SpanKind.H1, 2: SpanKind.H2, 3: SpanKind.H3,
    4: SpanKind.H4, 5: SpanKind.H5, 6: SpanKind.H6,
}


class RegexScanner:
    """V1 scanner. Block constructs are matched line-by-line; inline
    constructs are matched within each block's content, with code-inline
    and link ranges masking other inline patterns.

    Limitations (acceptable for v1):

    - No reference-style links, no images, no setext headings.
    - Lists and tables are ignored on purpose.
    - Edge cases around mixed `*`/`_` emphasis follow the regex's reading,
      which matches typical usage but is not full CommonMark.
    """

    def scan(self, text: str) -> list[Span]:
        spans: list[Span] = []
        lines = text.split("\n")
        line_starts = [0]
        for line in lines[:-1]:
            line_starts.append(line_starts[-1] + len(line) + 1)

        in_fence_marker: str | None = None
        fence_start_line = -1
        fence_start_offset = -1

        idx = 0
        while idx < len(lines):
            line = lines[idx]
            line_start = line_starts[idx]
            line_end = line_start + len(line)

            fm = _FENCE_RE.match(line)
            if in_fence_marker is None:
                if fm:
                    in_fence_marker = fm.group(1)
                    fence_start_line = idx
                    fence_start_offset = line_start
                    idx += 1
                    continue
                hm = _HEADING_RE.match(line)
                if hm:
                    level = len(hm.group(1))
                    marker_end_col = hm.end(2)
                    spans.append(Span(
                        start=line_start,
                        end=line_end,
                        kind=_HEADING_KIND[level],
                        marker_ranges=((line_start, line_start + marker_end_col),),
                    ))
                    self._scan_inline(line, line_start, marker_end_col, len(line), spans)
                    idx += 1
                    continue
                if _HR_RE.match(line):
                    spans.append(Span(
                        start=line_start,
                        end=line_end,
                        kind=SpanKind.HR,
                        marker_ranges=((line_start, line_end),),
                    ))
                    idx += 1
                    continue
                qm = _QUOTE_RE.match(line)
                if qm:
                    marker_end_col = qm.end(1)
                    spans.append(Span(
                        start=line_start,
                        end=line_end,
                        kind=SpanKind.QUOTE,
                        marker_ranges=((line_start, line_start + marker_end_col),),
                    ))
                    self._scan_inline(line, line_start, marker_end_col, len(line), spans)
                    idx += 1
                    continue
                self._scan_inline(line, line_start, 0, len(line), spans)
                idx += 1
            else:
                if fm and fm.group(1) == in_fence_marker:
                    open_line = lines[fence_start_line]
                    open_line_start = line_starts[fence_start_line]
                    spans.append(Span(
                        start=fence_start_offset,
                        end=line_end,
                        kind=SpanKind.CODE_BLOCK,
                        marker_ranges=(
                            (open_line_start, open_line_start + len(open_line)),
                            (line_start, line_end),
                        ),
                    ))
                    in_fence_marker = None
                    fence_start_line = -1
                    fence_start_offset = -1
                idx += 1

        if in_fence_marker is not None:
            # Unclosed fence — style the rest of the buffer as a code block.
            open_line = lines[fence_start_line]
            open_line_start = line_starts[fence_start_line]
            spans.append(Span(
                start=fence_start_offset,
                end=len(text),
                kind=SpanKind.CODE_BLOCK,
                marker_ranges=((open_line_start, open_line_start + len(open_line)),),
            ))

        spans.sort(key=lambda s: (s.start, s.end))
        return spans

    def _scan_inline(
        self,
        line: str,
        line_offset: int,
        start_col: int,
        end_col: int,
        spans: list[Span],
    ) -> None:
        """Scan inline constructs in ``line[start_col:end_col]`` and append
        spans with absolute (buffer-wide) offsets.
        """
        segment = line[start_col:end_col]
        base = line_offset + start_col
        masked: list[tuple[int, int]] = []  # ranges other inline rules must skip

        # Inline code first — contents are opaque to further parsing.
        for m in _CODE_INLINE_RE.finditer(segment):
            spans.append(Span(
                start=base + m.start(),
                end=base + m.end(),
                kind=SpanKind.CODE_INLINE,
                marker_ranges=(
                    (base + m.start(), base + m.start() + 1),
                    (base + m.end() - 1, base + m.end()),
                ),
            ))
            masked.append((m.start(), m.end()))

        # Links second. Label + URL together masked from emphasis scans.
        for m in _LINK_RE.finditer(segment):
            if _in_any(m.start(), masked):
                continue
            label_start, label_end = m.start(1), m.end(1)
            spans.append(Span(
                start=base + m.start(),
                end=base + m.end(),
                kind=SpanKind.LINK,
                marker_ranges=(
                    (base + m.start(), base + label_start),       # '['
                    (base + label_end, base + m.end()),           # '](url)'
                ),
                extras={"url": m.group(2)},
            ))
            masked.append((m.start(), m.end()))

        # Bold: contents may also be italicised, so don't mask bold ranges.
        for m in _BOLD_RE.finditer(segment):
            if _in_any(m.start(), masked):
                continue
            spans.append(Span(
                start=base + m.start(),
                end=base + m.end(),
                kind=SpanKind.BOLD,
                marker_ranges=(
                    (base + m.start(), base + m.start() + 2),
                    (base + m.end() - 2, base + m.end()),
                ),
            ))

        for italic_re in (_ITALIC_AST_RE, _ITALIC_UND_RE):
            for m in italic_re.finditer(segment):
                if _in_any(m.start(), masked):
                    continue
                spans.append(Span(
                    start=base + m.start(),
                    end=base + m.end(),
                    kind=SpanKind.ITALIC,
                    marker_ranges=(
                        (base + m.start(), base + m.start() + 1),
                        (base + m.end() - 1, base + m.end()),
                    ),
                ))


def _in_any(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in ranges)
