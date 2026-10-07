"""ROMFS says why it declines an image (#82)."""

from __future__ import annotations

from oaknut.filesystem import Rejection, create_filesystem, reader_for


def _reason(image: bytes) -> str:
    with reader_for(bytes(image)) as reader:
        verdict = create_filesystem("acorn-romfs").probe(reader)
    assert isinstance(verdict, Rejection), verdict
    assert verdict.filesystem == "acorn-romfs"
    return verdict.reason


def test_too_small():
    assert _reason(b"\x00" * 8) == "image too small to be a paged ROM"


def test_no_sync_byte():
    assert _reason(b"\x00" * 16384) == "no ROMFS block: no &2A sync byte after the ROM header"


def test_sync_bytes_without_a_valid_block():
    # &FF filler, so a header following each sync byte fails its CRC.
    image = bytearray(b"\xff" * 16384)
    image[0x100] = image[0x200] = 0x2A
    assert _reason(image) == (
        "no ROMFS block: none of the 2 &2A sync bytes starts a block with a valid header CRC"
    )
