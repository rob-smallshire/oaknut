"""Exception hierarchy for the BBC BASIC tokeniser and de-tokeniser.

All errors derive from :class:`BASICError`, itself a
:class:`~oaknut.exception.DataError`: a tokeniser/de-tokeniser failure is
always a problem with the *program* — bad source text or a malformed
token stream — never a bug, so the CLI boundary renders them without a
traceback and exits with :data:`~exit_codes.ExitCode.DATA_ERR`.

Two families sit under the base, mirroring the two directions:

- :class:`TokeniseError` — source text → tokens. Carries the 1-based
  index and verbatim text of the offending source line.
- :class:`DetokeniseError` — tokens → source text. Carries the byte
  *offset* into the program where the fault was found.

Each concrete class stores its specifics as attributes (so the CLI can
quote line text, point at a byte offset, or report an out-of-range line
number) and attaches an actionable ``__note__`` where one helps. The CLI
boundary reads :attr:`exit_code` and walks ``__notes__`` via
:func:`oaknut.exception.render_error`.
"""

from __future__ import annotations

from exit_codes import ExitCode
from oaknut.basic.linenumber import MAX_LINE_NUMBER
from oaknut.basic.tokens import MAX_BODY_LENGTH
from oaknut.exception import DataError


class BASICError(DataError):
    """Base for every BBC BASIC tokeniser and de-tokeniser error."""

    _exit_code = ExitCode.DATA_ERR


# ---------------------------------------------------------------------------
# Tokenising: source text -> tokens
# ---------------------------------------------------------------------------


class TokeniseError(BASICError):
    """Base for an error in BBC BASIC source being tokenised.

    Attributes:
        line_index: 1-based position of the offending line in the source.
        line_text: The offending line, verbatim (no trailing newline).
    """

    def __init__(self, message: str, *, line_index: int, line_text: str) -> None:
        super().__init__(message)
        self.line_index = line_index
        self.line_text = line_text


class UnnumberedLineError(TokeniseError):
    """A source line has no leading line number.

    Raised when tokenising without auto-numbering: every line must begin
    with a line number (as a saved ``LIST`` would).
    """

    def __init__(self, line_index: int, line_text: str) -> None:
        super().__init__(
            f"line {line_index} has no line number: {line_text!r}",
            line_index=line_index,
            line_text=line_text,
        )
        self.add_note("Pass --start/--step to auto-number unnumbered source, as AUTO would.")


class AlreadyNumberedError(TokeniseError):
    """Auto-numbering was requested but the source is already numbered.

    Attributes:
        line_number: The line number already present on the line.
    """

    def __init__(self, line_index: int, line_number: int, line_text: str) -> None:
        super().__init__(
            f"line {line_index} is already numbered (line {line_number}) "
            f"but auto-numbering was requested: {line_text!r}",
            line_index=line_index,
            line_text=line_text,
        )
        self.line_number = line_number
        self.add_note("Drop --start/--step to tokenise source that already carries line numbers.")


class LineNumberRangeError(TokeniseError):
    """A line number is outside the valid range.

    Attributes:
        line_number: The out-of-range line number.
    """

    def __init__(self, line_index: int, line_number: int, line_text: str) -> None:
        super().__init__(
            f"line {line_index}: line number {line_number} is out of range "
            f"(0-{MAX_LINE_NUMBER})",
            line_index=line_index,
            line_text=line_text,
        )
        self.line_number = line_number


class LineNumberOrderError(TokeniseError):
    """A line number does not exceed the line before it.

    BBC BASIC stores lines in strictly ascending order; a listing that
    repeats or rewinds a line number could not have come from ``LIST``.

    Attributes:
        line_number: The offending line number.
        previous_line_number: The line number of the preceding line.
    """

    def __init__(
        self,
        line_index: int,
        line_number: int,
        previous_line_number: int,
        line_text: str,
    ) -> None:
        super().__init__(
            f"line {line_index}: line number {line_number} does not follow the "
            f"previous line number {previous_line_number} (lines must ascend)",
            line_index=line_index,
            line_text=line_text,
        )
        self.line_number = line_number
        self.previous_line_number = previous_line_number


class LineTooLongError(TokeniseError):
    """A tokenised line exceeds the maximum storable length.

    Attributes:
        line_number: The BASIC line number that overflowed.
        length: The tokenised body length in bytes.
    """

    def __init__(self, line_index: int, line_number: int, length: int, line_text: str) -> None:
        super().__init__(
            f"line {line_index} (BASIC line {line_number}) tokenises to {length} "
            f"bytes, exceeding the {MAX_BODY_LENGTH}-byte maximum",
            line_index=line_index,
            line_text=line_text,
        )
        self.line_number = line_number
        self.length = length


# ---------------------------------------------------------------------------
# De-tokenising: tokens -> source text
# ---------------------------------------------------------------------------


class DetokeniseError(BASICError):
    """Base for an error in a tokenised program being de-tokenised.

    Attributes:
        offset: Byte offset into the program where the fault was found.
    """

    def __init__(self, message: str, *, offset: int) -> None:
        super().__init__(f"offset {offset}: {message}")
        self.offset = offset


class MissingLineMarkerError(DetokeniseError):
    """A line did not begin with the expected ``&0D`` marker.

    Attributes:
        found: The byte found where the marker was expected.
    """

    def __init__(self, offset: int, found: int) -> None:
        super().__init__(
            f"expected a &0D line marker, found &{found:02X}",
            offset=offset,
        )
        self.found = found


class TruncatedProgramError(DetokeniseError):
    """The token stream ended in the middle of a structure.

    Attributes:
        detail: What was being read when the bytes ran out.
    """

    def __init__(self, offset: int, detail: str) -> None:
        super().__init__(f"truncated program ({detail})", offset=offset)
        self.detail = detail


class InvalidLineLengthError(DetokeniseError):
    """A line's length byte is impossible.

    Attributes:
        length: The offending length byte.
    """

    def __init__(self, offset: int, length: int) -> None:
        super().__init__(
            f"invalid line length {length} (a line is at least its 4-byte "
            f"header and must stay within the program)",
            offset=offset,
        )
        self.length = length
