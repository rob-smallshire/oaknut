"""Tests for creating fresh ROMFS images."""

from __future__ import annotations

import pytest
from oaknut.romfs.exceptions import ROMFSError
from oaknut.romfs.romfs import ROMFS, build_rom_image


def test_created_rom_round_trips():
    image = build_rom_image(title="GAMES", size=16384)
    assert len(image) == 16384
    rom = ROMFS.from_bytes(image)
    assert rom.title == "GAMES"
    assert rom.header_title == "GAMES"
    assert rom.copyright == "(C) oaknut"
    assert rom.rom_type == 0x82  # service-only ROM
    assert rom.is_complete
    assert rom.is_plain
    assert rom.data_files == ()  # no files yet, just the title block
    # Re-serialising the parsed image reproduces it exactly.
    assert rom.to_bytes() == image


def test_data_offset_matches_the_mkromfs_anchor():
    # mkromfs documents data at 0x805D for an empty header, growing by the
    # title and copyright lengths (no version string).
    image = build_rom_image(title="X", copyright="(C)", size=16384)
    rom = ROMFS.from_bytes(image)
    assert rom.data_offset == 0x5D + len("X") + len("(C)")


@pytest.mark.parametrize("size", [8192, 16384])
def test_supported_sizes(size: int):
    rom = ROMFS.from_bytes(build_rom_image(title="MINI", size=size))
    assert rom.title == "MINI"


def test_title_too_long_is_rejected():
    with pytest.raises(ROMFSError):
        build_rom_image(title="TOOLONGTITLE", size=16384)  # > 8 chars


def test_copyright_must_begin_c():
    with pytest.raises(ROMFSError):
        build_rom_image(title="X", copyright="no copyright mark", size=16384)


def test_create_then_add_a_file_round_trips():
    # A freshly-created ROM is plain and complete, so it is writable: build
    # it, mount it writable, add a file, and read it back.
    from oaknut.filesystem import reader_for
    from oaknut.romfs.filesystem import AcornROMFS

    data = bytearray(build_rom_image(title="DISC", size=16384))
    reader = reader_for(data, writable=True)
    fs = AcornROMFS()
    mount = fs.open(reader, fs.probe(reader).geometry)
    mount.write_bytes("README", b"hello, world")

    reparsed = ROMFS.from_bytes(bytes(data))
    assert reparsed.title == "DISC"
    by_name = {f.name: f for f in reparsed.data_files}
    assert by_name["README"].data == b"hello, world"
