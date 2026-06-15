"""De-tokenise a stored BBC BASIC II program into source text.

Mirrors the ROM's ``LIST`` walk: split the program into lines on the
``&0D`` start-of-line markers, render each line's number followed by its
de-tokenised body. Within a body, keyword tokens expand to their table
spelling, ``&8D`` references decode back to plain decimal, and bytes
inside a quoted string are emitted verbatim (no token expansion).

The returned string uses latin-1/code-point semantics: a stored byte
``b`` becomes ``chr(b)``, so the text round-trips byte-exactly through
:func:`oaknut.basic.tokenise`. Mapping to a host character set (Acorn,
UTF-8) is the caller's job — the CLI does it at its I/O boundary.

The line layout (from the disassembly) is::

    &0D <lineNo-hi> <lineNo-lo> <length> <body...>   ...   &0D &FF

where *length* counts the whole record from this ``&0D`` up to (not
including) the next one, so ``length = 4 + len(body)``.
"""

from __future__ import annotations

from oaknut.basic.exceptions import (
    InvalidLineLengthError,
    MissingLineMarkerError,
    TruncatedProgramError,
)
from oaknut.basic.linenumber import decode_line_number
from oaknut.basic.tokens import HEADER_LENGTH, LINE_NUMBER_TOKEN, TOKEN_TO_KEYWORD

_CR = 0x0D
_END_MARKER = 0xFF
_QUOTE = 0x22


def detokenise(data: bytes) -> str:
    """De-tokenise a BBC BASIC II program into source text.

    Args:
        data: A tokenised program, as stored on disc or in memory,
            terminated by the ``&0D &FF`` end marker.

    Returns:
        The program as numbered source text, lines separated by ``"\\n"``
        with a trailing newline. Empty for an empty program.

    Raises:
        DetokeniseError: The token stream is malformed — a missing line
            marker, a truncated header or reference, or an impossible
            length byte.
    """
    lines: list[str] = []
    i = 0
    n = len(data)
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
        lines.append(f"{line_number}{_detokenise_body(body, base_offset=i + HEADER_LENGTH)}")
        i += length
    return "".join(f"{line}\n" for line in lines)


def _detokenise_body(body: bytes, *, base_offset: int) -> str:
    """Expand one line's body bytes to text.

    *base_offset* is the absolute offset of ``body[0]`` within the whole
    program, so any fault can be reported at its true location.
    """
    out: list[str] = []
    i = 0
    n = len(body)
    in_string = False
    while i < n:
        b = body[i]
        if in_string:
            out.append(chr(b))
            if b == _QUOTE:
                in_string = False
            i += 1
            continue
        if b == _QUOTE:
            in_string = True
            out.append('"')
            i += 1
            continue
        if b == LINE_NUMBER_TOKEN:
            payload = body[i + 1 : i + 4]
            if len(payload) != 3:
                raise TruncatedProgramError(
                    offset=base_offset + i,
                    detail="incomplete &8D line-number reference",
                )
            out.append(str(decode_line_number(payload)))
            i += 4
            continue
        if b >= 0x80:
            # Unknown high bytes (e.g. the &CE gap) fall back to a raw
            # character so the bytes still round-trip.
            out.append(TOKEN_TO_KEYWORD.get(b, chr(b)))
            i += 1
            continue
        out.append(chr(b))
        i += 1
    return "".join(out)
