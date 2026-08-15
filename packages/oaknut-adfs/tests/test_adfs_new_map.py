"""New Map (ADFS E format) reading tests.

Rung 2: the single-zone New Map — a FileCore disc record, a zoned
allocation bitmap, and fragment-based object addressing. File objects are
no longer contiguous; an entry's indirect disc address is a fragment ID
plus a within-fragment sector offset resolved through the map.

Specimen: ``E_RISCOS310_NewLook.adf`` (RISC OS 3.10 NewLook kit), a
single-zone new-map disc (see the corpus README). Writing New Map discs
is a later rung, so mutation is expected to be refused here.
"""

from __future__ import annotations

import pytest
from oaknut.adfs.adfs import ADFS
from oaknut.adfs.directory import NewDirectoryFormat
from oaknut.adfs.exceptions import ADFSError
from oaknut.adfs.new_map import DiscRecord, calculate_zone_check

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

RISCOS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "adfs-riscos"
NEWLOOK = RISCOS_DIRPATH / "E_RISCOS310_NewLook.adf"


def test_e_format_detected_as_new_map():
    with ADFS.from_file(NEWLOOK) as adfs:
        assert adfs.is_new_map
        assert isinstance(adfs._dir_format, NewDirectoryFormat)


def test_disc_record_fields():
    raw = NEWLOOK.read_bytes()
    dr = DiscRecord.parse(raw)
    assert dr.sector_size == 1024
    assert dr.idlen == 15
    assert dr.bytes_per_map_bit == 128
    assert dr.nzones == 1
    assert dr.root == 0x203
    assert dr.disc_size == 819200
    assert dr.disc_name == "NewLook"


def test_zone_check_matches_stored():
    raw = NEWLOOK.read_bytes()
    dr = DiscRecord.parse(raw)
    sector = bytearray(raw[: dr.sector_size])
    assert calculate_zone_check(sector, 0, dr.log2_sector_size) == raw[0]


def test_disc_level_metadata_from_disc_record():
    with ADFS.from_file(NEWLOOK) as adfs:
        assert adfs.total_size == 819200
        assert adfs.disc_name == "NewLook"
        assert 0 < adfs.free_space < adfs.total_size


def test_root_listing():
    with ADFS.from_file(NEWLOOK) as adfs:
        names = {p.name for p in adfs.root.iterdir()}
    assert {"!NewLook", "ReadMe", "OldTempl", "TemplApp1", "TemplApp2", "TemplSupp"} <= names


def test_read_file_via_fragment():
    with ADFS.from_file(NEWLOOK) as adfs:
        readme = adfs.root / "ReadMe"
        stat = readme.stat()
        assert not stat.is_directory
        data = readme.read_bytes()
    assert len(data) == stat.length == 1820
    assert data[:1].isascii()


def test_descend_subdirectory():
    with ADFS.from_file(NEWLOOK) as adfs:
        newlook = adfs.root / "!NewLook"
        assert newlook.is_dir()
        # Every child resolves through the map and stats cleanly.
        children = list(newlook.iterdir())
        assert children
        for child in children:
            child.stat()


def test_whole_tree_validates():
    with ADFS.from_file(NEWLOOK) as adfs:
        assert adfs.validate() == []


def test_every_object_resolves_and_reads():
    """Walk the whole tree; read every file's full length via the map."""
    with ADFS.from_file(NEWLOOK) as adfs:

        def walk(path):
            count = 0
            for child in path.iterdir():
                count += 1
                if child.is_dir():
                    count += walk(child)
                else:
                    assert len(child.read_bytes()) == child.stat().length
            return count

        assert walk(adfs.root) > 10


def test_writing_into_a_real_new_map_disc():
    """Write into a mutable copy of a real RISC OS E disc (not the corpus file)."""
    buffer = memoryview(bytearray(NEWLOOK.read_bytes()))
    adfs = ADFS.from_buffer(buffer)
    try:
        (adfs.root / "OaknutFile").write_bytes(b"added by oaknut")
        assert adfs.validate() == []
        assert (adfs.root / "OaknutFile").read_bytes() == b"added by oaknut"
        # Pre-existing files are untouched.
        assert (adfs.root / "ReadMe").stat().length == 1820
    finally:
        adfs.close()
