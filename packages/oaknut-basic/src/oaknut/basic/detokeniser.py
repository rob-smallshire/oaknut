"""De-tokenise BBC BASIC II bytes into source text.

The de-tokeniser is the *text projection* of the token scanner
(:mod:`oaknut.basic.scanner`): :func:`detokenise` mirrors the ROM's
``LIST`` walk over the ``&0D``-framed stored form — rendering each line's
number followed by its body — while :func:`detokenise_body` flattens one
unframed line body. Both join the body :class:`~oaknut.basic.Token`
stream's values: keyword tokens expand to their table spelling, ``&8D``
references decode back to plain decimal, and bytes inside a quoted string
are emitted verbatim (no token expansion). Where keyword *adjacency*
matters — ``?QPLOT`` is not re-typeable as a program — reach past the
text for :func:`oaknut.basic.scan` instead.

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

from oaknut.basic.dialect import BASIC_II, Dialect
from oaknut.basic.scanner import scan, scan_program


def detokenise(data: bytes, *, dialect: Dialect = BASIC_II) -> str:
    """De-tokenise a stored BBC BASIC program into source text.

    Args:
        data: A tokenised program, as stored on disc or in memory,
            terminated by the ``&0D &FF`` end marker.
        dialect: The BBC BASIC variant whose token tables to use.
            Defaults to :data:`~oaknut.basic.BASIC_II`; pass
            :data:`~oaknut.basic.BASIC_V` for Archimedes / RISC OS
            programs so the ``&C6``/``&C7``/``&C8`` escape tokens and the
            re-purposed single-byte tokens decode correctly.

    Returns:
        The program as numbered source text, lines separated by ``"\\n"``
        with a trailing newline. Empty for an empty program.

    Raises:
        DetokeniseError: The token stream is malformed — a missing line
            marker, a truncated header or reference, or an impossible
            length byte.
    """
    return "".join(
        f"{record.line_number}{''.join(token.value for token in record.tokens)}\n"
        for record in scan_program(data, dialect=dialect)
    )


def detokenise_body(data: bytes, *, dialect: Dialect = BASIC_II) -> str:
    """De-tokenise an unframed line body into text.

    Unlike :func:`detokenise`, this expects a line *body* — inline token
    bytes with no ``&0D`` framing and no leading line number, the form
    BBC Micro Bot / Owlet programs and AUTO-style entry arrive in. It is
    the text join of :func:`oaknut.basic.scan`; when keyword adjacency
    matters, consume that token stream directly instead.

    Args:
        data: A line body of inline token bytes.
        dialect: The BBC BASIC variant whose token tables to use, passed
            through to :func:`scan`. Defaults to
            :data:`~oaknut.basic.BASIC_II`.

    Returns:
        The body as source text, using latin-1/code-point semantics so it
        round-trips byte-exactly through :func:`oaknut.basic.tokenise`.

    Raises:
        DetokeniseError: A ``&8D`` line-number reference is truncated.
    """
    return "".join(token.value for token in scan(data, dialect=dialect))
