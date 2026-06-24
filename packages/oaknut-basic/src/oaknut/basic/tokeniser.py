"""Tokenise BBC BASIC II source text into a stored program.

This reproduces the ROM's line-input "crunch": each numbered source line
is framed into a ``&0D <hi> <lo> <length>`` record whose body is the
tokenised statement text. The body crunch is a small state machine over
two pieces of state, matching the disassembly:

- **mid** — middle-of-statement (vs. start-of-statement). Pseudo-variables
  (``PAGE``, ``PTR``, ...) tokenise to their assignment form at the start
  of a statement and their function form elsewhere.
- **armed** — the next decimal literal is a line-number reference and is
  encoded with the ``&8D`` token. Armed by ``GOTO``/``THEN``/... and
  disarmed by anything that is not a space, comma, or the literal itself.

Keywords match by scanning the table in ROM order and taking the first
full (or ``.``-abbreviated) match; the flag byte then drives the state
machine. Tokenising is suppressed inside string literals, after ``REM``
and ``DATA``, after a statement-leading ``*`` (OSCLI), and across ``&``
hex and decimal literals, all of which are copied verbatim.

The source is handled with latin-1/code-point semantics — a character
``c`` contributes the byte ``ord(c)`` — so the output round-trips
byte-exactly with :func:`oaknut.basic.detokenise`. Mapping a host
character set (Acorn, UTF-8) onto those code points is the caller's job;
the CLI does it at its I/O boundary.
"""

from __future__ import annotations

from oaknut.basic.exceptions import (
    AlreadyNumberedError,
    LineNumberOrderError,
    LineNumberRangeError,
    LineTooLongError,
    UnnumberedLineError,
)
from oaknut.basic.linenumber import MAX_LINE_NUMBER, encode_line_number
from oaknut.basic.numbering import (
    DEFAULT_LINE_NUMBER,
    DEFAULT_LINE_STEP,
    LINE_SEPARATOR_RE,
    number_lines,
)
from oaknut.basic.tokens import (
    FLAG_CONDITIONAL,
    FLAG_FN_PROC,
    FLAG_LINE_NUMBER,
    FLAG_MIDDLE,
    FLAG_PSEUDO_VAR,
    FLAG_START,
    FLAG_STOP_LINE,
    HEADER_LENGTH,
    KEYWORDS,
    LINE_NUMBER_TOKEN,
    MAX_BODY_LENGTH,
    PSEUDO_VAR_ASSIGN_OFFSET,
)

_CR = 0x0D
_END_MARKER = 0xFF


def _split_source_lines(source: str) -> list[str]:
    return LINE_SEPARATOR_RE.split(source)

# Keyword entries grouped by first character, preserving ROM order within
# each group, so the crunch only scans the relevant group.
_KEYWORDS_BY_FIRST: dict[str, list[tuple[str, int, int]]] = {}
for _keyword, _token, _flags in KEYWORDS:
    _KEYWORDS_BY_FIRST.setdefault(_keyword[0], []).append((_keyword, _token, _flags))


def tokenise(source: str, *, start: int | None = None, step: int | None = None) -> bytes:
    """Tokenise BBC BASIC II source text into a stored program.

    Args:
        source: BBC BASIC source. By default every non-blank line must
            begin with a line number, as a saved ``LIST`` would.
        start: First line number for auto-numbering. Supplying *start*
            and/or *step* turns auto-numbering on (as typing under
            ``AUTO`` would); the source must then have **no** line
            numbers. Defaults to 10 when only *step* is given.
        step: Increment for auto-numbering. Defaults to 10 when only
            *start* is given.

    Returns:
        The tokenised program bytes, terminated by ``&0D &FF``.

    Raises:
        TokeniseError: The source is malformed — an unnumbered line (or,
            under auto-numbering, an already-numbered one), a line number
            out of range or out of order, or a line that tokenises beyond
            the maximum storable length.
    """
    auto_number = start is not None or step is not None
    lines = _split_source_lines(source)
    if auto_number:
        _reject_existing_numbers(lines)
        renumbered = number_lines(
            source,
            start=DEFAULT_LINE_NUMBER if start is None else start,
            step=DEFAULT_LINE_STEP if step is None else step,
        )
        lines = _split_source_lines(renumbered)

    out = bytearray()
    previous_number: int | None = None
    for line_index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        split = _split_line_number(line)
        if split is None:
            raise UnnumberedLineError(line_index, line)
        line_number, body_text = split
        if line_number > MAX_LINE_NUMBER:
            raise LineNumberRangeError(line_index, line_number, line)
        if previous_number is not None and line_number <= previous_number:
            raise LineNumberOrderError(line_index, line_number, previous_number, line)
        previous_number = line_number

        body = _tokenise_body(body_text, line_index=line_index, line_text=line)
        if len(body) > MAX_BODY_LENGTH:
            raise LineTooLongError(line_index, line_number, len(body), line)

        out += bytes(
            (_CR, (line_number >> 8) & 0xFF, line_number & 0xFF, HEADER_LENGTH + len(body))
        )
        out += body

    out += bytes((_CR, _END_MARKER))
    return bytes(out)


