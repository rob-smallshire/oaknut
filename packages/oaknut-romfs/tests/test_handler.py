"""Tests for the ROM filing-system service handler assembler.

The handler is the canonical mkromfs / NAUG &0D/&0E handler. Its length and
layout are pinned by mkromfs (81 bytes; filing-system data at &805D for an
empty header), which these tests anchor to. Execution on real hardware is
to be confirmed against a 6502 emulator.
"""

from __future__ import annotations

from oaknut.romfs.handler import HANDLER_LENGTH, build_rfs_handler


def test_handler_is_81_bytes():
    # Matches mkromfs: a 12-byte empty header + 81-byte handler puts data at
    # &805D (0x8000 + 0x5D).
    assert HANDLER_LENGTH == 81
    assert len(build_rfs_handler(0x800C, 0x805D)) == 81


def test_handler_entry_and_data_pointer():
    handler = build_rfs_handler(0x800C, 0x805D)
    # Entry: CMP #&0D / BEQ ; CMP #&0E / BEQ ; RTS.
    assert handler[0:2] == bytes([0xC9, 0x0D])
    assert handler[4:6] == bytes([0xC9, 0x0E])
    # The data address is poked little-endian: LDA #&5D / STA &F6 / LDA #&80.
    assert bytes([0xA9, 0x5D, 0x85, 0xF6, 0xA9, 0x80, 0x85, 0xF7]) in handler
    # OSRDRM is called for the OSRDRM-capable path.
    assert bytes([0x20, 0xB9, 0xFF]) in handler


def test_data_address_is_relocated_into_the_operands():
    handler = build_rfs_handler(0x800C, 0x9ABC)
    assert bytes([0xA9, 0xBC, 0x85, 0xF6, 0xA9, 0x9A, 0x85, 0xF7]) in handler


def test_internal_jumps_track_the_base_address():
    # JMP/JSR to internal labels are absolute, so they shift with the base.
    low = build_rfs_handler(0x8000, 0x9000)
    high = build_rfs_handler(0x8100, 0x9000)
    assert low != high  # the absolute operands differ by the base delta
    assert len(low) == len(high) == HANDLER_LENGTH
