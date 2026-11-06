"""IBM-format FM and MFM track encoding, as used by Acorn floppy controllers.

Both the Intel 8271 (single-density FM) and the WD1770 (FM and MFM) lay
tracks out in the IBM System 34 style: gaps, an ID address mark carrying
the sector's C/H/R/N, a CRC, a gap, then a data (or deleted-data) address
mark, the sector bytes and a second CRC.

Bits on the track are handled here as *half-cells*: a string of ``"0"`` and
``"1"`` characters in which every data bit is preceded by a clock slot, so
one byte occupies sixteen half-cells in either density. The densities differ
only in which clock slots carry a flux transition:

* **FM** writes a transition in every clock slot, except within an address
  mark, whose missing clocks (clock pattern ``0xC7``) make the mark
  distinguishable from data.
* **MFM** writes a clock transition only between two zero data bits. Its
  address marks are preceded by three ``0xA1`` sync bytes written with one
  clock deliberately omitted (the ``0x4489`` pattern).

Strings make the decoder simple and fast: an address mark at any bit offset
is found with :meth:`str.find`.

The CRC is CRC-16/CCITT (polynomial ``0x1021``, preset ``0xFFFF``), computed
over the address-mark byte and the field that follows it. In MFM the three
sync bytes are included, which takes the preset to ``0xCDB4``.
"""

from __future__ import annotations

__all__ = [
    "BYTE_HALF_CELLS",
    "FM_MARK_CLOCK",
    "ID_MARK",
    "DATA_MARK",
    "DELETED_DATA_MARK",
    "FM_ID_MARK",
    "FM_DATA_MARK",
    "FM_DELETED_DATA_MARK",
    "MFM_SYNC",
    "MFM_SYNC_CRC",
    "crc16",
    "fm_encode",
    "fm_mark",
    "mfm_encode",
    "decode_byte",
    "decode_bytes",
]

#: Half-cells per encoded byte, in either density.
BYTE_HALF_CELLS = 16

#: The clock pattern written with every FM address mark.
FM_MARK_CLOCK = 0xC7

#: Address-mark data bytes, common to FM and MFM.
ID_MARK = 0xFE
DATA_MARK = 0xFB
DELETED_DATA_MARK = 0xF8

#: The CRC after the three MFM ``0xA1`` sync bytes.
MFM_SYNC_CRC = 0xCDB4


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT of *data*, continuing from *crc*."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def _fm_byte(data: int, clock: int) -> str:
    return "".join(f"{(clock >> bit) & 1}{(data >> bit) & 1}" for bit in range(7, -1, -1))


_FM_ORDINARY = tuple(_fm_byte(byte, 0xFF) for byte in range(256))


def fm_encode(data: bytes) -> str:
    """FM half-cells for *data*, each byte written with a full clock."""
    return "".join(_FM_ORDINARY[byte] for byte in data)


def fm_mark(mark: int) -> str:
    """FM half-cells for address-mark byte *mark* with the ``0xC7`` clock."""
    return _fm_byte(mark, FM_MARK_CLOCK)


FM_ID_MARK = fm_mark(ID_MARK)
FM_DATA_MARK = fm_mark(DATA_MARK)
FM_DELETED_DATA_MARK = fm_mark(DELETED_DATA_MARK)


def mfm_encode(data: bytes, previous_bit: int = 0) -> str:
    """MFM half-cells for *data*.

    *previous_bit* is the last data bit written before *data*, which decides
    whether the first byte's leading clock is set.
    """
    cells = []
    last = previous_bit
    for byte in data:
        for bit in range(7, -1, -1):
            value = (byte >> bit) & 1
            cells.append("01" if value else ("00" if last else "10"))
            last = value
    return "".join(cells)


#: One MFM ``0xA1`` sync byte with its missing clock (``0x4489``).
MFM_SYNC = "0100010010001001"


def decode_byte(cells: str) -> int:
    """The data byte in sixteen half-cells (the odd-numbered slots)."""
    return int(cells[1:16:2], 2)


def decode_bytes(cells: str, start: int, count: int) -> bytes:
    """*count* data bytes from the half-cells beginning at *start*.

    Bytes running off the end of *cells* decode as if the missing
    half-cells were zero.
    """
    span = cells[start : start + count * BYTE_HALF_CELLS]
    span = span.ljust(count * BYTE_HALF_CELLS, "0")
    return int(span[1::2], 2).to_bytes(count, "big") if count else b""
