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


class Float5RangeError(BASICError):
    """A Python float is too large for the 5-byte BBC REAL format.

    The packed format carries an excess-128 exponent, so the largest
    representable magnitude is just under ``2**127``. Underflow is *not*
    an error — the format has no denormals, so tiny magnitudes flush to
    zero — but overflow (and any non-finite value) cannot be stored.

    Attributes:
        value: The offending Python float.
    """

    def __init__(self, value: float) -> None:
        super().__init__(
            f"{value!r} cannot be represented as a 5-byte BBC REAL "
            f"(magnitude must be finite and below 2**127)"
        )
        self.value = value


# ---------------------------------------------------------------------------
# Data files: PRINT# / INPUT# / BPUT# / BGET#
# ---------------------------------------------------------------------------


class DataFileError(BASICError):
    """Base for a fault reading or writing a BBC BASIC data file.

    Attributes:
        offset: Byte offset of the record where the fault was found, or
            ``None`` when the fault is not tied to a position.
    """

    def __init__(self, message: str, *, offset: int | None = None) -> None:
        if offset is not None:
            message = f"offset {offset}: {message}"
        super().__init__(message)
        self.offset = offset


class UnknownTagError(DataFileError):
    """A tagged record began with a byte that is not a known type tag.

    A ``PRINT#`` record starts with ``&00`` (string), ``&40`` (integer)
    or ``&FF`` (real); anything else means the stream is not tagged data
    at this point (often raw ``BPUT#`` bytes read as if tagged).

    Attributes:
        tag: The offending tag byte.
    """

    def __init__(self, tag: int, offset: int) -> None:
        super().__init__(
            f"&{tag:02X} is not a known type tag (&00 string, &40 integer, &FF real)",
            offset=offset,
        )
        self.tag = tag
        self.add_note("Untagged bytes written by BPUT# must be read with read_byte/read_bytes.")


class DataFileTypeMismatchError(DataFileError):
    """A typed read found a record of a different type.

    Mirrors BASIC's *Type mismatch* on ``INPUT#``: the record's tag did
    not match the type the caller asked for. The stream position is left
    at the start of the record so the caller can re-read it.

    Attributes:
        expected: Human-readable name of the requested type.
        tag: The tag byte actually found.
    """

    def __init__(self, expected: str, tag: int, offset: int) -> None:
        super().__init__(
            f"expected a {expected} record but found type tag &{tag:02X}",
            offset=offset,
        )
        self.expected = expected
        self.tag = tag


class TruncatedRecordError(DataFileError):
    """A tagged record ran past the end of the stream.

    Distinct from a clean end of file (which a typed read signals with
    :class:`EOFError`): the tag, or part of the payload, was present but
    the rest of the record was missing — the stream is corrupt.

    Attributes:
        detail: What was being read when the bytes ran out.
    """

    def __init__(self, offset: int, detail: str) -> None:
        super().__init__(f"truncated record ({detail})", offset=offset)
        self.detail = detail


class IntegerRangeError(DataFileError):
    """An integer is outside the signed 32-bit range a BBC integer holds.

    Attributes:
        value: The offending integer.
    """

    def __init__(self, value: int) -> None:
        super().__init__(
            f"{value} is out of range for a BBC integer "
            f"(must be -2**31 .. 2**31 - 1)"
        )
        self.value = value


class StringTooLongError(DataFileError):
    """A string is longer than the single length byte can describe.

    A ``PRINT#`` string is prefixed by one length byte, so it can hold at
    most 255 characters.

    Attributes:
        length: The offending string length.
    """

    def __init__(self, length: int) -> None:
        super().__init__(f"string of {length} characters exceeds the 255-character maximum")
        self.length = length


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
