"""Creating blank single-zone New Map (ADFS E) discs.

Round-trip validation (the chosen strategy): a freshly created blank E is
re-read with the verified New Map reader and must validate cleanly, present
an empty root, and report the right size and free space.

Confidence is additionally built by comparing the format-defining bytes
against DiscImageManager's reference blank (``~/Code/DiscImageManager``,
GPL-3 — used transiently, never committed) when it is present.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs.adfs import ADFS, ADFS_E
from oaknut.adfs.new_map import DiscRecord, calculate_zone_check

_DIM_BLANK = (
    Path.home() / "Code" / "DiscImageManager" / "Blank Images" / "Acorn ADFS" / "ADFS_E.adf"
)


def test_create_blank_e_is_new_map_with_empty_root():
    adfs = ADFS.create(ADFS_E, title="TestE")
    try:
        assert adfs.is_new_map
        assert list(adfs.root.iterdir()) == []
        assert adfs.total_size == 819200
        assert adfs.disc_name == "TestE"
        # Free = everything but the 4096-byte system+root fragment.
        assert adfs.free_space == 819200 - 4096
    finally:
        adfs.close()


def test_create_blank_e_validates():
    adfs = ADFS.create(ADFS_E, title="TestE")
    try:
        assert adfs.validate() == []
    finally:
        adfs.close()


def test_create_blank_e_zone_and_dir_checks_are_consistent():
    """The created image must satisfy its own zone check and root dir check."""
    adfs = ADFS.create(ADFS_E, title="TestE")
    try:
        # sector_range over the whole image gives the raw bytes.
        raw = bytes(adfs._disc.sector_range(0, ADFS_E.total_sectors))
    finally:
        adfs.close()
    dr = DiscRecord.parse(raw)
    assert dr.nzones == 1 and dr.root == 0x203
    assert calculate_zone_check(raw[: dr.sector_size], 0, dr.log2_sector_size) == raw[0]
    # Map is duplicated: primary zone equals its copy.
    assert raw[: dr.sector_size] == raw[dr.sector_size : dr.sector_size * 2]
    # Root New directory signature is "Nick".
    assert raw[0x801:0x805] == b"Nick"


def test_created_blank_reopens_via_from_buffer():
    adfs = ADFS.create(ADFS_E, title="TestE")
    try:
        raw = bytes(adfs._disc.sector_range(0, ADFS_E.total_sectors))
    finally:
        adfs.close()
    reopened = ADFS.from_buffer(memoryview(bytearray(raw)))
    try:
        assert reopened.is_new_map
        assert reopened.validate() == []
        assert list(reopened.root.iterdir()) == []
    finally:
        reopened.close()


def test_create_file_e_on_disk(tmp_path):
    """A blank E written to disk reopens as a valid, empty New Map disc."""
    image = tmp_path / "blank.adf"
    with ADFS.create_file(image, ADFS_E, title="OnDisk") as adfs:
        assert adfs.is_new_map
        assert list(adfs.root.iterdir()) == []
    assert image.stat().st_size == 819200
    with ADFS.from_file(image) as adfs:
        assert adfs.is_new_map
        assert adfs.validate() == []
        assert adfs.disc_name == "OnDisk"
        assert list(adfs.root.iterdir()) == []


@pytest.mark.skipif(not _DIM_BLANK.exists(), reason="DIM reference blank not present")
def test_format_defining_bytes_match_dim_reference():
    """Compare the structural bytes against DIM's reference blank.

    Title, disc id and root name are our own choices, so match them to DIM's
    for this comparison and then assert the map, zone header, bitmap and root
    directory structure are byte-identical over the leading system region.
    """
    dim = _DIM_BLANK.read_bytes()

    adfs = ADFS.create(ADFS_E, title="ADFS\xa0E")
    try:
        raw = bytes(adfs._disc.sector_range(0, ADFS_E.total_sectors))
    finally:
        adfs.close()

    # Zone header: FreeLink and CrossCheck are format-defining (ZoneCheck too,
    # but it depends on the disc record which carries our differing disc id).
    assert raw[1:3] == dim[1:3], "FreeLink differs"
    assert raw[3] == dim[3], "CrossCheck differs"

    # Bitmap: system fragment (id 2, 32 bits) and the free terminator bit.
    assert raw[0x40] == dim[0x40] == 0x02
    assert raw[0x43] == dim[0x43] == 0x80
    assert raw[0x35F] == dim[0x35F] == 0x80

    # Disc record structural fields (everything but disc id at 0x18-0x19 and
    # the name at 0x1A-0x23).
    assert raw[0x04:0x18] == dim[0x04:0x18], "disc record head differs"
    assert raw[0x24:0x28] == dim[0x24:0x28], "disctype differs"

    # Root directory tail: parent, signature and check byte.
    tail = 0x800 + 0x7D7
    assert raw[tail + 3 : tail + 6] == dim[tail + 3 : tail + 6]  # parent 0x203
    assert raw[tail + 0x24 : tail + 0x28] == dim[tail + 0x24 : tail + 0x28] == b"Nick"
