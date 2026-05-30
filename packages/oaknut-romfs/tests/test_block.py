"""Tests for the CFS block-header codec.

Covers the marker/flag constants, parsing a real header from the Hopper
reference image, the flag-bit properties, and a serialise/parse round-trip
(needed for the write path). See ``docs/romfs-format-spec.md`` §2.
"""

from __future__ import annotations

import struct

import pytest

from oaknut.romfs.block import (
    END_OF_FILESYSTEM,
    FLAG_EMPTY,
    FLAG_LAST,
    FLAG_LOCKED,
    INTER_BLOCK_MARKER,
    SYNC_BYTE,
    BlockHeader,
)
from oaknut.romfs.exceptions import CRCError


def test_marker_byte_values():
    assert SYNC_BYTE == 0x2A
    assert INTER_BLOCK_MARKER == 0x23
    assert END_OF_FILESYSTEM == 0x2B


def test_flag_bit_values():
    assert FLAG_LAST == 0x80
    assert FLAG_EMPTY == 0x40
    assert FLAG_LOCKED == 0x01


def _hopper_boot_block() -> bytes:
    """The on-ROM bytes of Hopper's !BOOT header block (no data appended)."""
    fields = (
        b"!BOOT\x00"
        + struct.pack("<II", 0x00001E86, 0x00001E86)  # load, exec
        + struct.pack("<HH", 0x0000, 0x003A)  # block number, length
        + bytes([FLAG_LAST])  # flag
        + struct.pack("<I", 0x00008130)  # end-of-file address
    )
    return bytes([SYNC_BYTE]) + fields + (0x329B).to_bytes(2, "big")


def test_parse_real_header():
    header, data_offset = BlockHeader.parse(_hopper_boot_block())
    assert header.name == "!BOOT"
    assert header.load_address == 0x00001E86
    assert header.exec_address == 0x00001E86
    assert header.block_number == 0
    assert header.block_length == 0x3A
    assert header.end_address == 0x8130
    # The data begins immediately after the 2-byte header CRC.
    assert data_offset == len(_hopper_boot_block())


def test_flag_properties():
    last = BlockHeader("X", 0, 0, 0, 0x3A, FLAG_LAST, 0)  # non-empty last block
    assert last.is_last and not last.is_empty and not last.is_locked

    title = BlockHeader("X", 0, 0, 0, 0, FLAG_LAST | FLAG_LOCKED, 0)  # &81 corpus title block
    assert title.is_last and title.is_locked and title.is_empty  # length 0 -> empty

    mid = BlockHeader("X", 0, 0, 1, 256, 0x00, 0)
    assert not mid.is_last


def test_parse_at_offset():
    block = b"\xaa\xbb\xcc" + _hopper_boot_block()
    header, data_offset = BlockHeader.parse(block, 3)
    assert header.name == "!BOOT"
    assert data_offset == len(block)


def test_parse_rejects_bad_crc():
    block = bytearray(_hopper_boot_block())
    block[-1] ^= 0xFF  # corrupt the stored header CRC
    with pytest.raises(CRCError):
        BlockHeader.parse(bytes(block))


def test_serialise_round_trip():
    original = BlockHeader(
        name="HOPOBJ",
        load_address=0x3000,
        exec_address=0x3000,
        block_number=0x22,
        block_length=0x57,
        flag=FLAG_LAST | FLAG_LOCKED,
        end_address=0xA839,
    )
    encoded = original.to_bytes()
    assert encoded[0] == SYNC_BYTE
    parsed, data_offset = BlockHeader.parse(encoded)
    assert parsed == original
    assert data_offset == len(encoded)


def test_serialise_matches_real_bytes():
    # Rebuilding Hopper's !BOOT header must reproduce its exact on-ROM bytes.
    header = BlockHeader("!BOOT", 0x1E86, 0x1E86, 0, 0x3A, FLAG_LAST, 0x8130)
    assert header.to_bytes() == _hopper_boot_block()