def _reject_existing_numbers(lines: list[str]) -> None:
    """Raise if any non-blank line already carries a line number."""
    for line_index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        split = _split_line_number(line)
        if split is not None:
            raise AlreadyNumberedError(line_index, split[0], line)


def _split_line_number(line: str) -> tuple[int, str] | None:
    """Split a leading line number off *line*.

    Returns ``(number, body)`` where *body* is everything after the
    digits (its leading space, if any, is significant and kept), or
    ``None`` if the line has no leading number. Whitespace before the
    number is insignificant and dropped.
    """
    i = 0
    n = len(line)
    while i < n and line[i] == " ":
        i += 1
    digits_start = i
    while i < n and "0" <= line[i] <= "9":
        i += 1
    if i == digits_start:
        return None
    return int(line[digits_start:i]), line[i:]


def _is_name_char(c: str) -> bool:
    """True for the BBC's identifier characters (``0-9 A-Z a-z _``)."""
    return c.isascii() and (c.isalnum() or c == "_")


def _is_letter(c: str) -> bool:
    return ("A" <= c <= "Z") or ("a" <= c <= "z")


def _is_hex_digit(c: str) -> bool:
    return ("0" <= c <= "9") or ("A" <= c <= "F")


def _try_keyword(text: str, i: int) -> tuple[int, int, int] | None:
    """Match a keyword at ``text[i]``.

    Returns ``(token, consumed, flags)`` for the first full or
    ``.``-abbreviated match in ROM order, or ``None`` if the cursor does
    not begin a keyword (including a conditional keyword suppressed by a
    following name character).
    """
    group = _KEYWORDS_BY_FIRST.get(text[i])
    if group is None:
        return None
    n = len(text)
    for keyword, token, flags in group:
        klen = len(keyword)
        p = 0
        matched = True
        abbreviated = False
        while p < klen:
            if i + p >= n:
                matched = False
                break
            source_char = text[i + p]
            if source_char == keyword[p]:
                p += 1
                continue
            if source_char == ".":
                abbreviated = True
                break
            matched = False
            break
        if not matched:
            continue
        if abbreviated:
            return token, p + 1, flags
        # Full match. A conditional keyword is suppressed when a name
        # character follows, so it stays part of an identifier.
        if flags & FLAG_CONDITIONAL and i + klen < n and _is_name_char(text[i + klen]):
            return None
        return token, klen, flags
    return None


