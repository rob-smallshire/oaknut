"""The BBC BASIC II ``&8D`` line-number reference codec.

A line number referenced inside a program body (after ``GOTO``,
``GOSUB``, ``THEN``, ...) is stored as the token ``&8D`` followed by
three bytes. The encoding lifts every byte into ``&40``-``&FF`` and
gathers the four "dangerous" high bits into one scrambled control byte,
so none of the three can collide with ``&0D`` (the line terminator).

Both transforms are transcribed from the disassembly
(``encode_line_number`` at ``&88F5``, ``decode_line_number`` at
``&97EB``). The codec round-trips exactly for line numbers ``0``-``32767``;
above that the high bit is lost, which is the mechanism behind BASIC II's
32767 line-number ceiling.
"""

from __future__ import annotations

# The maximum line number that survives the &8D codec intact.
MAX_LINE_NUMBER = 32767


def encode_line_number(line_number: int) -> bytes:
    """Encode *line_number* as the 3 payload bytes following ``&8D``.

    The returned bytes do **not** include the ``&8D`` token itself; the
    caller prepends :data:`~oaknut.basic.tokens.LINE_NUMBER_TOKEN`.

    Args:
        line_number: The referenced line number (0-65535).

    Returns:
        The three encoded payload bytes.

    Raises:
        ValueError: *line_number* is outside 0-65535.
    """
    if not 0 <= line_number <= 0xFFFF:
        raise ValueError(f"line number out of range 0-65535: {line_number}")
    lo = line_number & 0xFF
    hi = (line_number >> 8) & 0xFF
    control = ((((lo & 0xC0) | ((hi & 0xC0) >> 2)) >> 2) ^ 0x54) & 0xFF
    byte2 = (lo & 0x3F) | 0x40
    byte3 = (hi | 0x40) & 0xFF
    return bytes((control, byte2, byte3))


def decode_line_number(payload: bytes) -> int:
    """Decode the 3 payload bytes following ``&8D`` back to a line number.

    Args:
        payload: Exactly the three bytes after the ``&8D`` token.

    Returns:
        The decoded line number.

    Raises:
        ValueError: *payload* is not exactly three bytes.
    """
    if len(payload) != 3:
        raise ValueError(f"line-number payload must be 3 bytes, got {len(payload)}")
    control, byte2, byte3 = payload
    t = (control << 2) & 0xFF
    lo = (t & 0xC0) ^ byte2
    hi = ((t << 2) & 0xFF) ^ byte3
    return lo | (hi << 8)
