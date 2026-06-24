"""Line numbering for BBC BASIC source held as text.

BBC BASIC programs are stored with an explicit line number at the start
of every line. Source that was authored or captured without those
numbers — the form a programmer types under the BBC's ``AUTO`` command —
needs them prepended before it will tokenise or run. :func:`number_lines`
performs that prepend, mirroring ``AUTO start,step``.

The facade operates purely on Python strings, so it is usable
programmatically without touching a disc image or the CLI. The CLI
(:mod:`oaknut.basic.cli`) is a thin wrapper that adds the byte/text and
stream plumbing on top.
"""

from __future__ import annotations

import re

DEFAULT_LINE_NUMBER = 10
DEFAULT_LINE_STEP = 10

# A BBC BASIC line ends only at a carriage return (or a host newline);
# Python's str.splitlines() additionally breaks on &0B, &0C, &1C-&1E and
# others, which occur legitimately inside string literals (mode-7 / VDU
# control codes), so split strictly on the real terminators only. This
# definition is shared with the tokeniser, which imports it from here.
LINE_SEPARATOR_RE = re.compile(r"\r\n|\r|\n")


def split_source_lines(source: str) -> list[str]:
    """Split BBC BASIC source into lines on real terminators only.

    Matches :meth:`str.splitlines` semantics for the terminators a BBC
    BASIC line actually ends on (``"\\n"``, ``"\\r"``, ``"\\r\\n"``) — an
    empty *source* yields no lines and a single trailing terminator is
    not treated as introducing a final empty line — but, unlike
    :meth:`str.splitlines`, never breaks on the in-string control codes
    (&0B, &0C, &1C-&1E, ...) that BBC BASIC string literals legitimately
    contain.
    """
    lines = LINE_SEPARATOR_RE.split(source)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def number_lines(
    source: str,
    *,
    start: int = DEFAULT_LINE_NUMBER,
    step: int = DEFAULT_LINE_STEP,
) -> str:
    """Prepend ascending line numbers to unnumbered BBC BASIC source.

    Each line of *source* receives a line number, beginning at *start*
    and increasing by *step*, in the manner of the BBC's
    ``AUTO start,step`` command. Internal references (``GOTO``,
    ``GOSUB``, ...) are left untouched; the caller is responsible for
    ensuring they already match the numbering produced here.

    Args:
        source: BBC BASIC source text with no line numbers, lines
            separated by newlines. ``"\\n"``, ``"\\r"`` and ``"\\r\\n"``
            are all accepted as line terminators.
        start: Line number given to the first line. Must not be negative.
        step: Increment between successive line numbers. Must be at
            least 1.

    Returns:
        The source with a line number prepended to every line, lines
        joined by ``"\\n"``. A trailing newline in *source* is preserved.

    Raises:
        ValueError: *start* is negative or *step* is less than 1.
    """
    if start < 0:
        raise ValueError(f"start line number must not be negative: {start}")
    if step < 1:
        raise ValueError(f"step must be at least 1: {step}")

    number = start
    numbered = []
    for line in split_source_lines(source):
        numbered.append(f"{number} {line}")
        number += step

    text = "\n".join(numbered)
    if numbered and source.endswith(("\n", "\r")):
        text += "\n"
    return text
