"""Identify tokenised BBC BASIC programs by structure alone.

Files harvested from Acorn disc images (DFS ``.ssd``, ADFS ``.adl``)
carry no filetype or extension, so a blob's nature has to be inferred
from its bytes. A stored BBC BASIC program — BASIC I, II, IV and V all
share the same line framing — is a run of lines::

    &0D  <line-hi>  <line-lo>  <len>   <len-4 tokenised body bytes>

repeated, then a terminator: ``&0D`` followed by a byte with its top bit
set. BASIC writes ``&0D &FF``, but the ROM only tests the top bit, and
programs with data appended sometimes tamper with the second byte, so
``&0D &80``-``&FF`` all terminate — :func:`detect` matches the ROM, not
the literal ``&FF``, and merely notes a non-``&FF`` terminator.

The walk is length-driven: each line's own ``<len>`` byte says where the
next ``&0D`` must be, so tokenised body bytes that happen to look like
``&0D`` never trip the scan. It is exactly what the ROM does to ``LIST``
a program, which makes it about as faithful a classifier as is possible
without a full de-tokenise. Because the framing is identical across all
BASIC versions, detection is purely structural and needs no
:class:`~oaknut.basic.Dialect` — it sits well below the token table.

Unlike :func:`~oaknut.basic.scan_program`, which raises
:class:`~oaknut.basic.DetokeniseError` on malformed input, :func:`detect`
is **total**: it classifies clean programs, program-plus-data, truncated
fragments and arbitrary garbage into a :class:`Verdict` with evidence,
and never raises. Classification is deliberately conservative and
reason-bearing so a corpus filter can explain every accept and reject.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from oaknut.basic.tokens import HEADER_LENGTH

_CR = 0x0D

# A stored line number is 0-32767 (see oaknut.basic.linenumber.MAX_LINE_NUMBER),
# so its high byte is always <= &7F — top bit clear. The end-of-program
# terminator's second byte has the top bit set (&FF, or a tampered &80-&FE).
# Testing the top bit therefore tells a terminator from a line-number high
# byte, exactly as the ROM's LIST loop does.
_TERMINATOR_TOP_BIT = 0x80


class Verdict(enum.Enum):
    """How confident :func:`detect` is that a blob is tokenised BBC BASIC."""

    #: A clean walk all the way to a proper terminator, no trailing bytes.
    BASIC = "basic"
    #: A valid program followed by extra bytes (data appended after the end).
    BASIC_TRAILING = "basic+"
    #: Begins as one or more well-formed lines, then the structure breaks.
    MAYBE = "maybe"
    #: Does not begin as a tokenised line at all.
    NOT_BASIC = "not-basic"

    @property
    def is_basic(self) -> bool:
        """True for the verdicts a corpus filter would extract as BASIC."""
        return self in (Verdict.BASIC, Verdict.BASIC_TRAILING)


@dataclass(frozen=True)
class Detection:
    """The outcome of inspecting one blob, with the evidence behind it.

    Attributes:
        verdict: The :class:`Verdict` reached.
        reason: A human-readable explanation of the decision.
        line_count: Well-formed lines walked before the terminator or break.
        program_length: Bytes up to and including the terminator (0 if none
            was reached).
        trailing_length: Bytes after the terminator (non-zero only for
            :attr:`Verdict.BASIC_TRAILING`).
        first_line: The first line's number, or ``None`` if no line parsed.
        last_line: The last line's number, or ``None`` if no line parsed.
        ascending: Whether the line numbers were strictly ascending.
        notes: Non-fatal observations (e.g. a non-``&FF`` terminator).
    """

    verdict: Verdict
    reason: str
    line_count: int = 0
    program_length: int = 0
    trailing_length: int = 0
    first_line: int | None = None
    last_line: int | None = None
    ascending: bool = True
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_basic(self) -> bool:
        """True when the verdict is :attr:`Verdict.BASIC` or ``BASIC_TRAILING``."""
        return self.verdict.is_basic


def detect(data: bytes | bytearray) -> Detection:
    """Classify *data* as tokenised BBC BASIC (or not) by walking its lines.

    Args:
        data: The raw bytes to classify.

    Returns:
        A :class:`Detection` carrying the :class:`Verdict` and the
        evidence gathered during the walk. Always returns; never raises.
    """
    n = len(data)
    if n < 2:
        return Detection(Verdict.NOT_BASIC, "too short to be a BASIC line")
    if data[0] != _CR:
        return Detection(
            Verdict.NOT_BASIC,
            f"first byte is &{data[0]:02X}, not a &0D line marker",
        )

    pos = 0
    line_count = 0
    first_line: int | None = None
    last_line: int | None = None
    prev_line: int | None = None
    ascending = True
    notes: list[str] = []

    def broke(reason: str) -> Detection:
        """A broken walk is MAYBE if it parsed >=1 clean line, else NOT_BASIC.

        One or more well-formed lines before the break means the blob
        really does begin as a tokenised program (truncated, or BASIC
        followed by data without a proper terminator); zero clean lines
        means the leading ``&0D`` was a coincidence.
        """
        return Detection(
            Verdict.MAYBE if line_count > 0 else Verdict.NOT_BASIC,
            reason,
            line_count=line_count,
            first_line=first_line,
            last_line=last_line,
            ascending=ascending,
            notes=tuple(notes),
        )

    while True:
        # Every iteration must land on a line marker.
        if pos >= n or data[pos] != _CR:
            found = f"&{data[pos]:02X}" if pos < n else "end of data"
            return broke(f"expected &0D at offset {pos}, found {found}")

        # The byte after &0D is either a terminator (top bit set) or a
        # line-number high byte.
        if pos + 1 >= n:
            return broke(f"truncated after &0D at offset {pos}")

        marker = data[pos + 1]
        if marker & _TERMINATOR_TOP_BIT:
            # A terminator before any line parsed means the leading &0D was
            # a coincidence (e.g. a View document opening &0D &80), not an
            # empty program — real type-ins always have at least one line.
            if line_count == 0:
                return Detection(
                    Verdict.NOT_BASIC,
                    f"&0D &{marker:02X} at offset 0 — terminator with no lines, "
                    "not a program",
                )
            program_length = pos + 2
            trailing = n - program_length
            if marker != 0xFF:
                notes.append(
                    f"terminator second byte &{marker:02X} (not &FF, top bit "
                    "only) — data may follow"
                )
            verdict = Verdict.BASIC if trailing == 0 else Verdict.BASIC_TRAILING
            reason = f"walked {line_count} line(s) to a terminator" + (
                f", {trailing} trailing byte(s)" if trailing else ""
            )
            return Detection(
                verdict=verdict,
                reason=reason,
                line_count=line_count,
                program_length=program_length,
                trailing_length=trailing,
                first_line=first_line,
                last_line=last_line,
                ascending=ascending,
                notes=tuple(notes),
            )

        # A real line: need the full 4-byte header.
        if pos + HEADER_LENGTH > n:
            return broke(f"truncated line header at offset {pos}")

        line_no = (marker << 8) | data[pos + 2]
        length = data[pos + 3]
        if length < HEADER_LENGTH:
            return broke(
                f"line {line_no} at offset {pos} has length {length} "
                f"(< {HEADER_LENGTH})"
            )
        if pos + length > n:
            return broke(f"line {line_no} at offset {pos} runs {length} bytes past end of data")

        if first_line is None:
            first_line = line_no
        if prev_line is not None and line_no <= prev_line:
            ascending = False
        prev_line = line_no
        last_line = line_no
        line_count += 1
        pos += length
