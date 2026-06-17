"""Tests for the ROMFS write path.

The medium is a ≤16 KiB ROM, so the serialiser rebuilds the whole image.
The strongest check is an exact round-trip over the corpus: re-serialising
an unchanged ROMFS must reproduce the original bytes — proving the
block-chain builder (header placement, &23 markers, end-of-file addresses,
CRCs) and the preservation of the header/handler prefix and any opaque
trailing content are all byte-accurate.
"""

from __future__ import annotations

import pytest
from oaknut.romfs.exceptions import ROMFullError
from oaknut.romfs.romfs import ROMFS, ROMFSFile

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"


@pytest.mark.parametrize("filepath", sorted(ROMFS_DIRPATH.glob("*.rom")), ids=lambda p: p.name)
def test_round_trip_is_byte_exact(filepath):
    original = filepath.read_bytes()
    rebuilt = ROMFS.from_bytes(original).to_bytes()
    assert rebuilt == original


def test_to_bytes_preserves_image_size():
    for filepath in ROMFS_DIRPATH.glob("*.rom"):
        rom = ROMFS.from_bytes(filepath.read_bytes())
        assert len(rom.to_bytes()) == 16384


def test_non_derived_flag_bits_are_preserved():
    # The New Advanced User Guide example sets the &40 "no data" bit on the
    # zero-length title block; Acorn's own ROMs leave it clear. The reader must
    # capture that bit and the writer re-emit it, so a round-trip does not churn
    # the flag (the byte-exact corpus test relies on this for the tool-built
    # ROM, whose title block carries &40).
    from oaknut.romfs.block import FLAG_EMPTY

    tool_built = ROMFS.from_bytes((ROMFS_DIRPATH / "Snapper_mkromfs.rom").read_bytes())
    assert tool_built.files[0].flag_extra == FLAG_EMPTY  # &40 captured

    acornsoft = ROMFS.from_bytes((ROMFS_DIRPATH / "Electron_Snapper.rom").read_bytes())
    assert acornsoft.files[0].flag_extra == 0  # Acorn leaves it clear


def test_replace_file_data_reparses():
    rom = ROMFS.from_bytes((ROMFS_DIRPATH / "Electron_Hopper.rom").read_bytes())
    # Shrink HOPOBJ to a single small block; the image stays 16 KiB and
    # re-parses with the new contents and recomputed catalogue figures.
    new_files = tuple(
        ROMFSFile(f.name, f.load_address, f.exec_address, f.run_only, b"hello")
        if f.name == "HOPOBJ"
        else f
        for f in rom.files
    )
    mutated = rom.with_files(new_files)
    image = mutated.to_bytes()
    assert len(image) == 16384

    reparsed = ROMFS.from_bytes(image)
    hopobj = {f.name: f for f in reparsed.files}["HOPOBJ"]
    assert hopobj.data == b"hello"
    assert hopobj.length == 5
    assert hopobj.last_block_number == 0
    # The other files are untouched.
    assert {f.name: f.data for f in reparsed.files}["!BOOT"] == (
        {f.name: f.data for f in rom.files}["!BOOT"]
    )


def test_growth_beyond_capacity_raises():
    # Countdown To Doom is a language ROM: code sits immediately after the
    # filing system, so there is no padding to grow into. Adding a large
    # file must refuse rather than overwrite that code — and say so.
    rom = ROMFS.from_bytes((ROMFS_DIRPATH / "Electron_Countdown_To_Doom_1.rom").read_bytes())
    bloated = rom.with_files(rom.files + (ROMFSFile("BIG", 0, 0, False, b"\x00" * 8192),))
    with pytest.raises(ROMFullError, match="overwrite the .* program that follows"):
        bloated.to_bytes()


def test_plain_rom_full_message_names_the_capacity():
    # On a plain ROM there is no trailing program — the message says the FS
    # is simply too large for the ROM, not that it would overwrite anything.
    rom = ROMFS.from_bytes((ROMFS_DIRPATH / "Electron_Hopper.rom").read_bytes())
    bloated = rom.with_files(rom.files + (ROMFSFile("BIG", 0, 0, False, b"\x00" * 16384),))
    with pytest.raises(ROMFullError, match="too large for this 16 KiB ROM"):
        bloated.to_bytes()
