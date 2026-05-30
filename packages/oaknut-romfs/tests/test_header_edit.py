"""Tests for the ROMFS header getters/setters (copyright, version)."""

from __future__ import annotations

import pytest
from oaknut.romfs.exceptions import ROMFSError
from oaknut.romfs.romfs import (
    ROMFS,
    build_rom_image,
    get_copyright,
    get_version,
    set_copyright,
    set_version,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"


def test_get_copyright_and_version():
    image = build_rom_image(title="X", copyright="(C) me", version=42, size=16384)
    assert get_copyright(image) == "(C) me"
    assert get_version(image) == 42


def test_set_version_is_in_place():
    image = build_rom_image(title="X", size=16384)
    updated = set_version(image, 9)
    assert get_version(updated) == 9
    # Only the single version byte changed; nothing else moved.
    assert updated[:8] == image[:8]
    assert updated[9:] == image[9:]


def test_set_version_range_checked():
    image = build_rom_image(title="X", size=16384)
    with pytest.raises(ROMFSError):
        set_version(image, 256)


def test_set_copyright_same_length_is_in_place():
    image = build_rom_image(title="X", copyright="(C) 1984AB", size=16384)  # 10 chars
    updated = set_copyright(image, "(C) 2026CD")  # also 10 chars
    assert get_copyright(updated) == "(C) 2026CD"
    assert len(updated) == len(image)
    # Same length: the handler and data did not move.
    assert ROMFS.from_bytes(updated).data_offset == ROMFS.from_bytes(image).data_offset


def test_set_copyright_length_change_rebuilds_and_preserves_content():
    # Build a ROM, add a file, then change the copyright length.
    from oaknut.filesystem import reader_for
    from oaknut.romfs.filesystem import AcornROMFS

    data = bytearray(build_rom_image(title="DISC", version=3, size=16384))
    reader = reader_for(data, writable=True)
    AcornROMFS().open(reader, AcornROMFS().probe(reader).geometry).write_bytes("HELLO", b"hi there")

    updated = set_copyright(bytes(data), "(C) 1984 Acornsoft")  # longer than the default
    rom = ROMFS.from_bytes(updated)
    assert rom.copyright == "(C) 1984 Acornsoft"
    assert rom.title == "DISC"  # preserved
    assert rom.version == 3  # preserved
    assert rom.is_plain and rom.is_complete
    assert {f.name: f.data for f in rom.data_files}["HELLO"] == b"hi there"  # file survived


def test_set_copyright_must_begin_c():
    image = build_rom_image(title="X", size=16384)
    with pytest.raises(ROMFSError, match="begin"):
        set_copyright(image, "no copyright mark")


def test_set_copyright_length_change_refused_on_language_rom():
    # An Acornsoft cartridge has a language entry; changing the copyright
    # length would relocate its code, so a length change is refused.
    hopper = (ROMFS_DIRPATH / "Electron_Hopper.rom").read_bytes()
    with pytest.raises(ROMFSError, match="language entry"):
        set_copyright(hopper, "(C) a totally different length string")


def test_set_copyright_length_change_refused_on_composite_rom():
    # A same-length change would be fine, but a length change on a service-only
    # ROM that still carries trailing code (Zalaga) is refused.
    zalaga = (ROMFS_DIRPATH / "Zalaga.rom").read_bytes()
    original = get_copyright(zalaga)
    with pytest.raises(ROMFSError):
        set_copyright(zalaga, original + " EXTENDED")
