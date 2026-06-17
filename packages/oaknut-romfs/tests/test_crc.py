"""Tests for the ROMFS / CFS block CRC.

The CRC is CRC-16/XMODEM (polynomial 0x1021, initial value 0x0000,
most-significant-bit first, no reflection), stored big-endian on the ROM.
See ``docs/romfs-format-spec.md`` §3.
"""

from __future__ import annotations

import struct

from oaknut.romfs.crc import crc16_ccitt


def test_empty_input_is_zero():
    assert crc16_ccitt(b"") == 0x0000


def test_xmodem_standard_check_value():
    # The canonical CRC-16/XMODEM check string "123456789" -> 0x31C3.
    assert crc16_ccitt(b"123456789") == 0x31C3


def test_naug_example_header_record():
    # The header record from the New Advanced User Guide example:
    # a title block named "*EXAMPLE*", load=exec=0, block 0, length 0,
    # flag &C0 (last + empty), end-of-file address &809E. The CRC is taken
    # over the header bytes from the name through the end-of-file address.
    record = (
        b"*EXAMPLE*\x00"
        + struct.pack("<IIHH", 0, 0, 0, 0)  # load, exec, block, length
        + bytes([0xC0])  # flag
        + struct.pack("<I", 0x809E)  # end-of-file address
    )
    assert crc16_ccitt(record) == 0x6F24


def test_real_block_header_crc_from_hopper():
    # The !BOOT header from Electron_Hopper.rom (at &80DA): the header
    # bytes from the name through the end-of-file address must produce the
    # stored header CRC of 0x329B (big-endian on the ROM).
    name = b"!BOOT\x00"
    header = (
        name
        + struct.pack("<II", 0x00001E86, 0x00001E86)  # load, exec
        + struct.pack("<HH", 0x0000, 0x003A)  # block number, length
        + bytes([0x80])  # flag: last block
        + struct.pack("<I", 0x00008130)  # end-of-file address
    )
    assert crc16_ccitt(header) == 0x329B


def test_accepts_bytearray_and_memoryview():
    assert crc16_ccitt(bytearray(b"123456789")) == 0x31C3
    assert crc16_ccitt(memoryview(b"123456789")) == 0x31C3
