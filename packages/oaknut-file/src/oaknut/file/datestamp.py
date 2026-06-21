"""The RISC OS load/exec datestamp codec.

When the top twelve bits of a file's load address are ``0xFFF`` the
load/exec pair no longer holds a real address: bits 8–19 of the load
address carry a 12-bit filetype, and the remaining bits hold a 40-bit
datestamp — a count of centiseconds since 1900-01-01 00:00:00. The
most significant byte of that count is the low byte of the load
address; the low four bytes are the exec address.

There is a single datestamp per file (RISC OS keeps no separate
creation / modification / access times), and it carries no timezone, so
this module works in naive local time throughout.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from oaknut.file.exceptions import DatestampRangeError

#: The RISC OS datestamp epoch — naive, no timezone.
RISCOS_EPOCH = datetime(1900, 1, 1)

#: A datestamped load address has all of its top twelve bits set.
_FILETYPE_MARKER = 0xFFF00000

#: The datestamp is a 40-bit centisecond count.
_MAX_CENTISECONDS = (1 << 40) - 1

#: One centisecond expressed in microseconds, the unit ``timedelta`` keeps.
_MICROSECONDS_PER_CENTISECOND = 10_000


def is_datestamped(load_address: int) -> bool:
    """True if a load address carries a RISC OS filetype and datestamp."""
    return (load_address & _FILETYPE_MARKER) == _FILETYPE_MARKER


def decode_datestamp(load_address: int, exec_address: int) -> datetime | None:
    """The datestamp encoded in a load/exec pair, or None if unstamped.

    Returns a naive local :class:`~datetime.datetime` at the field's
    centisecond resolution, or ``None`` when the load address holds a
    real address rather than a filetype/datestamp.
    """
    if not is_datestamped(load_address):
        return None
    centiseconds = ((load_address & 0xFF) << 32) | (exec_address & 0xFFFFFFFF)
    return RISCOS_EPOCH + timedelta(
        microseconds=centiseconds * _MICROSECONDS_PER_CENTISECOND
    )


def encode_datestamp(when: datetime) -> tuple[int, int]:
    """Encode a naive local datetime as ``(load_high_byte, exec_word)``.

    The returned high byte occupies bits 0–7 of the load address (the
    caller ORs in the ``0xFFF`` marker and the filetype); the exec word
    is the low four bytes. Sub-centisecond resolution is truncated. An
    instant outside the 40-bit field's range raises
    :class:`~oaknut.file.exceptions.DatestampRangeError`.
    """
    delta = when - RISCOS_EPOCH
    centiseconds = (
        delta.days * 8_640_000
        + delta.seconds * 100
        + delta.microseconds // _MICROSECONDS_PER_CENTISECOND
    )
    if not 0 <= centiseconds <= _MAX_CENTISECONDS:
        raise DatestampRangeError(
            f"{when.isoformat()} is outside the RISC OS datestamp range "
            "(1900-01-01 to the 40-bit centisecond overflow)"
        )
    return (centiseconds >> 32) & 0xFF, centiseconds & 0xFFFFFFFF
