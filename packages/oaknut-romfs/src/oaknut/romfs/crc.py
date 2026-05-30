"""The CRC used by ROMFS / Cassette Filing System blocks.

Both the block header CRC and the block data CRC are CRC-16/XMODEM:
polynomial ``0x1021``, initial value ``0x0000``, processed
most-significant-bit first with no input/output reflection. On the ROM the
16-bit result is stored **big-endian** (most-significant byte first),
unlike the little-endian multi-byte integer fields of the header.

See ``docs/romfs-format-spec.md`` §3.
"""

from __future__ import annotations

from collections.abc import Iterable

_POLYNOMIAL = 0x1021


def crc16_ccitt(data: Iterable[int]) -> int:
    """Return the CRC-16/XMODEM of *data* (any iterable of byte values).

    Accepts ``bytes``, ``bytearray``, ``memoryview`` or any iterable of
    integers in ``0..255``. The empty input has CRC ``0x0000``; the
    canonical check string ``b"123456789"`` has CRC ``0x31C3``.
    """
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _POLYNOMIAL) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