def _tokenise_body(text: str, *, line_index: int, line_text: str) -> bytearray:
    """Crunch one statement-text body into tokenised bytes."""
    out = bytearray()
    i = 0
    n = len(text)
    mid = False  # &3B: start-of-statement
    # &3C: next decimal literal is a line-number reference. The body starts
    # *armed*: on the real machine the leading line number is crunched with
    # this flag pre-set, and encoding a number does not clear it, so the arm
    # carries into the body until a name, operator, ':' or disarming keyword
    # clears it (e.g. `TO1` -> TO, &8D-encoded 1).
    armed = True

    while i < n:
        c = text[i]

        if c == '"':  # string literal — copy verbatim through the closing quote
            out.append(ord('"'))
            i += 1
            while i < n and text[i] != '"':
                out.append(ord(text[i]))
                i += 1
            if i < n:
                out.append(ord('"'))
                i += 1
            # A string literal leaves both state flags untouched: it does
            # not start a fresh statement (so `"s" *` is still OSCLI) and
            # does not disarm (so `"s" 1` still encodes the 1).
            continue

        if c == "&":  # hex constant — copy & and the hex-digit run verbatim
            out.append(ord("&"))
            i += 1
            while i < n and _is_hex_digit(text[i]):
                out.append(ord(text[i]))
                i += 1
            mid = True  # a value, but does not disarm (`&FF 1` encodes the 1)
            continue

        if c == " ":  # space — emitted, but leaves the state (incl. armed) alone
            out.append(0x20)
            i += 1
            continue

        if c == ":":  # statement separator — back to start of statement
            out.append(ord(":"))
            i += 1
            mid, armed = False, False
            continue

        if c == ",":  # comma — keeps armed, so ON X GOTO 10,20,30 encodes each
            out.append(ord(","))
            i += 1
            continue

        if c == "*" and not mid:  # statement-leading * — OSCLI, rest of line literal
            while i < n:
                out.append(ord(text[i]))
                i += 1
            break

        if "0" <= c <= "9":  # decimal literal
            if armed:
                value, i = _read_decimal(text, i)
                if value > MAX_LINE_NUMBER:
                    raise LineNumberRangeError(line_index, value, line_text)
                out.append(LINE_NUMBER_TOKEN)
                out += encode_line_number(value)
                # Stay armed: commas and spaces keep it, so every entry in
                # a list such as RESTORE 100,200 is encoded. Only an
                # identifier, ':', an operator, or a MIDDLE/START keyword
                # disarms.
                mid = True
            else:
                while i < n and (("0" <= text[i] <= "9") or text[i] == "."):
                    out.append(ord(text[i]))
                    i += 1
                mid = True
            continue

        if c == ".":  # a number beginning with a decimal point (e.g. .5)
            while i < n and (("0" <= text[i] <= "9") or text[i] == "."):
                out.append(ord(text[i]))
                i += 1
            mid, armed = True, False
            continue

        if "A" <= c <= "W":  # potential keyword
            match = _try_keyword(text, i)
            if match is not None:
                token, consumed, flags = match
                emit = token
                if flags & FLAG_PSEUDO_VAR and not mid:
                    emit = token + PSEUDO_VAR_ASSIGN_OFFSET
                out.append(emit)
                i += consumed
                # Statement state. A START keyword (THEN/ELSE) resets to
                # start-of-statement and disarms; a MIDDLE keyword (most
                # commands) goes mid-statement and disarms. A value/function
                # keyword (TO, DIV, GET$, RND, ...) changes neither — it does
                # not disarm (so AND0 -> AND, &8D 0) and does not flip to
                # mid-statement (so a following pseudo-variable stays in its
                # assignment form). FN/PROC state follows the name below.
                if flags & FLAG_START:
                    mid, armed = False, False
                elif flags & FLAG_MIDDLE:
                    mid, armed = True, False
                if flags & FLAG_LINE_NUMBER:
                    armed = True
                if flags & FLAG_FN_PROC:
                    name_start = i
                    while i < n and _is_name_char(text[i]):
                        out.append(ord(text[i]))
                        i += 1
                    if i > name_start:  # consumed an identifier -> read a name
                        mid, armed = True, False
                if flags & FLAG_STOP_LINE:
                    while i < n:
                        out.append(ord(text[i]))
                        i += 1
                    break
                continue
            # Not a keyword: fall through and read it as an identifier.

        if _is_letter(c) or c == "_":  # identifier
            while i < n and _is_name_char(text[i]):
                out.append(ord(text[i]))
                i += 1
            mid, armed = True, False
            continue

        # An operator or any other character: goes mid-statement (so a
        # following pseudo-variable is its function form, and a later '*'
        # is multiply rather than OSCLI) and disarms.
        out.append(ord(c))
        i += 1
        mid, armed = True, False

    return out


def _read_decimal(text: str, i: int) -> tuple[int, int]:
    """Read a run of decimal digits from *i*, returning ``(value, end)``."""
    start = i
    n = len(text)
    while i < n and "0" <= text[i] <= "9":
        i += 1
    return int(text[start:i]), i
