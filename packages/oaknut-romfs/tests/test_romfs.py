"""Tests for the native ROMFS read path, against the reference corpus.

Parses the paged-ROM header and walks the CFS block chain into files,
verifying every header and data CRC. Expected values are the decoded
catalogues recorded in ``docs/romfs-format-spec.md`` §6, with the Hopper
and Zalaga listings confirmed against real BBC ``*.`` output.
"""

from __future__ import annotations

import pytest
from oaknut.romfs.exceptions import NotAROMFSError
from oaknut.romfs.romfs import ROMFS

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"


def load(filename: str) -> ROMFS:
    return ROMFS.from_bytes((ROMFS_DIRPATH / filename).read_bytes())


def test_hopper_header():
    rom = load("Electron_Hopper.rom")
    assert rom.rom_type == 0xC2
    assert rom.header_title == "ROM Cartridge"
    assert rom.version == 1
    assert rom.copyright == "(C) 1984 Acornsoft"
    assert rom.title == "Hopper01"  # from the *Hopper01* title block


def test_hopper_catalogue():
    rom = load("Electron_Hopper.rom")
    catalogue = [
        (f.name, f.length, f.load_address, f.exec_address, f.locked) for f in rom.files
    ]
    assert catalogue == [
        ("*Hopper01*", 0x0000, 0x00000000, 0x00000000, True),
        ("!BOOT", 0x003A, 0x00001E86, 0x00001E86, False),
        ("HOPPER", 0x03D5, 0x00000000, 0x00000000, False),
        ("HOPOBJ", 0x2257, 0x00003000, 0x00003000, True),
    ]


def test_hopper_last_block_numbers():
    by_name = {f.name: f for f in load("Electron_Hopper.rom").files}
    assert by_name["HOPOBJ"].last_block_number == 0x22  # 35 blocks
    assert by_name["HOPPER"].last_block_number == 0x03  # 4 blocks
    assert by_name["!BOOT"].last_block_number == 0x00  # single block


def test_data_length_matches_catalogue_length():
    for f in load("Electron_Hopper.rom").files:
        assert len(f.data) == f.length


def test_zalaga_bbc_no_title_block():
    rom = load("Zalaga.rom")
    assert rom.rom_type == 0x82  # service-only ROM
    assert rom.header_title == "RFS id:298DE"
    assert rom.title == ""  # no *...* title block
    assert [f.name for f in rom.files] == ["ZALAGA"]
    zalaga = rom.files[0]
    assert zalaga.length == 0x2D25
    assert zalaga.load_address == 0x00003000
    assert zalaga.exec_address == 0x00004522
    assert zalaga.locked
    assert zalaga.last_block_number == 0x2D


def test_starship_is_two_cartridges():
    one = load("Electron_Starship_Command_1.rom")
    two = load("Electron_Starship_Command_2.rom")
    assert "STRCOM1" in [f.name for f in one.files]
    assert "STRCOM2" in [f.name for f in two.files]
    assert one.title == "Star01"
    assert two.title == "Star02"


def test_master_demo_cartridges_are_independent_not_spanning():
    # DEMO-A and DEMO-B are two self-contained cartridges, each a complete
    # ROMFS with its own title block and end marker — not a spanning set.
    a = load("BBC_Master_Demonstration_Cartridge_1.rom")
    b = load("BBC_Master_Demonstration_Cartridge_2.rom")
    assert a.title == "DEMO-A"
    assert b.title == "DEMO-B"
    # DEMO-A carries a service handler after the filing system (composite),
    # so it is read-only; DEMO-B is plain.
    assert not a.is_plain
    assert b.is_plain


def test_filename_may_contain_a_slash():
    # ROMFS/CFS names are flat byte strings: '/' is a legal filename
    # character, not a path separator. Tree Of Knowledge has a file "M/C".
    by_name = {f.name: f for f in load("Electron_Tree_Of_Knowledge_1.rom").files}
    assert "M/C" in by_name
    assert by_name["M/C"].load_address == 0x5240


def test_whole_corpus_parses_with_valid_crcs():
    roms = sorted(ROMFS_DIRPATH.glob("*.rom"))
    assert len(roms) == 11
    for filepath in roms:
        rom = ROMFS.from_bytes(filepath.read_bytes())  # strict: raises on any bad CRC
        assert rom.files, f"{filepath.name} parsed no files"


def test_rejects_non_romfs():
    with pytest.raises(NotAROMFSError):
        ROMFS.from_bytes(b"\x00" * 16384)
