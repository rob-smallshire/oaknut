"""Multi-zone New Map (ADFS F format) reading.

Blank F is read from DiscImageManager's reference image (transient, GPL,
not committed). Cross-zone fragment addressing — the ``zone_spare*zone``
correction that only multi-zone discs exercise — is checked with a
white-box test that places a fragment in zone 2 exactly as in the *Guide
to Disc Formats* worked example and asserts the documented disc address.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs.adfs import ADFS, ADFS_F
from oaknut.adfs.new_map import DiscRecord, NewMap, compute_bootmap, write_bits

_DIM_BLANK_F = (
    Path.home() / "Code" / "DiscImageManager" / "Blank Images" / "Acorn ADFS" / "ADFS_F.adf"
)


def _f_disc_record(root: int = 0x209) -> DiscRecord:
    """The F-format disc record parameters (matching the guide's worked example)."""
    return DiscRecord(
        log2_sector_size=10,  # 1024
        sectors_per_track=10,
        heads=2,
        density=4,
        idlen=15,
        log2_bytes_per_map_bit=6,  # 64
        skew=1,
        boot_option=0,
        low_sector=0,
        nzones=4,
        zone_spare=1600,
        root=root,
        disc_size=1638400,
        disc_id=0,
        disc_name="TestF",
        disc_type=0x20158C78,
    )


def test_compute_bootmap_matches_dim_f():
    dr = _f_disc_record()
    assert compute_bootmap(dr) == 0xC6800


def test_cross_zone_fragment_address_matches_guide():
    """A fragment in zone 2 resolves to the guide's documented 0xC9000.

    The guide places fragment id 0x338 at disc byte 0xC7018 (zone 2, with
    map_start 0xC6840) and computes its disc address as 0xC9000. We build a
    map with that single fragment and confirm the reader agrees.
    """
    dr = _f_disc_record()
    secsize = dr.sector_size
    bootmap = compute_bootmap(dr)  # 0xC6800
    # Map view is bootmap-relative and spans both copies.
    map_view = bytearray(2 * dr.nzones * secsize)

    # Cells must tile contiguously (as on a real disc), so fill zone 2 from its
    # start up to the target fragment with a filler fragment (id 1), then place
    # fragment 0x338 at physical 0xC7018 as in the guide.
    zone2_start = 2 * secsize * 8 + 4 * 8  # after the 4-byte zone header
    frag_bit = (0xC7018 - bootmap) * 8
    write_bits(map_view, zone2_start, dr.idlen, 1)  # filler id
    write_bits(map_view, frag_bit - 1, 1, 1)  # filler stop bit, ending just before 0x338
    write_bits(map_view, frag_bit, dr.idlen, 0x338)
    write_bits(map_view, frag_bit + dr.idlen, 1, 1)  # 0x338 stop bit

    nm = NewMap(memoryview(map_view), dr, lambda a, n: b"\x00" * n)
    assert 0x338 in nm._fragments
    # object_start for indirect (frag 0x338, sector offset 0) — the guide's value.
    assert nm.object_start(0x338 << 8) == 0xC9000


def test_root_resolves_via_special_case():
    dr = _f_disc_record(root=0x209)
    map_view = bytearray(2 * dr.nzones * dr.sector_size)
    nm = NewMap(memoryview(map_view), dr, lambda a, n: b"\x00" * n)
    # Root is special-cased to bootmap + nzones*secsize*2, independent of bitmap.
    assert nm.object_start(0x209) == 0xC6800 + 4 * 1024 * 2  # 0xC8800


@pytest.mark.skipif(not _DIM_BLANK_F.exists(), reason="DIM reference blank not present")
def test_read_blank_f():
    with ADFS.from_file(_DIM_BLANK_F) as adfs:
        assert adfs.is_new_map
        assert adfs._map.disc_record.nzones == 4
        assert adfs.total_size == 1638400
        assert list(adfs.root.iterdir()) == []
        assert adfs.validate() == []  # all four zone checks pass
        assert 0 < adfs.free_space < adfs.total_size


def test_create_blank_f_validates_and_is_empty():
    adfs = ADFS.create(ADFS_F, title="MadeF")
    try:
        assert adfs.is_new_map
        assert adfs._map.disc_record.nzones == 4
        assert adfs.total_size == 1638400
        assert adfs.disc_name == "MadeF"
        assert list(adfs.root.iterdir()) == []
        assert adfs.validate() == []  # all four zone checks
    finally:
        adfs.close()


def test_create_file_f_on_disk_reopens(tmp_path):
    image = tmp_path / "blank.adf"
    with ADFS.create_file(image, ADFS_F, title="DiscF") as adfs:
        assert adfs.is_new_map
    assert image.stat().st_size == 1638400
    with ADFS.from_file(image) as adfs:
        assert adfs.is_new_map
        assert adfs._map.disc_record.nzones == 4
        assert adfs.validate() == []
        assert list(adfs.root.iterdir()) == []


@pytest.mark.skipif(not _DIM_BLANK_F.exists(), reason="DIM reference blank not present")
def test_created_f_matches_dim_structurally():
    """Created blank F is byte-identical to DIM's except id and don't-care pads."""
    dim = _DIM_BLANK_F.read_bytes()
    adfs = ADFS.create(ADFS_F, title="ADFS\xa0F")
    try:
        raw = bytes(adfs._disc.sector_range(0, ADFS_F.total_sectors))
    finally:
        adfs.close()
    bootmap = 0xC6800
    # All four zone headers (FreeLink + CrossCheck) are byte-identical.
    for zone in range(4):
        zb = bootmap + zone * 1024
        assert raw[zb + 1 : zb + 4] == dim[zb + 1 : zb + 4], f"zone {zone} header"
    # The entire bitmap region (past zone 0's disc record) matches.
    assert raw[bootmap + 0x40 : bootmap + 4 * 1024] == dim[bootmap + 0x40 : bootmap + 4 * 1024]
    # Boot block: defect terminator, partial disc record and checksum.
    assert raw[0xC00:0xC04] == dim[0xC00:0xC04]
    assert raw[0xDC0:0xDD4] == dim[0xDC0:0xDD4]
    assert raw[0xDFF] == dim[0xDFF]


@pytest.mark.skipif(not _DIM_BLANK_F.exists(), reason="DIM reference blank not present")
def test_multizone_write_is_refused():
    buffer = memoryview(bytearray(_DIM_BLANK_F.read_bytes()))
    adfs = ADFS.from_buffer(buffer)
    try:
        with pytest.raises(Exception):
            (adfs.root / "Nope").write_bytes(b"x")
    finally:
        adfs.close()
