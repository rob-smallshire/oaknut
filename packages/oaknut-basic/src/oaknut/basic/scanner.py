"""Scan tokenised BBC BASIC II bytes into a position-aware token stream.

De-tokenising to text is lossy for keyword adjacency: the body
``?Q <PLOT> ?Q`` renders as the text ``?QPLOT?Q``, which the ROM
tokeniser re-reads as ``?`` followed by the *variable* ``QPLOT`` — the
embedded ``PLOT`` keyword is gone (after a non-keyword letter the crunch
consumes the whole identifier; see :func:`oaknut.basic.tokenise`). The
only faithful representation of a tokenised program is therefore the
*bytes*, where ``PLOT`` is a distinct token. :func:`scan` yields that
stream: keyword tokens resolved to their spelling, ``&8D`` line-number
references decoded, quoted strings preserved verbatim, and every other
byte coalesced into literal :attr:`TokenKind.TEXT` runs for the consumer
to sub-lex.

The walk mirrors the de-tokeniser's; in fact the de-tokeniser is one
projection of this stream — joining every token's :attr:`Token.value`
reproduces a body's text exactly, which is how
:func:`oaknut.basic.detokenise_body` is defined. :func:`scan` works on a
line *body* (inline tokens, no framing); :func:`scan_program` walks the
``&0D``-framed stored form and yields a :class:`LineRecord` per line.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator
from dataclasses import dataclass

from oaknut.basic.dialect import BASIC_II, Dialect
from oaknut.basic.exceptions import (
    InvalidLineLengthError,
    MissingLineMarkerError,
    TruncatedProgramError,
)
from oaknut.basic.linenumber import decode_line_number
from oaknut.basic.tokens import HEADER_LENGTH, LINE_NUMBER_TOKEN

_CR = 0x0D
_END_MARKER = 0xFF
_QUOTE = 0x22


class TokenKind(enum.Enum):
    """The kind of a scanned :class:`Token`."""

    #: A keyword token byte, resolved to its spelling via the token table.
    KEYWORD = "KEYWORD"
    #: A run of literal bytes — identifiers, numbers, operators,
    #: punctuation, spaces, and any unknown high byte — for the consumer
    #: to sub-lex. Each byte ``b`` appears as ``chr(b)``.
    TEXT = "TEXT"
    #: A ``"..."`` string literal, copied verbatim through the closing
    #: quote (or the end of the body, if unterminated).
    STRING = "STRING"
    #: A ``&8D`` three-byte line-number reference, decoded to decimal.
    LINENUM = "LINENUM"


@dataclass(frozen=True)
class Token:
    """One unit of a scanned BBC BASIC line body.

    Attributes:
        kind: Which :class:`TokenKind` this is.
        value: The keyword spelling (``KEYWORD``), the literal run
            (``TEXT``), the quoted string including its quotes
            (``STRING``), or the decimal line number (``LINENUM``).
        start: Byte offset of the token within the scanned data, shifted
            by ``base_offset``.
        token: The token byte, for a ``KEYWORD``; ``None`` otherwise.
    """

    kind: TokenKind
    value: str
    start: int
    token: int | None = None


@dataclass(frozen=True)
class LineRecord:
    """One line of a scanned stored program.

    Attributes:
        line_number: The line's number.
        tokens: The line body as a tuple of :class:`Token`.
        start: Byte offset of the line's ``&0D`` marker.
    """

    line_number: int
    tokens: tuple[Token, ...]
    start: int


def scan(data: bytes, *, base_offset: int = 0, dialect: Dialect = BASIC_II) -> Iterator[Token]:
    """Scan an unframed line body into a stream of :class:`Token`.

    Args:
        data: A line *body* — inline token bytes with no ``&0D`` line
            framing and no leading line number.
        base_offset: Added to every token's :attr:`~Token.start`, so
            offsets can be reported against a larger buffer (for example
            the line body's position within a whole program).
        dialect: The BBC BASIC variant whose token tables to use.
            Defaults to :data:`~oaknut.basic.BASIC_II`; pass
            :data:`~oaknut.basic.BASIC_V` to resolve the
            ``&C6``/``&C7``/``&C8`` two-byte escape tokens and the
            re-purposed single-byte tokens of the Archimedes language.

    Yields:
        One :class:`Token` per keyword, literal run, string literal, and
        ``&8D`` line-number reference, in source order. For a two-byte
        escape keyword the token's :attr:`~Token.token` is the prefix
        byte and its :attr:`~Token.start` is the prefix's offset.

    Raises:
        DetokeniseError: A ``&8D`` reference is truncated.
    """
    n = len(data)
    i = 0
    text_start = -1
    text_chars: list[str] = []

    def flush() -> Iterator[Token]:
        nonlocal text_chars, text_start
        if text_chars:
            yield Token(TokenKind.TEXT, "".join(text_chars), base_offset + text_start)
            text_chars = []
            text_start = -1

    while i < n:
        b = data[i]
        if b == _QUOTE:
            yield from flush()
            j = i + 1
            while j < n and data[j] != _QUOTE:
                j += 1
            end = j + 1 if j < n else n
            yield Token(TokenKind.STRING, "".join(chr(c) for c in data[i:end]), base_offset + i)
            i = end
            continue
        if b == LINE_NUMBER_TOKEN:
            yield from flush()
            payload = data[i + 1 : i + 4]
            if len(payload) != 3:
                raise TruncatedProgramError(
                    offset=base_offset + i,
                    detail="incomplete &8D line-number reference",
                )
            yield Token(TokenKind.LINENUM, str(decode_line_number(payload)), base_offset + i)
            i += 4
            continue
        if b in dialect.escape and i + 1 < n and data[i + 1] in dialect.escape[b]:
            yield from flush()
            keyword = dialect.escape[b][data[i + 1]]
            yield Token(TokenKind.KEYWORD, keyword, base_offset + i, b)
            i += 2
            continue
        if b in dialect.single_byte:
            yield from flush()
            yield Token(TokenKind.KEYWORD, dialect.single_byte[b], base_offset + i, b)
            i += 1
            continue
        # A literal byte, an unknown high byte, or an escape prefix whose
        # following byte has no extended-token meaning: coalesce into a
        # TEXT run so the byte still round-trips.
        if text_start < 0:
            text_start = i
        text_chars.append(chr(b))
        i += 1
    yield from flush()


def scan_program(data: bytes, *, dialect: Dialect = BASIC_II) -> Iterator[LineRecord]:
    """Walk a ``&0D``-framed stored program, scanning each line body.

    Args:
        data: A tokenised program as stored on disc or in memory,
            terminated by the ``&0D &FF`` end marker.
        dialect: The BBC BASIC variant whose token tables to use, passed
            through to :func:`scan`. Defaults to
            :data:`~oaknut.basic.BASIC_II`.

    Yields:
        One :class:`LineRecord` per line, in storage order, each carrying
        the line number and its body :class:`Token` stream.

    Raises:
        DetokeniseError: The framing is malformed — a missing line
            marker, a truncated header or reference, or an impossible
            length byte.
    """
    n = len(data)
    i = 0
    while i < n:
        if data[i] != _CR:
            raise MissingLineMarkerError(offset=i, found=data[i])
        if i + 1 >= n:
            raise TruncatedProgramError(offset=i, detail="line marker with no line number")
        if data[i + 1] == _END_MARKER:
            break
        if i + HEADER_LENGTH > n:
            raise TruncatedProgramError(offset=i, detail="incomplete line header")
        line_number = (data[i + 1] << 8) | data[i + 2]
        length = data[i + 3]
        if length < HEADER_LENGTH or i + length > n:
            raise InvalidLineLengthError(offset=i, length=length)
        body = data[i + HEADER_LENGTH : i + length]
        tokens = tuple(scan(body, base_offset=i + HEADER_LENGTH, dialect=dialect))
        yield LineRecord(line_number=line_number, tokens=tokens, start=i)
        i += length
